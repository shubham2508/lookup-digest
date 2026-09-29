"""Result types and selectors shared by metrics, assertion checkers and attribution."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, get_args

from digest.schemas import CandidateType
from eval.manifest_schema import Manifest

from .artifacts import RenderedItem, RunView, Signal
from .coverage import covered_items, covered_signals, other_keys
from .match import about_match, split_about, type_matches

GENERIC_TOKENS = {"the", "and", "for", "with", "other", "meeting", "update", "series"}

# v2 attribution chain (PIVOT_SPEC §2), the entity spine first: a miss belongs to the first stage that lost it
STAGES = ("spine", "read", "sweep", "net", "merge", "compose", "materialize", "verify")


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
    lists: dict[str, list[str]] = field(default_factory=dict)  # named bullet lists for the report (e.g. the rescue list)

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


def is_never_draft(manifest: Manifest, target: str | None) -> bool:
    """A draft to this contact breaks a hard rule: never_draft (Sam), cold inbound, recruiters."""
    if not target:
        return False
    c = contact_label(manifest, target)
    if c is None:
        return False
    return "never_draft" in c.rules or c.category == "cold_inbound" or "recruit" in (c.subtype or "")


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


def expected_cites(manifest: Manifest, day: int | None, about: str | None) -> list[str]:
    """The answer key's own sources for a key that day: the cites_any of that day's expected items with that key.
    They stand in when a selector names a key but no sources (OPEN_QUESTIONS #21): v2 readers write light, free
    about tags ("deal:series-a"), so a key alone cannot find their items."""
    if day is None or not about:
        return []
    try:
        rd = manifest.run_day(day)
    except KeyError:
        return []
    items = list(rd.items) + ([rd.one_thing] if rd.one_thing else [])
    return sorted({s for ei in items if about_match(ei.about, about) for s in ei.cites_any})


def _by_cites(item_about: str | None, sources: set[str], cites_any: list[str], claimed: list[str]) -> bool:
    return bool(cites_any and sources & set(cites_any)) and not any(about_match(item_about, k) for k in claimed)


def select_items(view: RunView, manifest: Manifest, args: dict, cites_any: list[str] | None = None,
                 day: int | None = None) -> list[RenderedItem]:
    """Rendered items matching every selector given in args.

    Selectors: `about` (fuzzy about key of the item or of a finding behind it, or cites one of `cites_any` unless the
    item's key belongs to another expected item that `day`, or the #9 fallback; no `cites_any` → the answer key's
    sources for that key that day), `source_id` (cites that manifest item), `type` (v1 candidate type or a list of
    alternatives: see `signal_is_type`), `category` (truth category of a cited sender), `source_kind` (manifest kind
    of a cited source: thread | note | newsletter | ...).
    """
    cites_any = cites_any if cites_any is not None else list(args.get("cites_any") or [])
    day = day if day is not None else view.day
    cites_any = cites_any or expected_cites(manifest, day, args.get("about"))
    covered = covered_items(view, manifest, args["about"], cites_any, day) if "about" in args else None
    out = []
    for it in view.rendered:
        if covered is not None and it.id not in covered and not _by_signal_fallback(view, manifest, it, args["about"], day):
            continue
        if "source_id" in args and args["source_id"] not in it.source_ids:
            continue
        types = [args["type"]] if isinstance(args.get("type"), str) else list(args.get("type") or [])
        if types and not any(item_is_type(view, it, w) for w in types):
            continue
        if "category" in args and args["category"] not in item_categories(manifest, it):
            continue
        if "source_kind" in args and not any(view.index.kind_of(s) == args["source_kind"] for s in it.source_ids):
            continue
        out.append(it)
    return out


# ----------------------------------------------------------------------------- v1 candidate types in v2
# Safety nets keep their v1 rule name as `kind`; readers and sweeps write free text. Where a Finding has a structural
# analog of a v1 type, the analog stands in for the name and is required (an about match alone does not make a
# finding a contradiction or a news attachment). The other v1 types have no v2 rule and are matched by about key.
STRUCTURAL_TYPES: dict[str, Callable[[Signal], bool]] = {
    "contradiction": lambda s: s.contradiction,
    "suspicious_content": lambda s: s.suspicious,
    "news_attachment": lambda s: s.origin == "news_sweep",
}
# MIGRATION_PLAN §1: the v1 rules kept as safety nets (their findings carry these names)
NET_TYPES = ("reply_owed", "quiet_thread", "calendar_conflict", "double_book", "recruiter_pattern", "stale_source",
             "suspicious_content", "approval_pending")


V1_TYPES = get_args(CandidateType)


def names_a_v1_rule(kind: str) -> bool:
    """A net's kind or a v1 candidate's type (as opposed to a reader's or a sweep's free-text kind)."""
    return any(type_matches(kind, t) for t in V1_TYPES)


def signal_is_type(s: Signal, wanted: str) -> bool:
    if type_matches(s.type, wanted):
        return True
    check = STRUCTURAL_TYPES.get(wanted)
    return bool(check and check(s))


def open_world_type(ctype: str) -> bool:
    """A v1 type that v2 has neither a net nor a structural analog for (commitments, cadences, stalls, tasks, ...)."""
    return ctype not in STRUCTURAL_TYPES and not any(type_matches(ctype, t) or type_matches(t, ctype) for t in NET_TYPES)


def item_is_type(view: RunView, it: RenderedItem, wanted: str) -> bool:
    return any(type_matches(t, wanted) for t in it.candidate_types) or any(signal_is_type(s, wanted) for s in view.item_signals(it))


def about_tokens(key: str) -> list[str]:
    """Distinctive slug tokens of an about key (`meeting:lumen-demo` → lumen, demo)."""
    _, rest = split_about(key)
    return [t for t in re.split(r"[:\-]", rest) if len(t) >= 3 and t not in GENERIC_TOKENS]


def labeled_with(manifest: Manifest, about: str) -> set[str]:
    """Manifest sources whose expected labels carry this about key."""
    return {i.source_id for i in manifest.items if i.expected and any(about_match(a, about) for a in i.expected.about)}


def fallback_signal_match(view: RunView, s: Signal, about: str, storyline: str | None = None) -> bool:
    """OPEN_QUESTIONS #9, sources only: a finding of the expected type matches when it cites a source the answer key
    labels with that key, or a source of the same storyline. (The former token-in-entity heuristic is gone: #23.)"""
    manifest = view.index.manifest
    if s.sources & labeled_with(manifest, about):
        return True
    return bool(storyline and any(manifest.item(x).storyline == storyline for x in s.sources))


def _claimed_by_other(s: Signal, claimed: list[str]) -> bool:
    return any(about_match(a, k) for a in s.abouts for k in claimed)


def _day_expected(view: RunView, about: str):
    if view.day is None:
        return []
    try:
        return [c for c in view.index.manifest.run_day(view.day).candidates if about_match(c.about, about)]
    except KeyError:
        return []


def _by_signal_fallback(view: RunView, manifest: Manifest, it: RenderedItem, about: str, day: int | None,
                        claimed: list[str] | None = None) -> bool:
    """OPEN_QUESTIONS #9 for rendered items: a finding behind the item is the day's expected signal for this key by
    type + a citation the answer key labels with that key or its storyline (e.g. a net's `family:wren` whose evidence
    is `event:wren-pediatrician-…` is the manifest's `family:pediatrician`)."""
    if day is None or not it.candidate_ids or any(about_match(it.about, k) for k in other_keys(manifest, day, about)):
        return False   # an item labeled with another expected item's key, exactly, is that item
    try:
        expected = [c for c in manifest.run_day(day).candidates if about_match(c.about, about)]
    except KeyError:
        return False
    return any(signal_is_type(s, ec.type) and fallback_signal_match(view, s, ec.about, ec.storyline)
               for ec in expected for s in view.item_signals(it))


def _extra_selectors(view: RunView, s: Signal, args: dict) -> bool:
    """`source_id`, `source_kind`, `category` (a cited sender's truth category or the cited item's background
    category) and `system` (an automated item's system) narrow a candidate-kind assertion."""
    m = view.index.manifest
    if "source_id" in args and args["source_id"] not in s.sources:
        return False
    if "source_kind" in args and not any(view.index.kind_of(x) == args["source_kind"] for x in s.sources):
        return False
    items = [m.item(x) for x in s.sources if view.index.kind_of(x)]
    if "category" in args:
        cats = {i.category for i in items} | {c.category for x in s.sources for c in (
            contact_label(m, e) for e in sender_emails(m, x)) if c}
        if args["category"] not in cats:
            return False
    if "system" in args:
        systems = {(i.expected.automated.system or "").lower() for i in items if i.expected and i.expected.automated}
        if str(args["system"]).lower() not in systems:
            return False
    return True


def select_signals(view: RunView, ctype: str | None = None, about: str | None = None, cites_any: list[str] | None = None,
                   claimed: list[str] | None = None, *, live: bool = True, args: dict | None = None) -> list[Signal]:
    """Findings (or finding-less candidates) of v1 type `ctype` about `about` (MIGRATION_PLAN §1, handoff C3).

    With `about`: the finding's about keys fuzzy-match it or it cites one of `cites_any` (never through a key another
    expectation that day claims), or it is of the type and passes the #9 fallback. The about alternative stands in
    for a free-text kind only: a finding that names another v1 rule (a net's `approval_pending` about a candidate) is
    that rule, not this one. A structural type (contradiction, suspicious_content, news_attachment) must also carry
    its analog. Without `about`: the type alone decides.
    `live` keeps only findings that reach the digest (needs_avery yes, or unsure with a card)."""
    cites_any = cites_any or expected_cites(view.index.manifest, view.day, about)
    covered = covered_signals(view, about, cites_any, ctype) if about else set()
    storylines = {c.storyline for c in _day_expected(view, about) if c.storyline} if about else set()
    out = []
    for s in view.signals:
        if live and not s.live:
            continue
        typed = ctype is None or signal_is_type(s, ctype)
        if about:
            foreign = not typed and names_a_v1_rule(s.type)
            direct = not foreign and id(s) in covered
            fallback = ctype is not None and typed and any(fallback_signal_match(view, s, about, st) for st in (storylines or {None}))
            ok = (typed and (direct or fallback)) if (ctype in STRUCTURAL_TYPES) else (direct or fallback)
        else:
            ok = typed
        if ok and (not args or _extra_selectors(view, s, args)):
            out.append(s)
    return out


def signals_for_expected(view: RunView, about: str | None, cites_any: list[str] | None = None,
                         claimed: list[str] | None = None, *, live: bool = False) -> list[Signal]:
    """Findings behind an expected item: direct (fuzzy key / cited source), else via the day's expected candidates for
    that key, whose types enable the #9 fallback. `live=False` also returns findings that said needs_avery: no."""
    if not about:
        cites = set(cites_any or [])
        return [s for s in view.signals if (s.live or not live) and s.sources & cites]
    rows = select_signals(view, about=about, cites_any=cites_any, claimed=claimed, live=live)
    if rows:
        return rows
    seen: dict[int, Signal] = {}
    for ec in _day_expected(view, about):
        for s in select_signals(view, ec.type, about, cites_any, claimed, live=live):
            seen[id(s)] = s
    return list(seen.values())
