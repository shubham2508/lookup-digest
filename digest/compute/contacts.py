"""Contacts and relationship resolution (architecture §6.1), behavior stats, drift. Code only.

Resolution order, per contact: 1 profile match (email or name) → 2 role-at-org rule (org from domain/signature and
title matches the role) → 3 internal domain → team → 4 domain learned from resolved customer/capital/vendor
contacts → 5 majority of relationship hints (≥2 consistent, or 1 with a signature title) → 6 unresolved.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..normalize import NormalizedWorld
from ..schemas import (
    Behavior,
    Contact,
    Drift,
    Evidence,
    Extraction,
    HumanThread,
    ProfileConfig,
    ProfileContact,
    Relationship,
    RoleChange,
    SenderObservation,
    StageSignal,
)
from ..util import domain_of, fold, norm_name, org_from_domain, slugify

LEARNABLE = ("customer", "capital", "vendor")


@dataclass
class _Obs:
    email: str
    names: Counter = field(default_factory=Counter)
    titles: Counter = field(default_factory=Counter)
    orgs: Counter = field(default_factory=Counter)
    hints: list[tuple[str, str | None, bool]] = field(default_factory=list)   # (hint, subtype, has_title)
    introduced_by: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    router_types: Counter = field(default_factory=Counter)


@dataclass
class RoleRule:
    role: str
    orgs: list[str]
    contact: ProfileContact


@dataclass
class ContactDirectory:
    contacts: list[Contact]
    by_email: dict[str, Contact]
    by_slug: dict[str, Contact]
    role_rules: list[RoleRule]
    role_changes: list[tuple[RoleChange, str]] = field(default_factory=list)   # (change, source_id)

    def lookup(self, email: str | None = None, name: str | None = None) -> Contact | None:
        if email and email.lower() in self.by_email:
            return self.by_email[email.lower()]
        if name:
            s = slugify(name)
            if s in self.by_slug:
                return self.by_slug[s]
            n = norm_name(name)
            for c in self.contacts:
                if any(norm_name(x) == n for x in c.names):
                    return c
            # first-name match only when unique
            first = n.split(" ")[0] if n else ""
            if first:
                hits = [c for c in self.contacts if any(norm_name(x).split(" ")[0] == first for x in c.names)]
                if len(hits) == 1:
                    return hits[0]
        return None

    def slug_map(self) -> dict[str, str]:
        """name/org slug → contact slug, for about-key canonicalization."""
        out: dict[str, str] = {}
        for c in self.contacts:
            for n in c.names:
                out[slugify(n)] = c.contact_id
                parts = n.split()
                if len(parts) >= 2:
                    out.setdefault(slugify(parts[0]), c.contact_id)
        return out


def collect_observations(world: NormalizedWorld, extractions: list[Extraction]) -> dict[str, _Obs]:
    obs: dict[str, _Obs] = {}
    owner = world.owner_emails

    def get(email: str) -> _Obs:
        e = email.lower()
        if e not in obs:
            obs[e] = _Obs(email=e)
        return obs[e]

    for t in world.threads:
        for m in t.messages:
            if m.from_addr and m.from_addr not in owner:
                o = get(m.from_addr)
                if m.from_name:
                    o.names[m.from_name] += 1
                o.router_types[t.router_type] += 1
            for addr in [*m.to, *m.cc]:
                if addr and addr not in owner and t.router_type in ("human", "unsure"):
                    get(addr)
    for x in extractions:
        if x.type == "human_thread" and isinstance(x.payload, HumanThread):
            for so in x.payload.sender_observations:
                if not so.email or so.email.lower() in owner:
                    continue
                o = get(so.email)
                if so.name:
                    o.names[so.name] += 1
                if so.title:
                    o.titles[so.title] += 1
                if so.org:
                    o.orgs[so.org] += 1
                o.hints.append((so.relationship_hint, so.subtype_hint, bool(so.title)))
                o.introduced_by = o.introduced_by or so.introduced_by
                o.evidence.extend(so.evidence[:2])
    for e in world.events:      # calendar-only people: organizers and attendees
        for addr, name in [(e.organizer, ""), *[(a.email, a.name) for a in e.attendees]]:
            if addr and addr not in owner:
                o = get(addr)
                if name:
                    o.names[name] += 1
                o.router_types["calendar"] += 1
    for m in world.messages:   # header display names for everyone
        for addr, name in [(m.from_addr, m.from_name)]:
            if addr in obs and name:
                obs[addr].names.setdefault(name, 0)
    return obs


def _profile_contacts(profile: ProfileConfig) -> tuple[list[Contact], list[RoleRule]]:
    contacts: list[Contact] = []
    rules: list[RoleRule] = []
    for pc in profile.contacts:
        if pc.role_at_org and not pc.name:
            rules.append(RoleRule(pc.role_at_org.role, list(pc.role_at_org.orgs), pc))
            continue
        if not pc.name:
            continue
        contacts.append(Contact(
            contact_id=slugify(pc.name), names=[pc.name], emails=[e.lower() for e in pc.emails],
            relationship=Relationship(category=pc.category, subtype=pc.subtype, source="profile"),
            tier=pc.tier, profile_rules=list(pc.rules),
        ))
    return contacts, rules


def _role_at_org_answers(pending, rules, linker) -> dict[int, int]:
    """{pending index → rule index}: which profile role-at-org rule (e.g. 'procurement lead at Halberd, Northstar or
    Veritas') a sender holds, judged by the linker from their signature title and org. Without a linker: exact
    (case-insensitive) org name or domain, and the role phrase contained in the title."""
    if not rules:
        return {}
    if linker is None:
        out = {}
        for i, (c, o) in enumerate(pending):
            orgs_seen = {fold(c.org or ""), fold(org_from_domain(o.email) or "")}
            for j, r in enumerate(rules):
                if orgs_seen & {fold(x) for x in r.orgs} and c.title and fold(r.role) in fold(c.title):
                    out[i] = j
                    break
        return out
    from .linker import LinkOption, LinkQuestion

    options = [LinkOption(id=f"r{j}", text=f"{r.role} at one of: {', '.join(r.orgs)}") for j, r in enumerate(rules)]
    qs = [LinkQuestion(id=f"s{i}", item=f"{c.names[0] if c.names else o.email} <{o.email}>; title: {c.title or 'none'}; "
                                       f"org: {c.org or org_from_domain(o.email) or 'unknown'}", options=options)
          for i, (c, o) in enumerate(pending) if c.title or c.org]
    ans = linker.match("role_at_org", qs)
    return {int(q[1:]): int(m[0][1:]) for q, m in ans.items() if m}


def build_contacts(world: NormalizedWorld, extractions: list[Extraction], profile: ProfileConfig, linker=None) -> ContactDirectory:
    contacts, rules = _profile_contacts(profile)
    by_email: dict[str, Contact] = {e: c for c in contacts for e in c.emails}
    by_slug: dict[str, Contact] = {c.contact_id: c for c in contacts}
    obs = collect_observations(world, extractions)
    owner_domain = domain_of(world.owner_email or "")
    pending: list[tuple[Contact, _Obs]] = []

    for email, o in obs.items():
        best_name = o.names.most_common(1)[0][0] if o.names else ""
        # 1. profile match by email or name
        c = by_email.get(email)
        if c is None and best_name:
            n = norm_name(best_name)
            c = next((x for x in contacts if any(norm_name(y) == n for y in x.names)), None)
        if c is None:
            cid = slugify(best_name) if best_name else slugify(email.split("@")[0])
            if cid in by_slug and email not in by_slug[cid].emails and best_name:
                cid = f"{cid}-{slugify(domain_of(email).split('.')[0])}"
            c = by_slug.get(cid)
            if c is None:
                c = Contact(contact_id=cid, names=[best_name] if best_name else [], emails=[email])
                contacts.append(c)
                by_slug[cid] = c
        if email not in c.emails:
            c.emails.append(email)
        by_email[email] = c
        for n in o.names:
            if n and n not in c.names:
                c.names.append(n)
        if o.titles and not c.title:
            c.title = o.titles.most_common(1)[0][0]
        if o.orgs and not c.org:
            c.org = o.orgs.most_common(1)[0][0]
        c.relationship.evidence = (c.relationship.evidence + o.evidence)[:4]
        if c.relationship.source == "profile":
            continue
        pending.append((c, o))

    # 2. role-at-org, 3. internal domain, then 4/5/6
    learned_domains: dict[str, str] = {}
    for c in contacts:
        if c.relationship.source == "profile" and c.relationship.category in LEARNABLE:
            for e in c.emails:
                learned_domains[domain_of(e)] = c.relationship.category
    unresolved: list[tuple[Contact, _Obs]] = []
    role_answers = _role_at_org_answers(pending, rules, linker)
    for i, (c, o) in enumerate(pending):
        email = o.email
        matched = False
        if i in role_answers:
            r = rules[role_answers[i]]
            c.relationship = Relationship(category=r.contact.category, subtype=r.contact.subtype, source="profile",
                                          evidence=c.relationship.evidence)
            c.tier = r.contact.tier
            c.profile_rules = list(r.contact.rules)
            matched = True
        if matched:
            if c.relationship.category in LEARNABLE:
                learned_domains[domain_of(email)] = c.relationship.category
            continue
        if owner_domain and domain_of(email) == owner_domain:
            c.relationship = Relationship(category="team", subtype=None, source="inferred", evidence=c.relationship.evidence)
            continue
        if o.router_types and set(o.router_types) <= {"automated", "newsletter", "marketing"} and "calendar" not in o.router_types:
            c.relationship = Relationship(category="automated", subtype=o.router_types.most_common(1)[0][0], source="inferred")
            continue
        unresolved.append((c, o))
    for c, o in unresolved:
        dom = domain_of(o.email)
        hints = [h for h in o.hints if h[0] != "unresolved"]
        if dom in learned_domains and not any(h[0] == "cold_inbound" for h in hints):
            cat = learned_domains[dom]
            sub = next((h[1] for h in hints if h[0] == cat and h[1]), None)
            c.relationship = Relationship(category=cat, subtype=sub, source="inferred", evidence=c.relationship.evidence)
            continue
        if hints:
            counts = Counter(h[0] for h in hints)
            top, n = counts.most_common(1)[0]
            consistent = (n >= 2 and n == len(hints)) or (n == 1 and len(hints) == 1 and (hints[0][2] or top == "cold_inbound"))
            if consistent or (n >= 2 and n / len(hints) >= 0.66):
                sub = next((h[1] for h in hints if h[0] == top and h[1]), None)
                c.relationship = Relationship(category=top, subtype=sub, source="inferred", evidence=c.relationship.evidence)
                if top in LEARNABLE:
                    learned_domains.setdefault(dom, top)
                continue
        c.relationship = Relationship(category="unresolved", source="unresolved", evidence=c.relationship.evidence)
    d = ContactDirectory(contacts, by_email, by_slug, rules)
    apply_stages(d, extractions)
    apply_role_changes(d, extractions)
    return d


def _entity_contacts(d: ContactDirectory, name: str, hint: str | None) -> list[Contact]:
    c = d.lookup(hint, name)
    if c:
        return [c]
    # org-level entity: every contact of that org
    hits = [x for x in d.contacts if x.org and fold(x.org) == fold(name)]
    return hits


def apply_stages(d: ContactDirectory, extractions: list[Extraction]) -> None:
    latest: dict[str, tuple[datetime, StageSignal]] = {}
    for x in extractions:
        p = x.payload
        signals: list[StageSignal] = getattr(p, "stage_signals", []) if p is not None else []
        for s in signals:
            for c in _entity_contacts(d, s.entity.name, s.entity.contact_hint):
                cur = latest.get(c.contact_id)
                if cur is None or s.at > cur[0]:
                    latest[c.contact_id] = (s.at, s)
    for cid, (_, s) in latest.items():
        c = d.by_slug.get(cid)
        if c is not None:
            c.relationship.stage = s.stage
            if s.evidence not in c.relationship.evidence:
                c.relationship.evidence = (c.relationship.evidence + [s.evidence])[:5]


def apply_role_changes(d: ContactDirectory, extractions: list[Extraction]) -> None:
    """'I'm taking over from Renee' → the successor inherits the predecessor's profile category/tier/rules; the
    predecessor's record and the effective facts carry the drift (architecture §6.1 Drift)."""
    for x in extractions:
        p = x.payload
        changes: list[RoleChange] = getattr(p, "role_changes", []) if p is not None else []
        for rc in changes:
            successor = d.lookup(rc.person)
            pred = d.lookup(rc.replaces, rc.replaces) if rc.replaces else None
            d.role_changes.append((rc, x.source_id))
            if successor is None:
                continue
            if rc.new_role and not successor.title:
                successor.title = rc.new_role
            if rc.org and not successor.org:
                successor.org = rc.org
            if pred is not None and pred.relationship.source == "profile":
                successor.relationship = Relationship(category=pred.relationship.category, subtype=pred.relationship.subtype,
                                                      stage=pred.relationship.stage, source="inferred",
                                                      evidence=[rc.evidence])
                successor.tier = successor.tier or pred.tier
                for r in pred.profile_rules:
                    if r not in successor.profile_rules:
                        successor.profile_rules.append(r)
                pred.drift.append(Drift(field="role", profile_value=f"{pred.title or pred.relationship.subtype or 'contact'} at {pred.org or ''}".strip(),
                                        data_value=f"replaced by {successor.names[0] if successor.names else rc.person}"
                                                   + (f" as {rc.new_role}" if rc.new_role else ""), evidence=[rc.evidence]))
                successor.drift.append(Drift(field="role", profile_value=None,
                                             data_value=f"{rc.new_role or 'new role'} at {rc.org or pred.org or ''}, replacing {rc.replaces}".strip(),
                                             evidence=[rc.evidence]))
            else:
                successor.drift.append(Drift(field="role", profile_value=None,
                                             data_value=f"{rc.new_role or 'new role'} at {rc.org or ''}".strip(), evidence=[rc.evidence]))


def behavior_stats(d: ContactDirectory, world: NormalizedWorld, as_of: datetime, window_days: int = 30) -> None:
    start = as_of - timedelta(days=window_days)
    owner = world.owner_emails
    per: dict[str, dict] = defaultdict(lambda: {"in": [], "out": [], "replies": [], "started": 0, "threads": 0})
    for t in world.threads:
        if t.router_type not in ("human", "unsure"):
            continue
        parts = {a for m in t.messages for a in (m.from_addr, *m.to, *m.cc) if a and a not in owner}
        cids = {d.by_email[a].contact_id for a in parts if a in d.by_email}
        first = t.messages[0]
        for cid in cids:
            per[cid]["threads"] += 1
            if first.from_addr in d.by_email and d.by_email[first.from_addr].contact_id == cid:
                per[cid]["started"] += 1
        msgs = [m for m in t.messages if start <= m.sent_at <= as_of]
        for i, m in enumerate(msgs):
            if m.from_addr in owner:
                for cid in cids:
                    per[cid]["out"].append(m.sent_at)
                continue
            c = d.by_email.get(m.from_addr)
            if c is None:
                continue
            per[c.contact_id]["in"].append(m.sent_at)
            reply = next((r for r in msgs[i + 1:] if r.from_addr in owner), None)
            per[c.contact_id]["replies"].append((reply.sent_at - m.sent_at).total_seconds() / 3600 if reply else None)
    meetings: Counter[str] = Counter()
    for e in world.events:
        if start <= e.start <= as_of and any(a.email in owner for a in e.attendees) or (e.organizer in owner and start <= e.start <= as_of):
            for a in e.attendees:
                if a.email in d.by_email and a.email not in owner:
                    meetings[d.by_email[a.email].contact_id] += 1
    for c in d.contacts:
        s = per.get(c.contact_id)
        b = Behavior(shared_meetings_30d=meetings.get(c.contact_id, 0))
        if s:
            answered = [h for h in s["replies"] if h is not None]
            b.avery_reply_rate = round(len(answered) / len(s["replies"]), 2) if s["replies"] else None
            b.median_avery_reply_hours = round(statistics.median(answered), 1) if answered else None
            b.last_inbound = max(s["in"]) if s["in"] else None
            b.last_outbound = max(s["out"]) if s["out"] else None
            b.initiation_ratio = round(s["started"] / s["threads"], 2) if s["threads"] else None
        c.behavior = b


__all__ = ["ContactDirectory", "RoleRule", "build_contacts", "behavior_stats", "collect_observations", "apply_stages",
           "apply_role_changes", "SenderObservation"]
