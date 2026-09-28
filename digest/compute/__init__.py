"""Compute stage (architecture §6): contacts → effective facts → about-key merge → candidates → context. Code only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import Settings
from ..normalize import NormalizedWorld
from ..schemas import AboutMerge, Candidate, Contact, Extraction, ProfileConfig
from .aboutkeys import AboutMerger, canonical_key
from .candidates import ComputeInputs, generate, resolve_thresholds
from .contacts import ContactDirectory, behavior_stats, build_contacts
from .context import ContextIndex, apply_context
from .facts import EffectiveFact, collect_claims, effective_facts


@dataclass
class ComputeResult:
    contacts: list[Contact]
    directory: ContactDirectory
    facts: list[EffectiveFact]
    candidates: list[Candidate]
    about_merges: list[AboutMerge]
    about_map: dict[str, str]
    context: ContextIndex
    stats: dict = field(default_factory=dict)

    def facts_for_prompt(self) -> list[dict]:
        return [{"subject": f.subject, "effective": f.effective, "profile_value": f.profile_value, "data_value": f.data_value,
                 "drift": f.drift, "evidence": [e.model_dump(mode="json") for e in f.evidence]} for f in self.facts]


def _extraction_keys(extractions: list[Extraction], slug_map: dict[str, str], msg_thread: dict[str, str]) -> AboutMerger:
    """Every about key in the extractions, with the entities and evidence messages that carry it."""
    merger = AboutMerger()
    for x in extractions:
        p = x.payload
        if p is None:
            continue
        ents: set[str] = set()
        for so in getattr(p, "sender_observations", []) or []:
            ents.add(so.email.lower())
            if so.name:
                ents.add(slug_map.get(so.name.lower(), so.name.lower()))
        for e in getattr(p, "entities", []) or []:
            ents.add(e.name.lower())
        msgs = {x.source_id}
        keys: list[str] = []
        for a in getattr(p, "about", []) or []:
            keys.append(a)
        if isinstance(getattr(p, "about", None), str):
            keys.append(p.about)
        for c in list(getattr(p, "commitments", []) or []) + list(getattr(p, "action_items", []) or []) + list(getattr(p, "deferrals", []) or []):
            keys.append(c.about)
            msgs.add(msg_thread.get(c.evidence.source_id, c.evidence.source_id))
            ents.update(w.lower() for w in getattr(c, "to_whom", []) or [])
        for d in getattr(p, "decisions", []) or []:
            keys.append(d.about)
        for k in keys:
            merger.add(canonical_key(k, slug_map), ents, msgs)
    return merger


def _inherit_org_tiers(directory) -> None:
    """DESIGN_LOG §9.6 / P0 cases 5 and 12: a colleague of a profile contact at the same org (another IPV partner, the
    WSGR associate) inherits that contact's tier during the raise. Rules such as never_draft do not propagate."""
    from ..util import slugify

    org_tier: dict[str, str] = {}
    for c in directory.contacts:
        if c.relationship.source == "profile" and c.tier and c.org:
            org_tier[slugify(c.org)] = max(org_tier.get(slugify(c.org), "P9"), c.tier, key=lambda x: -int(x[1]))
        if c.relationship.source == "profile" and c.tier:
            for e in c.emails:
                org_tier[e.split("@")[-1].lower()] = c.tier
    for c in directory.contacts:
        if c.tier or c.relationship.source == "profile":
            continue
        keys = ([slugify(c.org)] if c.org else []) + [e.split("@")[-1].lower() for e in c.emails]
        for k in keys:
            if k in org_tier:
                c.tier = org_tier[k]
                break


def compute_world(world: NormalizedWorld, extractions: list[Extraction], profile: ProfileConfig, settings: Settings,
                  as_of: datetime) -> ComputeResult:
    directory = build_contacts(world, extractions, profile)
    _inherit_org_tiers(directory)
    behavior_stats(directory, world, as_of, settings.thresholds_default.behavior_window_days)
    slug_map = directory.slug_map()
    note_dates = {f"note:{n.path}": n.header_date for n in world.notes}
    facts = effective_facts(profile, collect_claims(extractions, note_dates))
    msg_thread = {f"msg:{m.message_id}": t.thread_id for t in world.threads for m in t.messages}
    merger = _extraction_keys(extractions, slug_map, msg_thread)
    generic = {"avery", "avery-chen", "tessera"} | set(world.owner_emails)
    for c in directory.contacts:
        if c.relationship.category == "team" or any(e in world.owner_emails for e in c.emails):
            generic |= {c.contact_id, *[e.lower() for e in c.emails], *[n.lower() for n in c.names]}
    merger.generic_entities = generic
    about_map, merges = merger.resolve()
    ci = ComputeInputs(world, extractions, profile, settings, as_of, directory, facts, about_map, resolve_thresholds(profile, settings))
    cands = generate(ci)
    cold = {c.contact_id for c in directory.contacts if c.relationship.category == "cold_inbound"}
    if cold:  # architecture §6.4 / §8: individual cold-inbound threads never become candidates
        cands = [c for c in cands if c.type == "recruiter_pattern" or not any(e in cold for e in c.entities)]
    # second pass: candidate-made keys (meeting:…, other:…) may merge with extraction keys
    for c in cands:
        merger.add(c.about, set(c.entities), {msg_thread.get(e.source_id, e.source_id) for e in c.evidence})
    about_map, merges = merger.resolve()
    for c in cands:
        c.about = about_map.get(c.about, c.about)
    idx = ContextIndex(world, extractions, as_of, settings.context.window_days, settings.context.max_items)
    apply_context(cands, idx, world.freshness)
    cands.sort(key=lambda c: (c.type, c.about, c.evidence[0].source_id if c.evidence else ""))
    for i, c in enumerate(cands, 1):
        c.candidate_id = f"c{i}"
    stats = {"contacts": len(directory.contacts), "candidates": len(cands), "by_type": {}, "about_merges": len(merges),
             "facts_drift": sum(1 for f in facts if f.drift)}
    for c in cands:
        stats["by_type"][c.type] = stats["by_type"].get(c.type, 0) + 1
    return ComputeResult(directory.contacts, directory, facts, cands, merges, about_map, idx, stats)


__all__ = ["ComputeResult", "compute_world", "ContactDirectory", "EffectiveFact"]
