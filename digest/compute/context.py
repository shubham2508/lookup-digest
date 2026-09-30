"""Retrieval for readers (specs/PIVOT_SPEC.md §3.3), source dependencies and freshness caps (architecture §6.5).

`retrieve` chooses what a thread reader reads next to its thread, from hard facts only (OPEN_QUESTIONS #26): calendar
events within a week that share a participant or an outside domain with the thread, the two other threads with the
same people (ranked by the rarest shared person, since a teammate on every thread links nothing; later before earlier,
as a promise made here may be delivered in a new thread), the whole task list and every note. No names, subject words or keywords are matched. `ContextIndex` is the v1 index over extractions; only its
`as_of` is still read."""
from __future__ import annotations

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
from ..util import domain_of, slugify


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


# ----------------------------------------------------------------------------- v2 retrieval
class ContextRef(Model):
    """One retrieved snippet. `text` is verbatim from the source (plus a one-line label), so a reader's quote from it
    can be checked: add (source_id, text) to the reader's SourceIndex."""
    source_id: str    # event:<uid> | note:<path> | task:<id> | msg:<id>
    text: str


EVENT_DAYS = 7
PREVIOUS_THREADS = 2
EXCERPT_CHARS = 300
NOTES_CHARS = 24_000   # every note goes to every reader; past this, newest first and `notes_left_out` names the rest


def _stamp(dt: datetime) -> str:
    return dt.strftime("%a %Y-%m-%d %H:%M")


def _excerpt(m: NormalizedMessage, label: str) -> ContextRef:
    who = f"{m.from_name} <{m.from_addr}>" if m.from_name else m.from_addr
    body = " ".join((m.body_new or "").split())[:EXCERPT_CHARS]
    return ContextRef(source_id=f"msg:{m.message_id}", text=f"{label} · {_stamp(m.sent_at)} · from {who} · subject: {m.subject}\n{body}")


def _event_text(e: NormalizedEvent, as_of: datetime, me: str = "owner") -> str:
    who = ", ".join(a.name or a.email for a in e.attendees[:8])
    return (f"{e.title} · {e.calendar} calendar · {_stamp(e.start)}–{e.end.strftime('%H:%M')} "
            f"({'past' if e.end < as_of else 'upcoming'}) · organizer {e.organizer} · {me}: {e.avery_partstat}"
            + (f" · attendees: {who}" if who else ""))


def _note_date(n) -> date | None:
    return n.header_date or (n.mtime.date() if n.mtime else None)


def _notes(world: NormalizedWorld) -> tuple[list[ContextRef], list[str]]:
    """Every note, newest first, whole, each line numbered as in the file (readers cite note:<path>#L<n>), until
    NOTES_CHARS; the paths that did not fit."""
    refs: list[ContextRef] = []
    left_out: list[str] = []
    budget = NOTES_CHARS
    for n in sorted(world.notes, key=lambda n: _note_date(n) or date.min, reverse=True):
        body = "\n".join(f"L{j + 1}: {ln}" for j, ln in enumerate(n.text.split("\n")) if ln.strip())
        text = f"note:{n.path} · {n.title} · dated {_note_date(n) or 'unknown'}\n{body}"
        if len(text) > budget:
            left_out.append(n.path)
            continue
        refs.append(ContextRef(source_id=f"note:{n.path}", text=text))
        budget -= len(text)
    return refs, left_out


def notes_left_out(world: NormalizedWorld) -> list[str]:
    """Notes no reader sees because the notes together pass NOTES_CHARS (the reader stage logs them)."""
    return _notes(world)[1]


def _tasks(world: NormalizedWorld) -> list[ContextRef]:
    return [ContextRef(source_id=f"task:{t.task_id}",
                       text=f"- [{'x' if t.status == 'done' else ' '}] {t.title}" + (f" (due: {t.due.isoformat()})" if t.due else ""))
            for t in world.tasks]


def _participants(t: NormalizedThread, owner: set[str]) -> set[str]:
    return {a.lower() for m in t.messages for a in (m.from_addr, *m.to, *m.cc) if a and a.lower() not in owner}


def _threads_per_address(world: NormalizedWorld, as_of: datetime, owner: set[str]) -> dict[str, int]:
    """How many human threads each address is on. A shared address links two threads as strongly as it is rare: a
    customer on three threads is a strong link, a co-founder on a hundred is almost none."""
    counts: dict[str, int] = {}
    for t in world.threads:
        if t.router_type == "human" and t.messages[0].sent_at <= as_of:
            for a in _participants(t, owner):
                counts[a] = counts.get(a, 0) + 1
    return counts


def retrieve(thread: NormalizedThread, world: NormalizedWorld, directory, as_of: datetime, cap_tokens: int = 4000) -> list[ContextRef]:
    """Context for one thread reader: events with the same people, then with the same outside domain, then the two
    threads with the same people, capped at about `cap_tokens` (4 characters a token); then the task list and the notes,
    whole. Links rank by the rarest shared person, then later before earlier, then nearest in time. `directory` is
    unused (kept for the reader stage's call)."""
    owner = world.owner_emails
    own_domains = {domain_of(e) for e in owner}
    people = _participants(thread, owner)
    domains = {domain_of(a) for a in people} - own_domains
    per_address = _threads_per_address(world, as_of, owner)

    def strength(shared: set[str]) -> float:
        return max((1 / per_address.get(a, 1) for a in shared), default=0.0)

    ranked: list[tuple[tuple, ContextRef]] = []
    # events in [as_of − 7d, as_of + 7d] sharing a participant or an outside domain; one occurrence per uid, the nearest
    lo, hi = as_of - timedelta(days=EVENT_DAYS), as_of + timedelta(days=EVENT_DAYS)
    nearest: dict[str, NormalizedEvent] = {}
    for e in world.events:
        if lo <= e.start <= hi and (e.uid not in nearest or abs(e.start - as_of) < abs(nearest[e.uid].start - as_of)):
            nearest[e.uid] = e
    for e in nearest.values():
        att = {a.email.lower() for a in e.attendees} | {e.organizer.lower()}
        if att & people:
            key = (0, -strength(att & people), abs((e.start - as_of).total_seconds()))
        elif {domain_of(a) for a in att} & domains:
            key = (1, 0.0, abs((e.start - as_of).total_seconds()))
        else:
            continue
        ranked.append((key, ContextRef(source_id=f"event:{e.uid}", text=_event_text(e, as_of, world.owner_name))))
    # the two other threads with the same people (a promise made here may be delivered in a new thread, so a later
    # thread comes before an earlier one with an equally rare shared person)
    first, last = thread.messages[0].sent_at, thread.messages[-1].sent_at
    others: list[tuple[tuple, bool, NormalizedThread]] = []
    for t in world.threads:
        if t.thread_id == thread.thread_id or t.router_type != "human" or t.messages[0].sent_at > as_of:
            continue
        shared = _participants(t, owner) & people
        if not shared:
            continue
        after = t.messages[0].sent_at > last
        gap = (t.messages[0].sent_at - last) if after else (first - t.messages[-1].sent_at)
        others.append(((-strength(shared), not after, abs(gap.total_seconds())), after, t))
    others.sort(key=lambda x: x[0])
    for i, (_key, after, t) in enumerate(others[:PREVIOUS_THREADS]):
        when = "after this thread" if after else "before this thread"
        ms = [t.messages[0]] + ([t.messages[-1]] if len(t.messages) > 1 else [])
        for k, m in enumerate(ms):
            label = f"related thread ({len(t.messages)} messages, started {when}), {'first' if k == 0 else 'last'} message"
            ranked.append(((2, float(i), float(k)), _excerpt(m, label)))
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
    return out + _tasks(world) + _notes(world)[0]


__all__ = ["ContextIndex", "ContextRef", "dependencies", "freshness_cap", "notes_left_out", "retrieve", "source_kind"]
