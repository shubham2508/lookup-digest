"""Result types and selectors shared by metrics, assertion checkers and attribution."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from eval.manifest_schema import Manifest

from .artifacts import RenderedItem, Row, RunView
from .match import about_match, type_matches

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
    k = key.lower()
    for c in manifest.contacts:
        if c.email.lower() == k or c.name.lower() == k:
            return c
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
    expected item that `day`), `source_id` (cites that manifest item),
    `type` (candidate type or a list of alternatives, prefix match), `category` (truth category of a cited sender), `source_kind`
    (manifest kind of a cited source: thread | note | newsletter | ...).
    """
    cites_any = cites_any if cites_any is not None else list(args.get("cites_any") or [])
    claimed = claimed_abouts(manifest, day if day is not None else view.day, args.get("about"))
    out = []
    for it in view.rendered:
        if "about" in args and not (about_match(it.about, args["about"]) or _by_cites(it.about, it.source_ids, cites_any, claimed)):
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


def select_candidates(view: RunView, ctype: str | None = None, about: str | None = None,
                      cites_any: list[str] | None = None, claimed: list[str] | None = None) -> list[Row]:
    out = []
    for r in view.candidates:
        if ctype and not type_matches(r.data.get("type"), ctype):
            continue
        if about:
            srcs = view.index.resolve_all(r.data.get("context_refs", []) + [e.get("source_id", "") for e in r.data.get("evidence", [])])
            if not (about_match(r.data.get("about"), about) or _by_cites(r.data.get("about"), srcs, cites_any or [], claimed or [])):
                continue
        out.append(r)
    return out


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
