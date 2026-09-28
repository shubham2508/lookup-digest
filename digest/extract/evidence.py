"""Evidence check (CLAUDE.md rule 6; extraction_schema §0.2): every quote must be a verbatim substring of its source.
Facts that fail are dropped and logged. Required singleton evidence (Ball, Automated) is replaced by a verbatim
span from the right source, and logged, so the fact keeps checkable provenance instead of a fabricated quote."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ..schemas import EVIDENCE_MAX_WORDS, Evidence

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "–": "-",
                         "—": "-", "…": "..."})


def normalize_for_match(s: str) -> str:
    return _WS.sub(" ", s.translate(_QUOTES)).strip()


@dataclass
class EvidenceReport:
    checked: int = 0
    valid: int = 0
    dropped: list[dict] = field(default_factory=list)      # {path, source_id, quote, reason}
    replaced: list[dict] = field(default_factory=list)     # singleton evidence substituted


class SourceIndex:
    """Resolves the model's source ids leniently to the document's canonical ones."""

    def __init__(self, sources: dict[str, str]):
        self.sources = sources
        self._norm = {k: normalize_for_match(v) for k, v in sources.items()}
        self._alias: dict[str, str] = {}
        for k in sources:
            self._alias[k] = k
            self._alias[k.lower()] = k
            if k.startswith("msg:"):
                bare = k[4:].strip("<>")
                self._alias[f"msg:{bare}"] = k
                self._alias[f"msg:<{bare}>"] = k
            if k.startswith("note:"):
                base = k.rsplit("/", 1)[-1]
                self._alias[f"note:{base}"] = k

    def resolve(self, source_id: str) -> str | None:
        s = (source_id or "").strip()
        if s in self._alias:
            return self._alias[s]
        if s.startswith("note:") and "#" in s:
            return self.resolve(s.split("#", 1)[0])
        if s.startswith("msg:"):
            return self._alias.get(f"msg:<{s[4:].strip('<>')}>") or self._alias.get(f"msg:{s[4:].strip('<>')}")
        return self._alias.get(s.lower())

    def contains(self, source_id: str, quote: str) -> bool:
        key = self.resolve(source_id)
        if key is None:
            return False
        q = normalize_for_match(quote)
        return bool(q) and q in self._norm[key]

    def first_words(self, source_id: str, n: int = 12) -> str | None:
        key = self.resolve(source_id)
        if key is None:
            return None
        text = self.sources[key]
        body = text.split("\n", 1)[1] if "\n" in text else text     # skip the subject line for messages
        words = normalize_for_match(body).split(" ")
        span = " ".join(w for w in words[:n] if w)
        return span or None

    def canonical(self, source_id: str) -> str:
        return self.resolve(source_id) or source_id


def _fix_singleton(ev: Evidence, idx: SourceIndex, path: str, fallback_source: str | None, report: EvidenceReport) -> Evidence:
    report.checked += 1
    if idx.contains(ev.source_id, ev.quote):
        report.valid += 1
        return Evidence(source_id=idx.canonical(ev.source_id), quote=ev.quote)
    src = idx.canonical(ev.source_id) if idx.resolve(ev.source_id) else fallback_source
    span = idx.first_words(src) if src else None
    if span is None:
        report.dropped.append({"path": path, "source_id": ev.source_id, "quote": ev.quote, "reason": "unresolved source"})
        return ev
    report.replaced.append({"path": path, "source_id": ev.source_id, "quote": ev.quote, "replaced_with": span})
    return Evidence(source_id=src, quote=" ".join(span.split()[:EVIDENCE_MAX_WORDS]))


def check_payload(payload: BaseModel, idx: SourceIndex, fallback_source: str | None = None) -> tuple[BaseModel, EvidenceReport]:
    """Return a copy of the payload with invalid-evidence facts removed, plus the report."""
    report = EvidenceReport()
    fixed = _walk(payload, idx, "", fallback_source, report)
    assert isinstance(fixed, BaseModel)
    return fixed, report


def _evidence_ok(ev: Evidence, idx: SourceIndex, path: str, report: EvidenceReport) -> Evidence | None:
    report.checked += 1
    if idx.contains(ev.source_id, ev.quote):
        report.valid += 1
        return Evidence(source_id=idx.canonical(ev.source_id), quote=ev.quote)
    reason = "unresolved source" if idx.resolve(ev.source_id) is None else "quote not a substring of the source"
    report.dropped.append({"path": path, "source_id": ev.source_id, "quote": ev.quote, "reason": reason})
    return None


def _walk(node: Any, idx: SourceIndex, path: str, fallback: str | None, report: EvidenceReport) -> Any:
    if isinstance(node, Evidence):
        return _fix_singleton(node, idx, path, fallback, report)
    if isinstance(node, BaseModel):
        updates: dict[str, Any] = {}
        for name in type(node).model_fields:
            val = getattr(node, name)
            if isinstance(val, Evidence):
                updates[name] = _fix_singleton(val, idx, f"{path}.{name}".strip("."), fallback, report)
            elif isinstance(val, list):
                updates[name] = _walk_list(val, idx, f"{path}.{name}".strip("."), fallback, report)
            elif isinstance(val, BaseModel):
                updates[name] = _walk(val, idx, f"{path}.{name}".strip("."), fallback, report)
        return node.model_copy(update=updates) if updates else node
    return node


def _walk_list(items: list, idx: SourceIndex, path: str, fallback: str | None, report: EvidenceReport) -> list:
    out: list = []
    for i, item in enumerate(items):
        p = f"{path}[{i}]"
        if isinstance(item, Evidence):
            ok = _evidence_ok(item, idx, p, report)
            if ok is not None:
                out.append(ok)
            continue
        if isinstance(item, BaseModel):
            fields = type(item).model_fields
            keep = True
            updates: dict[str, Any] = {}
            for name in fields:
                val = getattr(item, name)
                if isinstance(val, Evidence):
                    ok = _evidence_ok(val, idx, f"{p}.{name}", report)
                    if ok is None:
                        keep = False
                        break
                    updates[name] = ok
                elif isinstance(val, list) and val and all(isinstance(v, Evidence) for v in val):
                    kept = _walk_list(val, idx, f"{p}.{name}", fallback, report)
                    if not kept:
                        keep = False
                        report.dropped.append({"path": p, "source_id": "", "quote": "", "reason": "all evidence invalid"})
                        break
                    updates[name] = kept
                elif isinstance(val, list):
                    updates[name] = _walk_list(val, idx, f"{p}.{name}", fallback, report)
                elif isinstance(val, BaseModel):
                    updates[name] = _walk(val, idx, f"{p}.{name}", fallback, report)
            if keep:
                out.append(item.model_copy(update=updates) if updates else item)
            continue
        out.append(item)
    return out
