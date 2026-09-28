"""Retrieval for readers (specs/PIVOT_SPEC.md §3.3), source dependencies and freshness caps (architecture §6.5).

`retrieve` chooses what a thread reader reads next to its thread: nearby events with the same people or org, notes and
tasks that mention them or the subject, and the previous two threads with the same people. Word overlap is allowed
here and only here: retrieval widens what is read, it decides nothing. `ContextIndex` is the v1 index over extractions,
kept while the v1 orchestration still calls it."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..normalize import NormalizedWorld
from ..schemas import (
    Candidate,
    Extraction,
    FreshnessCap,
    Model,
    NormalizedEvent,
    NormalizedMessage,
    NormalizedThread,
    SourceKind,
)
from ..util import domain_of, fold, org_from_domain, slugify


def source_kind(source_id: str) -> SourceKind | None:
    if source_id.startswith(("msg:", "thread:")):
        return "email"
    if source_id.startswith("event:"):
        return "calendar"
    if source_id.startswith("note:"):
        return "notes"
    if source_id.startswith("task:"):
        return "tasks"
    return None


class ContextIndex:
    """Extraction source_id → (entity slugs, about keys, time), for retrieval by shared entity within ±window days."""

    def __init__(self, world: NormalizedWorld, extractions: list[Extraction], as_of: datetime, window_days: int = 14,
                 max_items: int = 8, ignore: set[str] | None = None):
        self.as_of = as_of
        self.ignore = {s.lower() for s in (ignore or ())}
        self.window = timedelta(days=window_days)
        self.max_items = max_items
        self.items: list[tuple[str, set[str], set[str], datetime | None, str]] = []   # (source_id, entities, abouts, time, summary)
        thread_time = {t.thread_id: t.messages[-1].sent_at for t in world.threads}
        thread_parts = {t.thread_id: {m.from_addr for m in t.messages} | {a for m in t.messages for a in m.to + m.cc} for t in world.threads}
        note_dates = {f"note:{n.path}": (datetime.combine(n.header_date, datetime.min.time(), tzinfo=as_of.tzinfo) if n.header_date else n.mtime)
                      for n in world.notes}
        for x in extractions:
            p = x.payload
            if p is None:
                continue
            ents: set[str] = set()
            abouts: set[str] = set()
            summary = getattr(p, "summary", "") or getattr(p, "what", "") or ""
            for a in getattr(p, "about", []) or ([p.about] if getattr(p, "about", None) and isinstance(p.about, str) else []):
                abouts.add(a)
            for so in getattr(p, "sender_observations", []) or []:
                ents.add(so.email.lower())
                if so.name:
                    ents.add(slugify(so.name))
                if so.org:
                    ents.add(slugify(so.org))
            for e in getattr(p, "entities", []) or []:
                ents.add(slugify(e.name))
                if e.contact_hint:
                    ents.add(e.contact_hint.lower())
            for att in getattr(p, "attendees", []) or []:
                ents.add(slugify(att))
            for s in getattr(p, "stage_signals", []) or []:
                ents.add(slugify(s.entity.name))
            for c in getattr(p, "commitments", []) or getattr(p, "action_items", []) or []:
                ents.update(w.lower() for w in c.to_whom)
                abouts.add(c.about)
            for part in thread_parts.get(x.source_id, set()):
                ents.add(part)
            when = thread_time.get(x.source_id) or note_dates.get(x.source_id)
            self.items.append((x.source_id, ents, abouts, when, summary[:160]))
        self.events = [(f"event:{e.uid}", {a.email for a in e.attendees} | {slugify(e.title)}, e.start, e.title) for e in world.events]

    def related(self, entities: set[str], abouts: set[str], exclude: set[str]) -> list[str]:
        """Most relevant first: same topic key, then more shared people, then newer. Avery and Avery's own company are
        not a link (every internal thread shares them; they pushed a same-topic delivery out of a triage card)."""
        entities = {e for e in entities if e.lower() not in self.ignore}
        hits: list[tuple[tuple, str]] = []
        lo, hi = self.as_of - self.window, self.as_of + self.window
        for sid, ents, abts, when, _ in self.items:
            if sid in exclude:
                continue
            shared, topic = ents & entities, bool(abts & abouts)
            if (shared or topic) and (when is None or lo <= when <= hi):
                hits.append(((not topic, -len(shared), -(when or self.as_of).timestamp()), sid))
        for sid, ents, when, _ in self.events:
            if sid in exclude:
                continue
            shared = ents & entities
            if shared and lo <= when <= hi:
                hits.append(((True, -len(shared), -when.timestamp()), sid))
        hits.sort(key=lambda h: h[0])
        out: list[str] = []
        for _, sid in hits:
            if sid not in out:
                out.append(sid)
        return out[: self.max_items]

    def summary_of(self, source_id: str) -> str:
        for sid, _, _, _, s in self.items:
            if sid == source_id:
                return s
        for sid, _, _, title in self.events:
            if sid == source_id:
                return title
        return ""


def dependencies(c: Candidate) -> list[SourceKind]:
    kinds: list[SourceKind] = []
    for e in c.evidence:
        k = source_kind(e.source_id)
        if k and k not in kinds:
            kinds.append(k)
    for k in c.facts.get("extra_dependencies", []) or []:
        if k not in kinds:
            kinds.append(k)
    return kinds


def freshness_cap(kinds: list[SourceKind], freshness: dict) -> FreshnessCap:
    cap: FreshnessCap = "none"
    for k in kinds:
        f = freshness.get(k)
        if f is None:
            continue
        if f.state in ("missing", "unreadable"):
            return "missing"
        if f.state == "stale":
            cap = "stale"
    return cap


def apply_context(cands: list[Candidate], idx: ContextIndex, freshness: dict) -> None:
    """Fill context_refs, source_dependencies, freshness_cap; add the sync-gap qualifier (architecture §6.5)."""
    for c in cands:
        own = {e.source_id for e in c.evidence} | {c.facts.get("thread_id", "")}
        ents = set(c.entities) | set(c.facts.get("entity_keys", []))
        c.context_refs = idx.related(ents, {c.about}, own)
        c.source_dependencies = dependencies(c)
        c.freshness_cap = freshness_cap(c.source_dependencies, freshness)
        if c.freshness_cap != "none":
            stale = [k for k in c.source_dependencies if freshness.get(k) and freshness[k].state != "ok"]
            c.facts["freshness_note"] = f"{', '.join(stale)} {'stale' if c.freshness_cap == 'stale' else 'missing/unreadable'}: confidence capped at medium"
            if c.type in ("quiet_thread", "commitment_overdue", "reply_owed", "cadence_drop"):
                c.facts["qualifier"] = "may be a sync gap"


# ----------------------------------------------------------------------------- v2 retrieval
class ContextRef(Model):
    """One retrieved snippet. `text` is verbatim from the source (plus a one-line label), so a reader's quote from it
    can be checked: add (source_id, text) to the reader's SourceIndex."""
    source_id: str    # event:<uid> | note:<path> | task:<id> | msg:<id>
    text: str


EVENT_DAYS = 7
PREVIOUS_THREADS = 2
EXCERPT_CHARS = 300
NOTE_CHARS = 900
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{3,}")
_SUBJECT_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw)\s*:\s*)+", re.I)
# words that say nothing about what a thread is about; retrieval ignores them as keywords
STOP = frozenset({
    "about", "after", "again", "also", "back", "been", "before", "being", "call", "calls", "could", "date", "days",
    "does", "done", "draft", "email", "emails", "from", "have", "hello", "here", "just", "last", "later", "latest",
    "meeting", "meetings", "more", "next", "note", "notes", "please", "quick", "question", "questions", "reply",
    "same", "send", "sent", "some", "sync", "that", "thanks", "thank", "their", "them", "then", "there", "these",
    "they", "thing", "this", "those", "thursday", "today", "tomorrow", "tuesday", "wednesday", "monday", "friday",
    "saturday", "sunday", "update", "updates", "week", "weekly", "what", "when", "where", "which", "while", "will",
    "with", "would", "your", "yours", "follow", "following", "checking", "check", "touch", "base", "intro",
    "introduction", "team", "time", "works", "working"
})


def _words(text: str) -> set[str]:
    return {w.strip("'-") for w in _WORD.findall(fold(text))} - STOP


def _has(term: str, text: str) -> bool:
    return bool(term) and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _stamp(dt: datetime) -> str:
    return dt.strftime("%a %Y-%m-%d %H:%M")


def _excerpt(m: NormalizedMessage, label: str) -> ContextRef:
    who = f"{m.from_name} <{m.from_addr}>" if m.from_name else m.from_addr
    body = " ".join((m.body_new or "").split())[:EXCERPT_CHARS]
    return ContextRef(source_id=f"msg:{m.message_id}", text=f"{label} · {_stamp(m.sent_at)} · from {who} · subject: {m.subject}\n{body}")


def _event_text(e: NormalizedEvent, as_of: datetime) -> str:
    who = ", ".join(a.name or a.email for a in e.attendees[:8])
    return (f"{e.title} · {e.calendar} calendar · {_stamp(e.start)}–{e.end.strftime('%H:%M')} "
            f"({'past' if e.end < as_of else 'upcoming'}) · organizer {e.organizer} · Avery: {e.avery_partstat}"
            + (f" · attendees: {who}" if who else ""))


def retrieve(thread: NormalizedThread, world: NormalizedWorld, directory, as_of: datetime, cap_tokens: int = 4000) -> list[ContextRef]:
    """Context for one thread reader, most relevant first (same people > same org > subject keyword; newer first inside
    a rank), capped at about `cap_tokens` (4 characters a token)."""
    owner = world.owner_emails
    own_domains = {domain_of(e) for e in owner}
    own_words = {fold(org_from_domain(e) or "") for e in owner} | {fold(e.split("@")[0]) for e in owner}
    people = {a.lower() for m in thread.messages for a in (m.from_addr, *m.to, *m.cc) if a and a.lower() not in owner}
    domains = {domain_of(a) for a in people} - own_domains
    contacts = [c for a in people if (c := directory.lookup(a)) is not None] if directory is not None else []
    names: set[str] = set()
    orgs: set[str] = set()
    for c in contacts:
        for n in c.names[:2]:
            full = fold(n).strip()
            if " " in full:
                names.add(full)
            first = full.split(" ")[0]
            if len(first) >= 4:
                names.add(first)
        if c.org and fold(c.org) not in own_words:
            orgs.add(fold(c.org))
    for d in domains:
        o = fold(org_from_domain(f"x@{d}") or "")
        if len(o) >= 4 and o not in own_words:
            orgs.add(o)
    subjects = " ".join(_SUBJECT_PREFIX.sub("", m.subject or "") for m in thread.messages)
    keywords = _words(subjects) - own_words - {w for n in names for w in n.split()}
    ranked: list[tuple[tuple, ContextRef]] = []

    def rank_text(text: str) -> int | None:
        t = fold(text)
        if any(_has(n, t) for n in names):
            return 0
        if any(_has(o, t) for o in orgs):
            return 1
        if any(_has(k, t) for k in keywords):
            return 2
        return None

    # events in [as_of − 7d, as_of + 7d] sharing a participant or the org; one occurrence per uid, the nearest
    lo, hi = as_of - timedelta(days=EVENT_DAYS), as_of + timedelta(days=EVENT_DAYS)
    nearest: dict[str, NormalizedEvent] = {}
    for e in world.events:
        if lo <= e.start <= hi and (e.uid not in nearest or abs(e.start - as_of) < abs(nearest[e.uid].start - as_of)):
            nearest[e.uid] = e
    for e in nearest.values():
        att = {a.email.lower() for a in e.attendees} | {e.organizer.lower()}
        if att & people:
            r = 0
        elif {domain_of(a) for a in att} & domains or any(_has(o, fold(e.title)) for o in orgs):
            r = 1
        else:
            continue
        ranked.append(((r, abs((e.start - as_of).total_seconds()) / 86400), ContextRef(source_id=f"event:{e.uid}", text=_event_text(e, as_of))))
    # notes: the lines that mention a participant, the org or a subject word, with a line on each side
    for n in world.notes:
        lines = n.text.split("\n")
        best, hits = None, []
        for i, ln in enumerate(lines):
            r = rank_text(ln)
            if r is not None:
                best = r if best is None else min(best, r)
                hits.extend(j for j in (i - 1, i, i + 1) if 0 <= j < len(lines) and j not in hits)
        if best is None:
            continue
        when = n.header_date or (n.mtime.date() if n.mtime else None)
        body = "\n".join(f"L{j + 1}: {lines[j]}" for j in sorted(hits) if lines[j].strip())[:NOTE_CHARS]
        age = (as_of.date() - when).days if when else 10_000
        ranked.append(((best, age), ContextRef(source_id=f"note:{n.path}", text=f"note:{n.path} · {n.title} · dated {when or 'unknown'}\n{body}")))
    # tasks
    for t in world.tasks:
        r = rank_text(t.title)
        if r is not None:
            line = f"- [{'x' if t.status == 'done' else ' '}] {t.title}" + (f" (due: {t.due.isoformat()})" if t.due else "")
            ranked.append(((r, 0), ContextRef(source_id=f"task:{t.task_id}", text=line)))
    # the previous two threads with the same people: first and last message excerpts
    last = thread.messages[-1].sent_at
    prev: list[tuple[int, float, NormalizedThread]] = []
    for t in world.threads:
        if t.thread_id == thread.thread_id or t.router_type not in ("human", "unsure") or t.messages[0].sent_at >= last:
            continue
        theirs = {a.lower() for m in t.messages for a in (m.from_addr, *m.to, *m.cc) if a and a.lower() not in owner}
        shared = len(theirs & people)
        if shared:
            prev.append((shared, t.messages[-1].sent_at.timestamp(), t))
    prev.sort(key=lambda x: (-x[0], -x[1]))
    for _shared, ts, t in prev[:PREVIOUS_THREADS]:
        ms = [t.messages[0]] + ([t.messages[-1]] if len(t.messages) > 1 else [])
        for k, m in enumerate(ms):
            label = f"earlier thread ({len(t.messages)} messages), {'first' if k == 0 else 'last'} message"
            ranked.append(((0, (as_of.timestamp() - ts) / 86400 + k / 1000), _excerpt(m, label)))
    ranked.sort(key=lambda x: x[0])
    out: list[ContextRef] = []
    budget = cap_tokens * 4
    for _key, ref in ranked:
        if any(r.source_id == ref.source_id for r in out):
            continue
        if len(ref.text) > budget:   # the most relevant thing that no longer fits is cut to what is left
            if budget >= 200:
                out.append(ref.model_copy(update={"text": ref.text[:budget]}))
            break
        out.append(ref)
        budget -= len(ref.text)
    return out


__all__ = ["ContextIndex", "ContextRef", "apply_context", "dependencies", "freshness_cap", "retrieve", "source_kind"]


def _unused(_: date) -> None:  # keep `date` import for type hints in annotations
    return None
