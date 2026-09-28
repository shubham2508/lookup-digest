"""Matching rules shared by every metric (extraction_schema §7 "Matching rules for scoring").

- About keys: same `kind`, and the rest (slug + qualifier) has a fuzzy ratio ≥ 0.85. Strict on purpose: the scorer
  must not be kinder than the product. (Grader side only; the product decides sameness with its linker.)
- Source references: product evidence IDs (`msg:<message-id>`, `thread:<root message-id>`, `note:<path>#L<n>`,
  `task:<id>`, `event:<uid>`) are mapped back to manifest `source_id`s through the manifest's message labels. The
  product assigns its own thread IDs, so a thread is identified by its messages, never by its ID.
- Dates: equal within the granularity the product claimed (day → same PT day, week → 7 days, ...).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, time
from pathlib import PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz

from eval.manifest_schema import Manifest

FUZZY_RATIO = 0.85
PT = ZoneInfo("America/Los_Angeles")


# ----------------------------------------------------------------------------- about keys
def split_about(key: str) -> tuple[str, str]:
    kind, _, rest = (key or "").strip().lower().partition(":")
    return kind, rest


def about_match(a: str | None, b: str | None, ratio: float = FUZZY_RATIO) -> bool:
    if not a or not b:
        return False
    ka, ra = split_about(a)
    kb, rb = split_about(b)
    if ka != kb:
        return False
    return ra == rb or fuzz.ratio(ra, rb) / 100.0 >= ratio


def any_about_match(key: str | None, keys: Iterable[str]) -> bool:
    return any(about_match(key, k) for k in keys)


# ----------------------------------------------------------------------------- candidate / action types
def type_matches(actual: str | None, wanted: str) -> bool:
    """`calendar_conflict` matches every `calendar_conflict:*`; otherwise exact."""
    if not actual:
        return False
    return actual == wanted or actual.startswith(wanted + ":")


# ----------------------------------------------------------------------------- source references
def _norm_msg(mid: str) -> str:
    return mid.strip().strip("<>").strip().lower()


def _stem(path: str) -> str:
    p = path.split("#", 1)[0]
    p = p.split(":", 1)[1] if p.startswith(("note:", "notes:")) else p
    return PurePosixPath(p).stem.lower()


class SourceIndex:
    """Maps any product source reference to a manifest `source_id` (or None)."""

    def __init__(self, manifest: Manifest):
        self.manifest = manifest
        self.by_msg: dict[str, str] = {}
        self.msg_label: dict[str, Any] = {}
        self.by_note: dict[str, str] = {}
        self.by_task: dict[str, str] = {}
        self.ids = {i.source_id for i in manifest.items}
        for item in manifest.items:
            for m in item.messages:
                self.by_msg[_norm_msg(m.message_id)] = item.source_id
                self.msg_label[_norm_msg(m.message_id)] = m
            if item.kind == "note":
                self.by_note[_stem(item.source_id)] = item.source_id
            if item.kind == "task":
                self.by_task[item.source_id.split(":", 1)[-1].lower()] = item.source_id

    def resolve(self, ref: str | None) -> str | None:
        if not ref:
            return None
        ref = ref.strip()
        if ref in self.ids:
            return ref
        low = ref.lower()
        if low.startswith(("msg:", "thread:")):
            return self.by_msg.get(_norm_msg(ref.split(":", 1)[1]))
        if low.startswith("note:"):
            return self.by_note.get(_stem(ref))
        if low.startswith("task:"):
            return self.by_task.get(ref.split(":", 1)[1].split("#", 1)[0].lower())
        if low.startswith("event:"):  # `event:<uid>`; a uid may carry an @domain or #occurrence the manifest id lacks
            uid = ref.split(":", 1)[1].split("#", 1)[0].split("@", 1)[0].strip()
            return f"event:{uid}" if f"event:{uid}" in self.ids else None
        if "@" in ref:  # a bare message id
            return self.by_msg.get(_norm_msg(ref))
        return None

    def resolve_all(self, refs: Iterable[str]) -> set[str]:
        return {s for s in (self.resolve(r) for r in refs) if s}

    def kind_of(self, source_id: str) -> str | None:
        try:
            return self.manifest.item(source_id).kind
        except KeyError:
            return None


def evidence_refs(obj: Any) -> list[str]:
    """Every `source_id` value nested anywhere in a JSON-like object (evidence, citations, ...)."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_id" and isinstance(v, str):
                out.append(v)
            else:
                out.extend(evidence_refs(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(evidence_refs(v))
    return out


def majority_source(index: SourceIndex, refs: Iterable[str], own_id: str | None = None, kind: str | None = None) -> str | None:
    """The manifest item a finding is about: its own id if the manifest knows it, else the majority of its evidence
    (counting only items of `kind`, when given)."""
    if own_id and index.resolve(own_id):
        return index.resolve(own_id)
    counts = Counter(s for s in (index.resolve(r) for r in refs) if s and (kind is None or index.kind_of(s) == kind))
    return counts.most_common(1)[0][0] if counts else None


# ----------------------------------------------------------------------------- dates
_TOLERANCE_DAYS = {"exact": 0, "day": 0, "week": 7, "month": 31, "quarter": 92}


def expected_dt(manifest: Manifest, day: int | None, hhmm: str | None = None) -> datetime | None:
    if day is None:
        return None
    d: date = manifest.meta.day_to_date(day)
    t = time.fromisoformat(hhmm) if hhmm else time(23, 59)
    return datetime.combine(d, t, tzinfo=PT)


def date_within(actual_iso: str | None, expected: datetime | None, granularity: str | None) -> bool | None:
    """True/False, or None when not scoreable (no expectation, unknown granularity)."""
    if expected is None:
        return None
    if not actual_iso:
        return False
    tol = _TOLERANCE_DAYS.get(granularity or "day")
    if tol is None:
        return None
    actual = datetime.fromisoformat(actual_iso)
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=PT)
    delta = abs((actual.astimezone(PT).date() - expected.astimezone(PT).date()).days)
    return delta <= tol


# ----------------------------------------------------------------------------- text
def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def contains_phrase(text: str, phrase: str | list[str]) -> bool:
    """A phrase may be a list of alternatives: any one of them counts (e.g. ["Fri", "Friday", "Sep 25"])."""
    t = norm_text(text)
    if isinstance(phrase, list):
        return any(norm_text(p) in t for p in phrase)
    return norm_text(phrase) in t


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def max_priority(ps: Iterable[str | None]) -> str | None:
    vals = [p for p in ps if p in PRIORITY_ORDER]
    return min(vals, key=PRIORITY_ORDER.__getitem__) if vals else None
