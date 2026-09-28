"""About-key canonicalization and merge (architecture §6.3): lowercase, slugify, map names to contact slugs; merge
two keys of the same kind when the slug fuzzy ratio ≥ threshold, or they share an entity and an evidence message.
Merges are logged (reduce.json.about_merges); merge accuracy is an eval metric."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz

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


_SPECIFIC_KINDS = {"offer", "renewal", "incident", "rollout", "hiring-req", "pricing", "contract", "approval", "invoice", "report"}


_GENERIC_TOKENS = {"product", "engineer", "engineers", "update", "updates", "report", "review", "meeting", "request", "series",
                   "other", "email", "thread", "avery", "tessera", "second", "first", "draft", "notes", "weekly", "monthly"}


def _tokens_overlap(x: str, y: str) -> bool:
    """The slugs share a meaningful token (hiring-req:backend ~ hiring-req:backend-engineer), ignoring generic words."""
    tx = {w for w in x.replace(":", "-").split("-") if len(w) >= 5 and w not in _GENERIC_TOKENS}
    ty = {w for w in y.replace(":", "-").split("-") if len(w) >= 5 and w not in _GENERIC_TOKENS}
    return bool(tx & ty)


def _is_prefix(x: str, y: str) -> bool:
    """One slug extends the other with more hyphenated words (≥ 6 chars of common prefix, no colon qualifier)."""
    if ":" in x or ":" in y:
        return False
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return len(short) >= 6 and long_.startswith(short + "-")


def _is_subtopic(x: str, y: str) -> bool:
    """series-a vs series-a:cap-table: the qualifier names a distinct sub-topic of the same thing."""
    return x.startswith(y + ":") or y.startswith(x + ":")


class AboutMerger:
    def __init__(self, fuzzy_ratio: float = 0.85, generic_entities: set[str] | None = None):
        self.threshold = fuzzy_ratio * 100
        self.keys: dict[str, _Key] = {}
        # entities too common to link topics: Avery, the company, the internal team (compute fills this in)
        self.generic_entities: set[str] = set(generic_entities or ())

    def add(self, key: str, entities: set[str] | None = None, messages: set[str] | None = None) -> str:
        k = self.keys.get(key)
        if k is None:
            kind, _, slug = key.partition(":")
            k = self.keys[key] = _Key(key, kind, slug)
        k.uses += 1
        k.entities |= set(entities or ())
        k.messages |= set(messages or ())
        return key

    def _should_merge(self, a: _Key, b: _Key) -> str | None:
        if a.kind != b.kind:
            # offer:mei-tanaka and candidate:mei-tanaka are the same person's loop (manifest should_merge)
            if {a.kind, b.kind} == {"offer", "candidate"} and fuzz.ratio(a.slug, b.slug) >= self.threshold:
                return "kind-alias"
            return None
        if fuzz.ratio(a.slug, b.slug) >= self.threshold:
            return "fuzzy-ratio"
        # deal:series-a never swallows deal:series-a:cap-table; rollout:halberd may absorb rollout:halberd:oct-6
        subtopic_blocked = _is_subtopic(a.slug, b.slug) and a.kind not in _SPECIFIC_KINDS
        ents = (a.entities & b.entities) - self.generic_entities
        msgs = {m for m in (a.messages & b.messages) if not m.startswith(("note:", "task:", "event:"))}  # notes mention everything
        if not subtopic_blocked and ents and msgs:
            return "shared-entity-and-evidence"
        if a.kind == "board-update":
            return "singleton-kind"  # one board update is ever in play; every spelling of it is the same item
        if a.kind in _SPECIFIC_KINDS and _tokens_overlap(a.slug, b.slug):
            return "same-kind-token"
        if not subtopic_blocked and _is_prefix(a.slug, b.slug):
            return "slug-prefix"  # deal:aperture ~ deal:aperture-capital, report:soc-2 ~ report:soc-2-type-ii
        if not subtopic_blocked and msgs and _tokens_overlap(a.slug, b.slug):
            return "shared-evidence-and-token"
        return None

    def resolve(self) -> tuple[dict[str, str], list[AboutMerge]]:
        keys = list(self.keys.values())
        parent = {k.key: k.key for k in keys}
        reason: dict[tuple[str, str], str] = {}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                why = self._should_merge(a, b)
                if why:
                    ra, rb = find(a.key), find(b.key)
                    if ra != rb:
                        parent[rb] = ra
                        reason[(a.key, b.key)] = why
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
