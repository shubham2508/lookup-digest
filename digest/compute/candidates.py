"""Candidate generation (architecture §6.4): every rule is code. Each generator is a function over ComputeInputs
returning Candidates; ids are assigned once at the end. Facts are plain dicts for triage; evidence is verbatim."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from ..config import Settings
from ..normalize import NormalizedWorld
from ..schemas import (
    Automated,
    Candidate,
    CandidateType,
    Commitment,
    Contact,
    Evidence,
    Extraction,
    HumanThread,
    Newsletter,
    NormalizedEvent,
    NormalizedThread,
    Note,
    ProfileConfig,
    TaskLink,
)
from ..util import fold, slugify
from .aboutkeys import canonical_key
from .contacts import ContactDirectory
from .facts import EffectiveFact
from .signals import (
    block_windows,
    business_days_between,
    cadence_days,
    cadence_stats,
    days_overdue,
    day_label,
    days_since,
    due_bucket,
    end_of_business_day,
    hours_since,
    overlap_minutes,
    recruiter_window,
)

WORK_HOURS = (time(9, 0), time(18, 0))
RECRUITER_WORDS = ("recruit", "talent", "search", "staffing", "headhunt", "sourcer")


@dataclass
class Thresholds:
    investor_quiet_business_days: int
    hiring_stall_days: int
    recruiter_count: int
    recruiter_window_days: int
    cadence_ratio: float
    cadence_min_gap_days: int
    cadence_baseline: tuple[int, int]
    cadence_recent: tuple[int, int]
    declined_lookback_days: int
    family_lookahead_days: int
    behavior_window_days: int


def resolve_thresholds(profile: ProfileConfig, settings: Settings) -> Thresholds:
    d = settings.thresholds_default
    t = profile.thresholds
    rp = t.recruiter_pattern
    return Thresholds(
        investor_quiet_business_days=t.investor_quiet_business_days or d.investor_quiet_business_days,
        hiring_stall_days=t.hiring_stall_days or d.hiring_stall_days,
        recruiter_count=rp.count if rp else d.recruiter_pattern.count,
        recruiter_window_days=rp.window_days if rp else d.recruiter_pattern.window_days,
        cadence_ratio=d.cadence_drop.ratio, cadence_min_gap_days=d.cadence_drop.min_current_gap_days,
        cadence_baseline=tuple(d.cadence_drop.baseline_days), cadence_recent=tuple(d.cadence_drop.recent_days),
        declined_lookback_days=d.declined_meeting_lookback_days, family_lookahead_days=d.family_conflict_lookahead_days,
        behavior_window_days=d.behavior_window_days,
    )


@dataclass
class ComputeInputs:
    world: NormalizedWorld
    extractions: list[Extraction]
    profile: ProfileConfig
    settings: Settings
    as_of: datetime
    directory: ContactDirectory
    facts: list[EffectiveFact]
    about_map: dict[str, str]
    thresholds: Thresholds
    linker: object | None = None  # digest/compute/linker.Linker; None → exact matches only
    threads: dict[str, NormalizedThread] = field(init=False)
    msg_time: dict[str, datetime] = field(init=False)
    msg_thread: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.threads = {t.thread_id: t for t in self.world.threads}
        self.msg_time = {}
        self.msg_thread = {}
        for t in self.world.threads:
            for m in t.messages:
                self.msg_time[f"msg:{m.message_id}"] = m.sent_at
                self.msg_thread[f"msg:{m.message_id}"] = t.thread_id

    # ------------------------------------------------------------------ helpers
    def link(self, task: str, questions: list) -> dict[str, list[str]]:
        """Batched LLM sameness decisions (compute/linker.py); {} without a linker."""
        return self.linker.match(task, questions) if self.linker is not None else {}

    def canon(self, key: str) -> str:
        c = canonical_key(key, self.directory.slug_map())
        return self.about_map.get(c, c)

    def human(self) -> list[tuple[Extraction, HumanThread, NormalizedThread]]:
        out = []
        for x in self.extractions:
            if x.type == "human_thread" and isinstance(x.payload, HumanThread) and x.source_id in self.threads:
                out.append((x, x.payload, self.threads[x.source_id]))
        return out

    def notes(self) -> list[tuple[Extraction, Note]]:
        return [(x, x.payload) for x in self.extractions if x.type == "note" and isinstance(x.payload, Note)]

    def task_links(self) -> dict[str, TaskLink]:
        return {x.source_id: x.payload for x in self.extractions if x.type == "task" and isinstance(x.payload, TaskLink)}

    def contact(self, email: str | None = None, name: str | None = None) -> Contact | None:
        return self.directory.lookup(email, name)

    def slug(self, email: str | None = None, name: str | None = None) -> str | None:
        c = self.contact(email, name)
        return c.contact_id if c else (slugify(name) if name else None)

    def last_inbound(self, t: NormalizedThread) -> datetime | None:
        ins = [m.sent_at for m in t.messages if not m.is_from_avery]
        return max(ins) if ins else None

    def evidence_time(self, ev: Evidence) -> datetime | None:
        return self.msg_time.get(ev.source_id)

    def event_evidence(self, e: NormalizedEvent) -> Evidence:
        return Evidence(source_id=f"event:{e.uid}", quote=" ".join(e.title.split()[:20]) or e.uid)

    def today(self) -> datetime.date:
        return self.as_of.date()


def _contact_facts(c: Contact | None) -> dict:
    if c is None:
        return {}
    return {"contact": c.contact_id, "category": c.relationship.category, "subtype": c.relationship.subtype,
            "stage": c.relationship.stage, "tier": c.tier, "rules": c.profile_rules}


def _mk(type_: CandidateType, about: str, entities: list[str], facts: dict, evidence: list[Evidence]) -> Candidate:
    seen: list[Evidence] = []
    for e in evidence:
        if e not in seen:
            seen.append(e)
    return Candidate(candidate_id="", type=type_, about=about, entities=[e for e in dict.fromkeys(entities) if e],
                     facts=facts, evidence=seen[:6])


# ----------------------------------------------------------------------------- email-driven rules
def reply_owed(ci: ComputeInputs) -> list[Candidate]:
    out = []
    for _x, p, t in ci.human():
        escalation = p.intent_primary == "escalation"
        if not escalation and (p.ball.awaiting != "avery" or p.ball.closed_by_courtesy):
            continue  # an escalation is Avery's to know about even while the team holds the ball (S14)
        open_asks = [a for a in p.asks if a.to_avery and a.status == "open"]
        if p.intent_primary not in ("ask", "escalation") and not open_asks:
            continue
        last_in = ci.last_inbound(t)
        sender = ci.contact(t.messages[-1].from_addr if not t.messages[-1].is_from_avery else (last_msg := next((m for m in reversed(t.messages) if not m.is_from_avery), None)) and last_msg.from_addr)
        if sender is not None and sender.relationship.category == "cold_inbound":
            continue  # individual cold-inbound threads (recruiters, pitches) never become candidates; recruiter_pattern covers them
        deadlines = [a.deadline.resolved for a in open_asks if a.deadline and a.deadline.resolved]
        bd_in = business_days_between(last_in.date(), ci.today()) if last_in else None
        is_capital = sender is not None and sender.relationship.category == "capital"
        facts = {"thread_id": t.thread_id, "subject": t.messages[0].subject, "summary": p.summary, "intent": p.intent_primary,
                 "domain": p.domain, "hours_since_inbound": hours_since(last_in, ci.as_of) if last_in else None,
                 "business_days_since_inbound": bd_in,
                 "below_quiet_threshold": bool(is_capital and not deadlines and bd_in is not None
                                               and bd_in < ci.thresholds.investor_quiet_business_days),
                 "last_inbound_at": last_in.isoformat() if last_in else None,
                 "last_message_by_avery": t.messages[-1].is_from_avery,
                 "deadline": min(deadlines).isoformat() if deadlines else None,
                 "open_asks": [a.what for a in open_asks], "escalation": p.intent_primary == "escalation", **_contact_facts(sender)}
        ev = [p.ball.evidence] + [a.evidence for a in open_asks]
        out.append(_mk("reply_owed", ci.canon(p.about[0]) if p.about else f"other:{slugify(t.messages[0].subject)}",
                       [sender.contact_id if sender else "", slugify(sender.org) if sender and sender.org else ""], facts, ev))
    return out


def quiet_thread(ci: ComputeInputs) -> list[Candidate]:
    out = []
    th = ci.thresholds
    for _x, p, t in ci.human():
        senders = [ci.contact(m.from_addr) for m in t.messages if not m.is_from_avery]
        counterpart = next((c for c in senders if c), None)
        if counterpart is None:
            continue
        cat, sub, rules = counterpart.relationship.category, counterpart.relationship.subtype, counterpart.profile_rules
        about = ci.canon(p.about[0]) if p.about else f"other:{slugify(t.messages[0].subject)}"
        ents = [counterpart.contact_id, slugify(counterpart.org) if counterpart.org else ""]
        if cat == "capital":
            last_in = ci.last_inbound(t)
            if p.ball.awaiting == "avery" and last_in is not None:
                bd = business_days_between(last_in.date(), ci.today())
                if bd >= th.investor_quiet_business_days:
                    out.append(_mk("quiet_thread", about, ents, {
                        "thread_id": t.thread_id, "reason": "awaiting Avery", "business_days_quiet": bd,
                        "last_inbound_at": last_in.isoformat(), "threshold": th.investor_quiet_business_days,
                        "summary": p.summary, **_contact_facts(counterpart)}, [p.ball.evidence]))
                    continue
            for c in p.commitments:
                if c.owner == "avery" and c.status_in_thread == "open":
                    when = ci.evidence_time(c.evidence)
                    if when is None:
                        continue
                    bd = business_days_between(when.date(), ci.today())
                    if bd >= th.investor_quiet_business_days:
                        out.append(_mk("quiet_thread", ci.canon(c.about), ents, {
                            "thread_id": t.thread_id, "reason": "Avery's open commitment", "commitment": c.what,
                            "business_days_quiet": bd, "committed_at": when.isoformat(), "threshold": th.investor_quiet_business_days,
                            "summary": p.summary, **_contact_facts(counterpart)}, [c.evidence]))
                        break
        elif cat == "customer" and (sub == "reference" or "same_day_reply" in rules):
            for a in p.asks:
                if not (a.to_avery and a.status == "open"):
                    continue
                arrived = ci.evidence_time(a.evidence) or ci.last_inbound(t)
                if arrived is None:
                    continue
                eod = end_of_business_day(arrived)
                if ci.as_of > eod:
                    out.append(_mk("quiet_thread", about, ents, {
                        "thread_id": t.thread_id, "reason": "reference customer ask unanswered past end of business day",
                        "ask": a.what, "arrived_at": arrived.isoformat(), "answer_was_due": eod.isoformat(),
                        "hours_since_inbound": hours_since(arrived, ci.as_of), "summary": p.summary, **_contact_facts(counterpart)},
                        [a.evidence]))
                    break
    return out


def _all_commitments(ci: ComputeInputs) -> list[tuple[Commitment, str, datetime | None, list[str]]]:
    """(commitment, source_id, time, recipients) for threads and notes."""
    out = []
    for x, p, t in ci.human():
        for c in p.commitments:
            when = ci.evidence_time(c.evidence) or p.ball.last_message_at
            out.append((c, x.source_id, when, [a for m in t.messages for a in (m.from_addr, *m.to, *m.cc)]))
    for x, n in ci.notes():
        when = datetime.combine(n.meeting_date, time(12, 0), tzinfo=ci.as_of.tzinfo) if n.meeting_date else None
        for c in n.action_items:
            out.append((c, x.source_id, when, list(n.attendees)))
    return out


def _delivery_options(c: Commitment, when: datetime | None, all_c) -> list[tuple]:
    """Hard filters only: a later delivery (fulfills_hint set) in another thread, to at least one of the same people."""
    out = []
    for other, sid, t2, recipients in all_c:
        if other is c or not other.fulfills_hint:
            continue
        if when and t2 and t2 < when:
            continue
        if c.to_whom and not ({a.lower() for a in c.to_whom} & {a.lower() for a in recipients}):
            continue
        out.append((other, sid))
    return out


def _fulfilled_elsewhere(ci: ComputeInputs, c: Commitment, when: datetime | None, all_c, linked: set[str] | None = None,
                         qid: str = "") -> tuple[bool, dict]:
    """Same topic key → fulfilled (exact); otherwise the linker decided whether a later delivery is this promise."""
    target = ci.canon(c.about)
    for other, sid in _delivery_options(c, when, all_c):
        if ci.canon(other.about) == target or (linked and f"{qid}|{sid}" in linked):
            return True, {"fulfilled_by": sid, "fulfills_hint": other.fulfills_hint}
    return False, {}


def commitments(ci: ComputeInputs) -> list[Candidate]:
    out = []
    all_c = _all_commitments(ci)
    task_abouts = {ci.canon(tl.about) for tl in ci.task_links().values()}
    open_tasks = [t for t in ci.world.tasks if t.status == "open"]
    todos = [c for x, n in ci.notes() if n.note_kind == "todo" for c in n.action_items]
    todo_abouts = {ci.canon(c.about) for c in todos}
    mine = [(i, c, sid, when) for i, (c, sid, when, _) in enumerate(all_c) if c.owner == "avery" and c.status_in_thread == "open"]
    # one linker call: is a later delivery in another thread this promise?
    from .linker import LinkOption, LinkQuestion
    q_ful = [LinkQuestion(id=f"p{i}", item=f"{c.what} (to {', '.join(c.to_whom) or 'unknown'})",
                          options=[LinkOption(id=s, text=o.fulfills_hint or o.what) for o, s in _delivery_options(c, when, all_c)
                                   if ci.canon(o.about) != ci.canon(c.about)])
             for i, c, sid, when in mine]
    ful = ci.link("fulfilled_elsewhere", q_ful)
    linked = {f"{q}|{s}" for q, ss in ful.items() for s in ss}
    # one linker call: is this promise already on the task list or todo note?
    task_opts = [LinkOption(id=f"task:{t.task_id}", text=t.title) for t in open_tasks] + \
                [LinkOption(id=f"todo:{n}", text=c.what) for n, c in enumerate(todos)]
    q_tasks = [LinkQuestion(id=f"p{i}", item=f"{c.what} (to {', '.join(c.to_whom) or 'unknown'})", options=task_opts)
               for i, c, sid, when in mine if ci.canon(c.about) not in task_abouts and ci.canon(c.about) not in todo_abouts]
    in_tasks_q = {q for q, ss in ci.link("promise_in_tasks", q_tasks).items() if ss}
    for i, c, sid, when in mine:
        done, how = _fulfilled_elsewhere(ci, c, when, all_c, linked, f"p{i}")
        if done:
            continue
        about = ci.canon(c.about)
        who = [ci.slug(e) or "" for e in c.to_whom]
        thread = ci.threads.get(sid)
        counterpart = next((ci.contact(e) for e in c.to_whom if ci.contact(e)), None)
        base = {"what": c.what, "made_at": when.isoformat() if when else None, "source": sid, "to": c.to_whom,
                "due_raw": c.due.raw if c.due else None, "due": c.due.resolved.isoformat() if c.due and c.due.resolved else None,
                "due_granularity": c.due.granularity if c.due else None, **_contact_facts(counterpart)}
        if thread:
            base["thread_id"] = thread.thread_id
            base["subject"] = thread.messages[0].subject
        due = c.due.resolved if c.due else None
        bucket = due_bucket(due, ci.as_of)
        if bucket == "overdue":
            out.append(_mk("commitment_overdue", about, who, {**base, "days_overdue": days_overdue(due, ci.as_of)}, [c.evidence]))
        elif bucket == "today":
            out.append(_mk("commitment_due", about, who, {**base, "due_today": True}, [c.evidence]))
        in_tasks = about in task_abouts or about in todo_abouts or f"p{i}" in in_tasks_q
        # the profile's target is "I'll send that by Friday" hiding in a thread: a dated promise, or any promise to
        # someone outside the team. Undated soft promises to teammates ("will circle back") are not tracked here.
        external = counterpart is None or counterpart.relationship.category not in ("team", "unresolved")
        if not in_tasks and (due is not None or external):
            out.append(_mk("commitment_not_in_tasks", about, who, {**base, "in_tasks": False}, [c.evidence]))
    return out


# ----------------------------------------------------------------------------- calendar rules
def _work_days_ahead(ci: ComputeInputs, n: int) -> set:
    days = set()
    d = ci.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.add(d)
        d += timedelta(days=1)
    return days


def _calendar_unreadable(ci: ComputeInputs) -> bool:
    f = ci.world.freshness.get("calendar")
    return f is not None and f.state in ("unreadable", "missing")


def deep_work_conflicts(ci: ComputeInputs) -> list[Candidate]:
    out = []
    if _calendar_unreadable(ci):
        return out  # eval.md §5 corrupt_ics: no overlap claims against a calendar we could not read
    days = _work_days_ahead(ci, 2)   # today (if a business day) and the next business day
    days.add(ci.today())
    for e in ci.world.events:
        if e.organizer_is_avery or e.avery_partstat == "DECLINED" or e.start.date() not in days or e.domain != "work":
            continue
        for ws, we in block_windows(ci.profile.blocks, e.start.date(), ci.as_of.tzinfo):
            ov = overlap_minutes(e.start, e.end, ws, we)
            if ov <= 0:
                continue
            org = ci.contact(e.organizer)
            out.append(_mk("calendar_conflict:deep_work", f"meeting:{slugify(e.title)}",
                           [org.contact_id if org else slugify(e.organizer.split('@')[0]), slugify(org.org) if org and org.org else ""],
                           {"uid": e.uid, "title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat(),
                            "block": f"{ws.strftime('%a %H:%M')}-{we.strftime('%H:%M')}", "overlap_minutes": ov,
                            "organizer": e.organizer, "avery_partstat": e.avery_partstat, "description": e.description,
                            "today": e.start.date() == ci.today(), **_contact_facts(org)}, [ci.event_evidence(e)]))
    return out


def _personal_slots(ci: ComputeInputs) -> list[tuple[datetime, datetime, str, list[Evidence], dict]]:
    """Personal-domain events plus personal-thread schedule mentions that have no matching calendar event."""
    slots = []
    for e in ci.world.events:
        if e.domain == "personal":
            slots.append((e.start, e.end, e.title, [ci.event_evidence(e)],
                          {"uid": e.uid, "calendar": e.calendar, "created": e.created.isoformat() if e.created else None,
                           "organizer": e.organizer, "location": e.location}))
    for x, p, t in ci.human():
        if p.domain != "personal":
            continue
        for sm in p.schedule_mentions:
            if sm.action == "cancelled" or not sm.when or not sm.when.resolved:
                continue
            start = sm.when.resolved
            if any(abs((s[0] - start).total_seconds()) < 3600 for s in slots):
                for s in slots:   # attach the email evidence to the matching calendar slot
                    if abs((s[0] - start).total_seconds()) < 3600:
                        s[3].append(sm.evidence)
                        s[4].setdefault("email_source", x.source_id)
                continue
            slots.append((start, start + timedelta(hours=1), sm.meeting_desc, [sm.evidence],
                          {"thread_id": t.thread_id, "from_email": True, "sender": t.messages[-1].from_addr}))
    return slots


def family_conflicts(ci: ComputeInputs) -> list[Candidate]:
    out = []
    horizon = ci.today() + timedelta(days=ci.thresholds.family_lookahead_days)
    work = [e for e in ci.world.events if e.domain == "work" and e.avery_partstat in ("ACCEPTED", "ORGANIZER")]
    for start, end, title, evidence, meta in _personal_slots(ci):
        if not (ci.today() <= start.date() <= horizon):
            continue
        overlaps = []
        for e in work:
            ov = overlap_minutes(start, end, e.start, e.end)
            if ov > 0:
                overlaps.append({"uid": e.uid, "title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat(),
                                 "overlap_minutes": ov, "organizer_is_avery": e.organizer_is_avery})
                evidence = evidence + [ci.event_evidence(e)]
        during = start.weekday() < 5 and WORK_HOURS[0] <= start.time() < WORK_HOURS[1]
        if not overlaps and not during:
            continue
        sender = ci.contact(meta.get("organizer") or meta.get("sender"))
        if _calendar_unreadable(ci):
            meta = {**meta, "work_calendar": "unreadable: overlaps with work meetings were not checked"}
        out.append(_mk("calendar_conflict:family", f"family:{slugify(title)}",
                       [sender.contact_id if sender else "", "wren" if "wren" in fold(title) else ""],
                       {"title": title, "start": start.isoformat(), "end": end.isoformat(), "overlaps": overlaps,
                        "overlaps_work_event": bool(overlaps), "during_work_hours": during, "day": "today" if start.date() == ci.today() else start.strftime("%a"),
                        **meta, **_contact_facts(sender)}, evidence))
    return out


def double_book(ci: ComputeInputs) -> list[Candidate]:
    out = []
    if _calendar_unreadable(ci):
        return out
    owner = ci.world.owner_emails
    todays = [e for e in ci.world.events if e.domain == "work" and e.start.date() == ci.today()
              and e.avery_partstat in ("ACCEPTED", "ORGANIZER") and any(a.email not in owner for a in e.attendees)]
    for i, a in enumerate(todays):
        for b in todays[i + 1:]:
            ov = overlap_minutes(a.start, a.end, b.start, b.end)
            if ov > 0:
                out.append(_mk("calendar_conflict:double_book", f"meeting:{slugify(a.title)}", [],
                               {"events": [{"uid": x.uid, "title": x.title, "start": x.start.isoformat(), "end": x.end.isoformat()} for x in (a, b)],
                                "overlap_minutes": ov}, [ci.event_evidence(a), ci.event_evidence(b)]))
    return out


def declined_meetings(ci: ComputeInputs) -> list[Candidate]:
    """A meeting Avery declined, followed by a decision, agreement or ask that came out of it. Code keeps only things
    dated after the meeting (notes on or after its day; asks from its attendees or on the same topic key); the linker
    decides which of those actually came out of that meeting."""
    from .linker import LinkOption, LinkQuestion

    since = ci.as_of - timedelta(days=ci.thresholds.declined_lookback_days)
    declined = [e for e in ci.world.events if e.avery_partstat == "DECLINED" and since <= e.start <= ci.as_of]
    per_event: dict[str, list[tuple[str, str, Evidence]]] = {}
    for e in declined:
        attendees = {a.email for a in e.attendees}
        key = f"meeting:{slugify(e.title)}"
        opts: list[tuple[str, str, Evidence]] = []
        for _x, n in ci.notes():
            when = n.meeting_date
            if when and datetime.combine(when, time(0), tzinfo=ci.as_of.tzinfo) < e.start:
                continue
            opts += [("decision", d.what, d.evidence) for d in n.decisions]
            opts += [("agreement", a.rule, a.evidence) for a in n.agreements]
        for _x, p, t in ci.human():
            if p.ball.last_message_at < e.start:
                continue
            parts = {m.from_addr for m in t.messages}
            if attendees & parts or any(ci.canon(k) == key for k in p.about):
                opts += [("ask", a.what, a.evidence) for a in p.asks if a.to_avery]
        per_event[e.uid] = opts
    q = [LinkQuestion(id=e.uid, item=f"declined meeting: {e.title} · {e.start.strftime('%a %d %b %H:%M')}",
                      options=[LinkOption(id=f"r{n}", text=f"{k}: {w}") for n, (k, w, _ev) in enumerate(per_event[e.uid])])
         for e in declined]
    links = ci.link("declined_meeting_fallout", q)
    out = []
    for e in declined:
        refs = [per_event[e.uid][int(r[1:])] for r in links.get(e.uid, [])]
        if refs:
            attendees = {a.email for a in e.attendees}
            out.append(_mk("declined_meeting", f"meeting:{slugify(e.title)}", [ci.slug(a) or "" for a in attendees if a not in ci.world.owner_emails],
                           {"uid": e.uid, "title": e.title, "start": e.start.isoformat(),
                            "later_references": [{"kind": k, "what": w} for k, w, _ in refs[:4]]},
                           [ci.event_evidence(e)] + [ev for _, _, ev in refs[:3]]))
    return out


# ----------------------------------------------------------------------------- contradictions and drift
def contradictions(ci: ComputeInputs) -> list[Candidate]:
    out = []
    # (a) schedule mention vs calendar. Code narrows to events with the same people within ±7 days (one occurrence per
    # uid); the linker decides which of those, if any, is the meeting the email talks about.
    from .linker import LinkOption, LinkQuestion
    pending: list[tuple] = []
    for _x, p, t in ci.human():
        parts = {m.from_addr for m in t.messages} | {a for m in t.messages for a in m.to + m.cc}
        for sm in p.schedule_mentions:
            if sm.action not in ("moved", "confirmed") or not sm.when or not sm.when.resolved:
                continue
            ref = sm.previous_when.resolved if sm.previous_when and sm.previous_when.resolved else sm.when.resolved
            nearest: dict[str, tuple[float, object]] = {}
            for e in ci.world.events:
                att = {a.email for a in e.attendees} | {e.organizer}
                if not (att & parts - ci.world.owner_emails):
                    continue
                d = abs((e.start - ref).total_seconds())
                if d <= 7 * 86400 and (e.uid not in nearest or d < nearest[e.uid][0]):
                    nearest[e.uid] = (d, e)
            if nearest:
                pending.append((p, t, parts, sm, nearest))
    q_sched = [LinkQuestion(id=f"m{n}", item=f"email ({sm.action}): {sm.meeting_desc}; now {sm.when.raw}"
                            + (f"; previously {sm.previous_when.raw}" if sm.previous_when else ""),
                            options=[LinkOption(id=uid, text=f"{e.title} · {e.start.strftime('%a %d %b %H:%M')}") for uid, (_d, e) in nearest.items()])
               for n, (p, t, parts, sm, nearest) in enumerate(pending)]
    sched = ci.link("email_meeting_to_event", q_sched)
    for n, (p, t, parts, sm, nearest) in enumerate(pending):
        for uid in sched.get(f"m{n}", []):
            d, e = nearest[uid]
            att = {a.email for a in e.attendees} | {e.organizer}
            delta = abs((e.start - sm.when.resolved).total_seconds())
            same_day = e.start.date() == sm.when.resolved.date()
            if (sm.when.granularity == "day" and same_day) or delta <= 1800:
                continue
            if sm.previous_when and sm.previous_when.resolved and abs((e.start - sm.previous_when.resolved).total_seconds()) > 86400 * 2:
                continue   # the calendar event is a different meeting
            out.append(_mk("contradiction", ci.canon(p.about[0]) if p.about else f"meeting:{slugify(e.title)}",
                           [ci.slug(a) or "" for a in (att & parts) - ci.world.owner_emails],
                           {"kind": "schedule", "email_says": sm.when.resolved.isoformat(), "email_raw": sm.when.raw,
                            "email_action": sm.action, "calendar_says": e.start.isoformat(), "event_uid": e.uid,
                            "event_title": e.title, "meeting_desc": sm.meeting_desc, "thread_id": t.thread_id,
                            "email_day": day_label(sm.when.resolved.date(), ci.today()),
                            "calendar_day": day_label(e.start.date(), ci.today()),
                            "extra_dependencies": ["calendar"]},
                           [sm.evidence, ci.event_evidence(e)]))
    # (b) task open while email/notes show it done
    fulfilled = [(c, sid) for c, sid, _, _ in _all_commitments(ci) if c.status_in_thread == "fulfilled" or c.fulfills_hint]
    links = ci.task_links()
    open_tasks = [t for t in ci.world.tasks if t.status == "open"]
    q_done = [LinkQuestion(id=f"task:{task.task_id}", item=task.title,
                           options=[LinkOption(id=f"f{n}", text=c.fulfills_hint or c.what) for n, (c, _s) in enumerate(fulfilled)])
              for task in open_tasks]
    done_links = ci.link("task_done_in_email", q_done)
    for task in open_tasks:
        tl = links.get(f"task:{task.task_id}")
        for n, (c, sid) in enumerate(fulfilled):
            same = (tl and ci.canon(tl.about) == ci.canon(c.about)) or f"f{n}" in done_links.get(f"task:{task.task_id}", [])
            if same:
                out.append(_mk("contradiction", ci.canon(tl.about) if tl else f"other:{slugify(task.title)}", [],
                               {"kind": "task_vs_email", "task": task.title, "task_id": task.task_id, "shown_done_in": sid,
                                "what": c.what}, [Evidence(source_id=f"task:{task.task_id}", quote=task.title), c.evidence]))
                break
    # (c) conflicting data claims; (d) profile vs data drift
    for f in ci.facts:
        key = f"other:profile-drift:{slugify(f.subject)}" if f.drift else f"other:{slugify(f.subject)}:conflict"
        touches_profile = f.profile_value is not None
        touches_draft = any(getattr(c, "note_kind", None) == "draft" for c in (f.conflicting_data or []))
        if f.conflicting_data and (touches_profile or touches_draft):
            out.append(_mk("contradiction", key, [], {
                "kind": "claims", "subject": f.subject,
                "values": [{"value": c.value, "source": c.source_id, "note_kind": c.note_kind} for c in f.conflicting_data],
                "profile_value": f.profile_value, "effective": f.effective}, [c.evidence for c in f.conflicting_data]))
        if f.drift:
            out.append(_mk("contradiction", key, [], {"kind": "profile_vs_data", "subject": f.subject, "profile_value": f.profile_value,
                                                      "data_value": f.data_value}, f.evidence))
    return out


def profile_drift(ci: ComputeInputs) -> list[Candidate]:
    out = []
    for f in ci.facts:
        if f.drift:
            out.append(_mk("profile_drift", f"other:profile-drift:{slugify(f.subject)}", [], {
                "field": f.subject, "profile_value": f.profile_value, "data_value": f.data_value,
                "proposal": f"profile.md says {f.subject} = {f.profile_value}; data says {f.data_value}"}, f.evidence))
    for c in ci.directory.contacts:
        for d in c.drift:
            if d.profile_value is None and c.relationship.source != "inferred":
                continue
            out.append(_mk("profile_drift", f"other:profile-drift:{c.contact_id}", [c.contact_id], {
                "field": f"{c.contact_id}.{d.field}", "profile_value": d.profile_value, "data_value": d.data_value,
                "proposal": f"{c.names[0] if c.names else c.contact_id}: {d.data_value}"}, d.evidence))
    return out


# ----------------------------------------------------------------------------- hiring, recruiters, customers
def hiring_stalls(ci: ComputeInputs) -> list[Candidate]:
    out = []
    latest: dict[str, tuple] = {}
    paused_words: set[str] = set()
    for x in ci.extractions:
        p = x.payload
        for s in getattr(p, "stage_signals", []) or []:
            k = slugify(s.entity.name)
            if s.entity.kind == "candidate" or s.stage in ("sourced", "screen", "onsite", "debrief", "offer_extended", "offer_signed", "rejected", "withdrawn"):
                cur = latest.get(k)
                if cur is None or s.at > cur[0]:
                    latest[k] = (s.at, s, x.source_id, [ci.canon(a) for a in (getattr(p, "about", []) or [])])
            if s.stage in ("paused", "closed"):
                paused_words.update(w for w in k.split("-") if len(w) > 3)
    for k, (at, s, sid, abouts) in latest.items():
        if s.stage not in ("screen", "onsite", "debrief", "offer_extended"):
            continue
        d = days_since(at, ci.as_of)
        if d < ci.thresholds.hiring_stall_days:
            continue
        words = set(k.split("-")) | {w for a in abouts for w in a.replace(":", "-").split("-")} | set(fold(s.evidence.quote).split())
        if paused_words & words:
            continue
        out.append(_mk("hiring_stall", f"candidate:{k}", [k], {"candidate": s.entity.name, "stage": s.stage, "since": at.isoformat(),
                                                            "days_since_signal": int(d), "threshold": ci.thresholds.hiring_stall_days,
                                                            "source": sid}, [s.evidence]))
    return out


def recruiter_patterns(ci: ComputeInputs) -> list[Candidate]:
    out = []
    by_domain: dict[str, list[tuple[datetime, Evidence, str]]] = {}
    for _x, p, t in ci.human():
        for m in t.messages:
            if m.is_from_avery or m.forwarded_by:
                continue
            c = ci.contact(m.from_addr)
            if c is None or c.relationship.category != "cold_inbound":
                continue
            sub = fold(c.relationship.subtype or "")
            hinted = any(w in sub for w in RECRUITER_WORDS) or any(so.subtype_hint and any(w in fold(so.subtype_hint) for w in RECRUITER_WORDS) for so in p.sender_observations)
            if not hinted:
                continue
            dom = m.from_addr.split("@")[-1]
            by_domain.setdefault(dom, []).append((m.sent_at, Evidence(source_id=f"msg:{m.message_id}", quote=" ".join(m.subject.split()[:20]) or "recruiter"), c.contact_id))
    for dom, items in by_domain.items():
        w = recruiter_window([t for t, _, _ in items], ci.as_of, ci.thresholds.recruiter_count, ci.thresholds.recruiter_window_days)
        if not w:
            continue
        start, end, n = w
        org = next((c.org for _, _, cid in items if (c := ci.directory.by_slug.get(cid)) and c.org), dom.split(".")[0])
        out.append(_mk("recruiter_pattern", f"other:recruiter-pattern:{slugify(org)}", [cid for _, _, cid in items],
                       {"org": org, "domain": dom, "count": n, "window_start": start.isoformat(), "window_end": end.isoformat(),
                        "senders": sorted({cid for _, _, cid in items})}, [e for _, e, _ in items[:3]]))
    return out


def cadence_drops(ci: ComputeInputs) -> list[Candidate]:
    out = []
    th = ci.thresholds
    merged_into: dict[str, str] = {}
    for rc, _ in ci.directory.role_changes:
        succ, pred = ci.contact(rc.person), ci.contact(rc.replaces, rc.replaces) if rc.replaces else None
        if succ and pred:
            merged_into[pred.contact_id] = succ.contact_id
    inbound: dict[str, list[datetime]] = {}
    for c in ci.directory.contacts:
        if c.relationship.category != "customer":
            continue
        if not (c.relationship.subtype in ("reference", "active") or c.relationship.stage in ("active", "renewal_window", "at_risk") or "same_day_reply" in c.profile_rules):
            continue
        times = [m.sent_at for t in ci.world.threads if t.router_type in ("human", "unsure") for m in t.messages if m.from_addr in c.emails]
        target = merged_into.get(c.contact_id, c.contact_id)
        inbound.setdefault(target, []).extend(times)
    for cid, times in inbound.items():
        st = cadence_stats(times, ci.as_of, th.cadence_baseline, th.cadence_recent, th.behavior_window_days)
        if st is None or st.ratio is None:
            continue
        if st.ratio >= th.cadence_ratio and st.current_gap_days >= th.cadence_min_gap_days:
            c = ci.directory.by_slug[cid]
            last = max(times)
            src = next((f"msg:{m.message_id}" for t in ci.world.threads for m in t.messages if m.sent_at == last), None)
            ev = [Evidence(source_id=src, quote=" ".join(next(m.subject for t in ci.world.threads for m in t.messages if m.sent_at == last).split()[:20]) or "last inbound")] if src else []
            out.append(_mk("cadence_drop", f"other:cadence:{slugify(c.org or cid)}", [cid, slugify(c.org) if c.org else ""], {
                "contact": cid, "org": c.org, "baseline_median_days": st.baseline_median_days, "recent_median_days": st.recent_median_days,
                "current_gap_days": st.current_gap_days, "ratio": st.ratio, "recent_used_current_gap": st.recent_used_current_gap,
                "merged_predecessors": [p for p, s in merged_into.items() if s == cid], **_contact_facts(c)}, ev))
    return out


# ----------------------------------------------------------------------------- approvals, obligations, tasks
def approvals(ci: ComputeInputs) -> list[Candidate]:
    out = []
    for x in ci.extractions:
        if x.type == "automated" and isinstance(x.payload, Automated) and x.payload.action_bearing:
            a = x.payload
            if a.action_kind == "security" and slugify(a.system) in ("github", "dependabot", "ci", "github-actions", "snyk"):
                continue  # engineering owns dev-tool security alerts (data_generation §6: DocuSign action vs GitHub FYI)
            t = ci.threads.get(x.source_id)
            when = t.messages[-1].sent_at if t else None
            about = ci.canon(a.about) if a.about else f"approval:{slugify(a.system)}"
            out.append(_mk("approval_pending", about, [], {
                "system": a.system, "what": a.what, "action_kind": a.action_kind, "link_present": a.link_present,
                "deadline": a.deadline.resolved.isoformat() if a.deadline and a.deadline.resolved else None,
                "received_at": when.isoformat() if when else None, "hours_waiting": hours_since(when, ci.as_of) if when else None,
                "thread_id": x.source_id}, [a.evidence]))
    for _x, p, t in ci.human():
        for a in p.asks:
            if a.to_avery and a.status == "open" and a.kind in ("approval", "signature"):
                sender = ci.contact(a.from_email)
                out.append(_mk("approval_pending", ci.canon(p.about[0]) if p.about else f"approval:{slugify(t.messages[0].subject)}",
                               [sender.contact_id if sender else ""], {"what": a.what, "kind": a.kind, "from": a.from_email,
                                "deadline": a.deadline.resolved.isoformat() if a.deadline and a.deadline.resolved else None,
                                "thread_id": t.thread_id, **_contact_facts(sender)}, [a.evidence]))
    return out


def obligations(ci: ComputeInputs) -> list[Candidate]:
    out = []
    cadence_fact = next((f for f in ci.facts if f.subject == "board_update_cadence"), None)
    agreements = [(a, x.source_id, n) for x, n in ci.notes() for a in n.agreements if a.cadence]
    if cadence_fact is None and not agreements:
        return out
    cadence = (cadence_fact.effective if cadence_fact else None) or (agreements[0][0].cadence if agreements else None)
    days = cadence_days(cadence)
    if not days:
        return out
    fulfilled = [(c, sid, when) for c, sid, when, _ in _all_commitments(ci)
                 if (c.status_in_thread == "fulfilled" or c.fulfills_hint) and ci.canon(c.about).startswith(("board-update", "report:board"))]
    last = max((w for _, _, w in fulfilled if w), default=None)
    open_items = [c for c, _, _, _ in _all_commitments(ci) if c.owner == "avery" and c.status_in_thread == "open" and ci.canon(c.about).startswith("board-update")]
    open_tasks = [t for t in ci.world.tasks if t.status == "open" and "board" in fold(t.title)]
    if last is not None:
        since = days_since(last, ci.as_of)
        if since <= days:
            return out
    elif not open_items and not open_tasks:
        return out
    ev = [a.evidence for a, _, _ in agreements[:2]] + ([fulfilled[-1][0].evidence] if fulfilled else []) \
        + [Evidence(source_id=f"task:{t.task_id}", quote=t.title) for t in open_tasks[:1]] + [c.evidence for c in open_items[:1]]
    out.append(_mk("obligation_cadence", "board-update:cadence", [], {
        "cadence": cadence, "cadence_days": days, "cadence_source": "data (drift)" if cadence_fact and cadence_fact.drift else ("data" if agreements else "profile"),
        "profile_cadence": cadence_fact.profile_value if cadence_fact else None,
        "last_fulfillment": last.isoformat() if last else None, "days_since_last": int(days_since(last, ci.as_of)) if last else None,
        "open_board_update_task": [t.title for t in open_tasks], "rule": agreements[0][0].rule if agreements else None}, ev))
    return out


def tasks_due(ci: ComputeInputs) -> list[Candidate]:
    out = []
    links = ci.task_links()
    for t in ci.world.tasks:
        if t.status != "open" or t.due is None or t.due > ci.today():
            continue
        tl = links.get(f"task:{t.task_id}")
        about = ci.canon(tl.about) if tl else f"other:{slugify(t.title)}"
        ents = [ci.slug(e.contact_hint, e.name) or slugify(e.name) for e in tl.entities] if tl else []
        out.append(_mk("task_due", about, ents, {"task_id": t.task_id, "title": t.title, "due": t.due.isoformat(),
                                                 "days_overdue": (ci.today() - t.due).days, "due_today": t.due == ci.today(),
                                                 "tasks_file_age_days": days_since(t.file_last_modified, ci.as_of) if t.file_last_modified else None},
                       [Evidence(source_id=f"task:{t.task_id}", quote=" ".join(t.title.split()[:20]))]))
    return out


# ----------------------------------------------------------------------------- news, staleness, injection
def active_entities(ci: ComputeInputs, cands: list[Candidate]) -> tuple[set[str], set[str]]:
    ents: set[str] = set()
    topics: set[str] = set()
    for c in cands:
        ents.update(e for e in c.entities if e)
        topics.update(w for w in c.about.split(":")[1:] for w in w.split("-") if len(w) > 3)
    for e in ci.world.events:
        if e.start.date() == ci.today():
            ents.add(slugify(e.title))
            for a in e.attendees:
                if a.email not in ci.world.owner_emails:
                    s = ci.slug(a.email, a.name)
                    if s:
                        ents.add(s)
                    ents.add(slugify(a.name or a.email.split("@")[0]))
    recent = ci.as_of - timedelta(days=7)
    for _x, p, t in ci.human():
        if t.messages[-1].sent_at >= recent:
            for m in t.messages:
                c = ci.contact(m.from_addr)
                if c:
                    ents.add(c.contact_id)
                    if c.org:
                        ents.add(slugify(c.org))
            for k in p.about:
                topics.update(w for w in ci.canon(k).split(":")[1:] for w in w.split("-") if len(w) > 3)
            for cl in p.claims:
                topics.update(w for w in fold(cl.subject).split() if len(w) > 3)
    for _x, n in ci.notes():
        if n.meeting_date and (ci.today() - n.meeting_date).days <= 7:
            for k in n.about:
                topics.update(w for w in ci.canon(k).split(":")[1:] for w in w.split("-") if len(w) > 3)
            for cl in n.claims:
                topics.update(w for w in fold(cl.subject).split() if len(w) > 3)
            for a in n.attendees:
                s = ci.slug(None, a)
                if s:
                    ents.add(s)
    for c in ci.directory.contacts:
        if c.org and c.contact_id in ents:
            ents.add(slugify(c.org))
    return ents, topics


_NEWS_STOP = {"tessera", "avery", "avery-chen", "series-a", "series", "board", "raise", "fundraising", "investors", "team",
              "startup", "startups", "founders", "saas"}


def active_about_slugs(ci: ComputeInputs, cands: list[Candidate]) -> set[str]:
    """Slugs (the part after the kind) of the about keys that are active today: candidates, threads with activity in the
    last 7 days, notes from the last 7 days. Newsletter topics attach only to these, never to single words."""
    slugs: set[str] = set()
    for c in cands:
        slugs.add("-".join(c.about.split(":")[1:]))
    recent = ci.as_of - timedelta(days=7)
    for _x, p, t in ci.human():
        if t.messages[-1].sent_at >= recent:
            for k in p.about:
                slugs.add("-".join(ci.canon(k).split(":")[1:]))
    for _x, n in ci.notes():
        if n.meeting_date and (ci.today() - n.meeting_date).days <= 7:
            for k in n.about:
                slugs.add("-".join(ci.canon(k).split(":")[1:]))
    return {s for s in slugs if s and s not in _NEWS_STOP}


def news_attachments(ci: ComputeInputs, cands: list[Candidate]) -> list[Candidate]:
    """architecture §6.4: a newsletter item becomes a candidate only if it changes something Avery is dealing with.
    Code lists the open items (today's candidates); the linker decides which, if any, a story attaches to."""
    from .linker import LinkOption, LinkQuestion

    active: dict[str, str] = {}
    for c in cands:
        if c.type in ("news_attachment", "stale_source", "profile_drift", "recruiter_pattern"):
            continue
        f = c.facts
        desc = f.get("summary") or f.get("subject") or f.get("title") or f.get("what") or ""
        active.setdefault(c.about, f"{c.type} on {c.about}: {desc}"[:220])
    options = [LinkOption(id=k, text=v) for k, v in list(active.items())[:80]]
    stories = []
    for x in ci.extractions:
        if x.type != "newsletter" or not isinstance(x.payload, Newsletter):
            continue
        for n, item in enumerate(x.payload.items):
            stories.append((f"{x.source_id}#{n}", x, item))
    links = ci.link("news_to_open_item", [LinkQuestion(id=sid, item=f"{it.headline}: {it.summary}", options=options)
                                          for sid, _x, it in stories])
    out = []
    for sid, x, item in stories:
        matched = links.get(sid, [])
        if not matched:
            continue
        nl = x.payload
        out.append(_mk("news_attachment", f"other:news:{_short_slug(item.headline)}", [], {
            "headline": item.headline, "summary": item.summary, "publication": nl.publication, "issue_date": nl.issue_date.isoformat(),
            "topics": item.topics, "entities": [e.name for e in item.entities], "attaches_to": matched,
            "attaches_to_what": [active[m] for m in matched],
            "effective_date": item.effective_date.resolved.isoformat() if item.effective_date and item.effective_date.resolved else None,
            "thread_id": x.source_id}, [item.evidence]))
    return out


def _short_slug(text: str, max_len: int = 40) -> str:
    words = slugify(text, 120).split("-")
    out = ""
    for w in words:
        if len(out) + len(w) + 1 > max_len:
            break
        out = f"{out}-{w}" if out else w
    return out or "item"


def stale_sources(ci: ComputeInputs) -> list[Candidate]:
    out = []
    for kind, f in ci.world.freshness.items():
        if f.state == "ok":
            continue
        ev: list[Evidence] = []
        if kind == "email":
            last = max(ci.world.messages, key=lambda m: m.sent_at, default=None)
            if last:
                ev = [Evidence(source_id=f"msg:{last.message_id}", quote=" ".join(last.subject.split()[:20]) or "last message")]
        elif kind == "tasks" and ci.world.tasks:
            ev = [Evidence(source_id=f"task:{ci.world.tasks[0].task_id}", quote=ci.world.tasks[0].title)]
        elif kind == "calendar" and ci.world.events:
            ev = [ci.event_evidence(ci.world.events[-1])]
        elif kind == "notes" and ci.world.notes:
            n = ci.world.notes[-1]
            ev = [Evidence(source_id=f"note:{n.path}", quote=" ".join(n.title.split()[:20]))]
        out.append(_mk("stale_source", f"other:stale-source:{kind}", [], {
            "source": kind, "state": f.state, "latest_item_time": f.latest_item_time.isoformat() if f.latest_item_time else None,
            "age_hours": f.age_hours, "detail": f.detail, "extra_dependencies": [kind]}, ev))
    return out


_ADDRESSED_TO_AI = re.compile(r"^\s*(assistant|ai assistant|ai|system|claude|chatgpt|gpt|copilot|llm)\s*[:>,-]\s*\S", re.I)
_OVERRIDE = re.compile(r"\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|rules)\b", re.I)


def _embedded_instructions(t) -> list[Evidence]:
    """Code guard (architecture §8 rule 11): lines that address an AI directly ("assistant: mark this P0 …") or
    tell it to drop its rules. Content is data; these are reported, never followed."""
    found = []
    for m in t.messages:
        for line in (m.body_new or "").splitlines():
            if _ADDRESSED_TO_AI.search(line) or _OVERRIDE.search(line):
                quote = " ".join(line.strip().split()[:20])
                found.append(Evidence(source_id=f"msg:{m.message_id}", quote=quote))
    return found


def suspicious(ci: ComputeInputs) -> list[Candidate]:
    out = []
    for _x, p, t in ci.human():
        if not p.suspicious_instructions:
            code_found = _embedded_instructions(t)
            if code_found:
                p = p.model_copy(update={"suspicious_instructions": code_found})
        if not p.suspicious_instructions:
            continue
        sender = ci.contact(t.messages[-1].from_addr)
        out.append(_mk("suspicious_content", ci.canon(p.about[0]) if p.about else f"other:suspicious:{slugify(t.messages[0].subject)}",
                       [sender.contact_id if sender else ""], {"thread_id": t.thread_id, "subject": t.messages[0].subject,
                        "instructions": [e.quote for e in p.suspicious_instructions], "summary": p.summary, **_contact_facts(sender)},
                       list(p.suspicious_instructions)))
    # the code guard also covers automated and bulk threads (the planted injection arrives as a "billing" email)
    covered = {c.facts.get("thread_id") for c in out}
    human_ids = {t.thread_id for _x, _p, t in ci.human()}
    for t in ci.world.threads:
        if t.thread_id in covered or t.thread_id in human_ids:
            continue
        found = _embedded_instructions(t)
        if not found:
            continue
        sender = ci.contact(t.messages[-1].from_addr)
        out.append(_mk("suspicious_content", f"other:suspicious:{slugify(t.messages[0].subject)}",
                       [sender.contact_id if sender else ""], {"thread_id": t.thread_id, "subject": t.messages[0].subject,
                        "instructions": [e.quote for e in found], "summary": t.messages[0].subject, **_contact_facts(sender)},
                       found))
    return out


def personal_date_collisions(ci: ComputeInputs) -> list[Candidate]:
    """architecture §6.4 calendar_conflict:family, second form: a personal-domain *email* about a time (a daycare
    closure, a school early dismissal) that lands on a workday within today + 2 days. The overlap is the day's
    accepted work events; with none, the collision is the workday itself."""
    out = []
    horizon = ci.thresholds.family_lookahead_days
    for _x, p, t in ci.human():
        if p.domain != "personal":
            continue
        mentions = []
        for cl in p.claims:
            if cl.as_of and cl.as_of.resolved:
                mentions.append((cl.subject, cl.value, cl.as_of.resolved, cl.evidence))
        for sm in p.schedule_mentions:
            if sm.when and sm.when.resolved and sm.action != "cancelled":
                mentions.append((sm.meeting_desc, sm.action, sm.when.resolved, sm.evidence))
        seen: set[str] = set()
        for subject, value, when, ev in mentions:
            d = when.date()
            if not (0 <= (d - ci.today()).days <= horizon) or d.weekday() >= 5:
                continue
            key = f"family:{slugify(subject)}"
            if key in seen:
                continue
            seen.add(key)
            todays = [e for e in ci.world.events if e.calendar == "work" and e.start.date() == d
                      and e.avery_partstat in ("ACCEPTED", "ORGANIZER")]
            unread = _calendar_unreadable(ci)
            sender = ci.contact(t.messages[-1].from_addr)
            out.append(_mk("calendar_conflict:family", key, [sender.contact_id if sender else ""], {
                "title": subject, "value": value, "start": when.isoformat(), "all_day": True, "source_kind": "email",
                "day": "today" if d == ci.today() else d.strftime("%a"),
                "overlaps": [{"uid": e.uid, "title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat()} for e in todays],
                "overlaps_work_event": bool(todays), "thread_id": t.thread_id, "summary": p.summary,
                **({"work_calendar": "unreadable: overlaps with work meetings were not checked"} if unread else {}),
                "extra_dependencies": ["calendar"], **_contact_facts(sender)}, [ev]))
    return out


GENERATORS: list[Callable[[ComputeInputs], list[Candidate]]] = [
    reply_owed, quiet_thread, commitments, deep_work_conflicts, family_conflicts, personal_date_collisions, double_book, declined_meetings,
    contradictions, hiring_stalls, recruiter_patterns, cadence_drops, approvals, obligations, tasks_due, stale_sources,
    suspicious, profile_drift,
]


def generate(ci: ComputeInputs) -> list[Candidate]:
    cands: list[Candidate] = []
    for g in GENERATORS:
        cands.extend(g(ci))
    cands.extend(news_attachments(ci, cands))
    return cands
