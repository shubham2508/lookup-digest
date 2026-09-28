"""About-key canonicalization and merge (architecture §6.3): lowercase, slugify, map names to contact slugs (code);
which keys name the same thing is decided by the linker, an LLM call (digest/compute/linker.py, OPEN_QUESTIONS #16).
Merges are logged (reduce.json.about_merges); merge accuracy is an eval metric."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..schemas import ABOUT_KINDS, AboutMerge
from ..util import slugify


def canonical_key(key: str, name_to_slug: dict[str, str] | None = None) -> str:
    """'Deal:Series A:Cap Table' → 'deal:series-a:cap-table'; person/org names mapped to contact slugs when known."""
    parts = [p for p in (key or "").split(":") if p.strip()]
    if not parts:
        return "other:unknown"
    kind = slugify(parts[0])
    if kind not in ABOUT_KINDS:
        kind = "other"
    rest = [slugify(p) for p in parts[1:]] or ["unknown"]
    if name_to_slug:
        rest = [name_to_slug.get(r, r) for r in rest]
    rest = rest[:2]
    return ":".join([kind, *rest])


@dataclass
class _Key:
    key: str
    kind: str
    slug: str
    uses: int = 0
    entities: set[str] = field(default_factory=set)
    messages: set[str] = field(default_factory=set)


class AboutMerger:
    """Collects every about key with the entities, evidence threads and a short description of what the document said.
    Which keys name the same thing is decided by the linker (an LLM call, OPEN_QUESTIONS #16), never by word
    similarity; without the linker only identical canonical keys merge."""

    def __init__(self, generic_entities: set[str] | None = None):
        self.keys: dict[str, _Key] = {}
        self.texts: dict[str, list[str]] = {}
        self.generic_entities: set[str] = set(generic_entities or ())
        self.groups: list[list[str]] = []

    def add(self, key: str, entities: set[str] | None = None, messages: set[str] | None = None, text: str | None = None) -> str:
        k = self.keys.get(key)
        if k is None:
            kind, _, slug = key.partition(":")
            k = self.keys[key] = _Key(key, kind, slug)
        k.uses += 1
        k.entities |= set(entities or ())
        k.messages |= set(messages or ())
        if text:
            texts = self.texts.setdefault(key, [])
            if len(texts) < 2 and text not in texts:
                texts.append(" ".join(text.split())[:160])
        return key

    def by_kind(self) -> dict[str, list[dict]]:
        """kind → [{key, text}] for the linker; offer and candidate share a bucket (one person's loop)."""
        out: dict[str, list[dict]] = defaultdict(list)
        for k in self.keys.values():
            bucket = "offer/candidate" if k.kind in ("offer", "candidate") else k.kind
            out[bucket].append({"key": k.key, "text": " | ".join(self.texts.get(k.key, [])) or k.key})
        return dict(out)

    def resolve(self, groups: list[list[str]] | None = None) -> tuple[dict[str, str], list[AboutMerge]]:
        if groups is not None:
            self.groups = groups
        keys = list(self.keys.values())
        parent = {k.key: k.key for k in keys}
        reason: dict[tuple[str, str], str] = {}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for g in self.groups:
            members = [m for m in g if m in parent]
            for m in members[1:]:
                ra, rb = find(members[0]), find(m)
                if ra != rb:
                    parent[rb] = ra
                    reason[(members[0], m)] = "linker"
        groups: dict[str, list[_Key]] = defaultdict(list)
        for k in keys:
            groups[find(k.key)].append(k)
        mapping: dict[str, str] = {}
        merges: list[AboutMerge] = []
        for members in groups.values():
            canonical = max(members, key=lambda k: (k.uses, -len(k.key), k.key))
            for m in members:
                mapping[m.key] = canonical.key
            if len(members) > 1:
                why = sorted({r for (x, y), r in reason.items() if x in {m.key for m in members} or y in {m.key for m in members}})
                merges.append(AboutMerge(canonical=canonical.key, merged=sorted(m.key for m in members if m.key != canonical.key),
                                         reason=", ".join(why)))
        merges.sort(key=lambda m: m.canonical)
        return mapping, merges
