"""Context retrieval, source dependencies and freshness caps (architecture §6.5)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..normalize import NormalizedWorld
from ..schemas import Candidate, Extraction, FreshnessCap, SourceKind
from ..util import slugify


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


__all__ = ["ContextIndex", "apply_context", "dependencies", "freshness_cap", "source_kind"]


def _unused(_: date) -> None:  # keep `date` import for type hints in annotations
    return None
