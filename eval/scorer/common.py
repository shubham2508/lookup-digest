"""Result types and selectors shared by metrics, assertion checkers and attribution."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from eval.manifest_schema import Manifest

from .artifacts import RenderedItem, Row, RunView
from .match import about_match, split_about, type_matches

GENERIC_TOKENS = {"the", "and", "for", "with", "other", "meeting", "update", "series"}

STAGES = ("extraction", "compute", "triage", "compose", "materializer")


@dataclass
class Miss:
    what: str
    expected: Any = None
    got: Any = None
    link: str | None = None
    stage: str | None = None


@dataclass
class StageMetrics:
    stage: str
    metrics: dict[str, Any] = field(default_factory=dict)
    misses: list[Miss] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    return {"precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn), "tp": tp, "fp": fp, "fn": fn}


# ----------------------------------------------------------------------------- manifest-side lookups
def sender_emails(manifest: Manifest, source_id: str) -> list[str]:
    """Non-Avery senders of a manifest item, in message order."""
    try:
        item = manifest.item(source_id)
    except KeyError:
        return []
    out = []
    for m in item.messages:
        if not m.is_from_avery and m.from_email not in out:
            out.append(m.from_email)
    return out


def contact_label(manifest: Manifest, key: str):
    """By email or full name; a bare first name ("Sam", as markdown drafts give it) when exactly one contact has it."""
    k = key.lower().strip()
    for c in manifest.contacts:
        if c.email.lower() == k or c.name.lower() == k:
            return c
    if k and "@" not in k and " " not in k:
        firsts = [c for c in manifest.contacts if c.name.lower().split()[0] == k]
        if len(firsts) == 1:
            return firsts[0]
    return None


def item_categories(manifest: Manifest, item: RenderedItem) -> set[str]:
    cats: set[str] = set()
    for sid in item.source_ids:
        for e in sender_emails(manifest, sid):
            c = contact_label(manifest, e)
            if c:
                cats.add(c.category)
    for ent in item.entities:
        c = contact_label(manifest, ent)
        if c:
            cats.add(c.category)
    if item.about and item.about.startswith("family:"):
        cats.add("family")
    return cats


# ----------------------------------------------------------------------------- selectors
SELECTOR_KEYS = ("about", "source_id", "type", "category", "source_kind")


def claimed_abouts(manifest: Manifest, day: int | None, about: str | None) -> list[str]:
    """About keys of the *other* expected items that day. A citation match may not steal an item that is theirs
    (Sam's email is cited by both the pediatrician conflict and the daycare ask)."""
    if day is None or not about:
        return []
    try:
        rd = manifest.run_day(day)
    except KeyError:
        return []
    keys = [ei.about for ei in rd.items] + ([rd.one_thing.about] if rd.one_thing else [])
    return [k for k in keys if not about_match(k, about)]


def _by_cites(item_about: str | None, sources: set[str], cites_any: list[str], claimed: list[str]) -> bool:
    return bool(cites_any and sources & set(cites_any)) and not any(about_match(item_about, k) for k in claimed)


def select_items(view: RunView, manifest: Manifest, args: dict, cites_any: list[str] | None = None,
                 day: int | None = None) -> list[RenderedItem]:
    """Rendered items matching every selector given in args.

    Selectors: `about` (fuzzy about key, or cites one of `cites_any` unless the item's key belongs to another
    expected item that `day`, or the #9 candidate fallback), `source_id` (cites that manifest item),
    `type` (candidate type or a list of alternatives, prefix match), `category` (truth category of a cited sender), `source_kind`
    (manifest kind of a cited source: thread | note | newsletter | ...).
    """
    cites_any = cites_any if cites_any is not None else list(args.get("cites_any") or [])
    day = day if day is not None else view.day
    claimed = claimed_abouts(manifest, day, args.get("about"))
    out = []
    for it in view.rendered:
        if "about" in args and not (about_match(it.about, args["about"]) or _by_cites(it.about, it.source_ids, cites_any, claimed)
                                    or _by_candidate_fallback(view, manifest, it, args["about"], day, claimed)):
            continue
        if "source_id" in args and args["source_id"] not in it.source_ids:
            continue
        types = [args["type"]] if isinstance(args.get("type"), str) else list(args.get("type") or [])
        if types and not any(type_matches(t, w) for t in it.candidate_types for w in types):
            continue
        if "category" in args and args["category"] not in item_categories(manifest, it):
            continue
        if "source_kind" in args and not any(view.index.kind_of(s) == args["source_kind"] for s in it.source_ids):
            continue
        out.append(it)
    return out


def _cand_sources(view: RunView, r: Row) -> set[str]:
    return view.index.resolve_all(r.data.get("context_refs", []) + [e.get("source_id", "") for e in r.data.get("evidence", [])])


def about_tokens(key: str) -> list[str]:
    """Distinctive slug tokens of an about key (`meeting:lumen-demo` → lumen, demo)."""
    _, rest = split_about(key)
    return [t for t in re.split(r"[:\-]", rest) if len(t) >= 3 and t not in GENERIC_TOKENS]


def labeled_with(manifest: Manifest, about: str) -> set[str]:
    """Manifest sources whose expected extraction carries this about key."""
    return {i.source_id for i in manifest.items if i.expected and any(about_match(a, about) for a in i.expected.about)}


def fallback_candidate_match(view: RunView, r: Row, about: str, storyline: str | None = None) -> bool:
    """OPEN_QUESTIONS #9: a computed key that doesn't fuzzy-match still matches (the caller checks the type) when the
    candidate shares a citation with a source labeled with that key or with the storyline, or an entity token."""
    srcs = _cand_sources(view, r)
    manifest = view.index.manifest
    if srcs & labeled_with(manifest, about):
        return True
    if storyline and any(manifest.item(s).storyline == storyline for s in srcs):
        return True
    blob = " ".join([*map(str, r.data.get("entities", [])), *(e.get("source_id", "") for e in r.data.get("evidence", []))]).lower()
    return any(tok in blob for tok in about_tokens(about))


def _by_candidate_fallback(view: RunView, manifest: Manifest, it: RenderedItem, about: str, day: int | None,
                           claimed: list[str]) -> bool:
    """OPEN_QUESTIONS #9 for rendered items: the item's candidate is the day's expected candidate for this key by
    type + shared labeled citation / storyline / entity token (e.g. compute's `family:wren` whose evidence is
    `event:wren-pediatrician-…` is the manifest's `family:pediatrician`). Never for a key another expectation claims."""
    if day is None or not it.candidate_ids or any(about_match(it.about, k) for k in claimed):
        return False
    try:
        expected = [c for c in manifest.run_day(day).candidates if about_match(c.about, about)]
    except KeyError:
        return False
    for ec in expected:
        for cid in it.candidate_ids:
            row = view.candidate(cid)
            if row and type_matches(row.data.get("type"), ec.type) and fallback_candidate_match(view, row, ec.about, ec.storyline):
                return True
    return False


def select_candidates(view: RunView, ctype: str | None = None, about: str | None = None,
                      cites_any: list[str] | None = None, claimed: list[str] | None = None) -> list[Row]:
    """Candidates of `ctype` about `about`: fuzzy key or cited source first; with a type given and no such match,
    the #9 fallback (shared labeled citation or entity token), never for a key another expectation claims."""
    out = []
    for r in view.candidates:
        if ctype and not type_matches(r.data.get("type"), ctype):
            continue
        if about:
            key = r.data.get("about")
            direct = about_match(key, about) or _by_cites(key, _cand_sources(view, r), cites_any or [], claimed or [])
            fallback = (ctype is not None and not any(about_match(key, k) for k in claimed or [])
                        and fallback_candidate_match(view, r, about))
            if not (direct or fallback):
                continue
        out.append(r)
    return out


def candidates_for_expected(view: RunView, about: str, cites_any: list[str] | None = None,
                            claimed: list[str] | None = None) -> list[Row]:
    """Candidates behind an expected item: direct (fuzzy key / cited source), else via the day's expected candidates
    for that key, whose types enable the #9 fallback."""
    rows = select_candidates(view, about=about, cites_any=cites_any, claimed=claimed)
    if rows or view.day is None:
        return rows
    try:
        expected = [c for c in view.index.manifest.run_day(view.day).candidates if about_match(c.about, about)]
    except KeyError:
        return []
    seen: dict[int, Row] = {}
    for ec in expected:
        for r in select_candidates(view, ec.type, about, cites_any, claimed):
            seen[r.line] = r
    return list(seen.values())


def extractions_for(view: RunView, source_ids: set[str], about: str | None = None) -> list[Row]:
    """Extractions whose evidence resolves to one of the sources, or whose about keys match."""
    out = []
    for r in view.extractions:
        srcs = view.extraction_sources(r)
        abouts = (r.data.get("payload") or {}).get("about") or []
        if isinstance(abouts, str):
            abouts = [abouts]
        if (srcs & source_ids) or (about and any(about_match(a, about) for a in abouts)):
            out.append(r)
    return out
