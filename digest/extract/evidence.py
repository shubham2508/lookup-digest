"""Evidence check (CLAUDE.md rule 6; extraction_schema §0.2): every quote must be a verbatim substring of its source.
Facts that fail are dropped and logged. Required singleton evidence (Ball, Automated) is replaced by a verbatim
span from the right source, and logged, so the fact keeps checkable provenance instead of a fabricated quote."""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "–": "-",
                         "—": "-", "…": "..."})


def normalize_for_match(s: str) -> str:
    """Typography, whitespace and markdown emphasis ("**closed Thursday**") are not words: both sides drop them before
    the exact substring test."""
    return _WS.sub(" ", s.translate(_QUOTES).replace("*", "")).strip()


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


