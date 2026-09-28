"""Merge diagnostics (PIVOT_SPEC §6, handoff C2): over-merged or duplicated items on the page. Reported, never gated.

- Duplicate: an expected item's key is matched by more rendered items (sections, one thing and also-pending
  one-liners alike) than the answer key lists for that key that day (some keys are expected twice, e.g. a thread
  and the newsletter that attaches to it).
- Over-merge: one rendered item matches two or more different expected keys of that day.
"Matches" is the scorer's usual item selector (`common.select_items`: fuzzy key of the item or of a finding behind
it, a cited source, or the #9 fallback). Also scored here: the answer key's about-key pairs that should or should
not merge, against the merges reduce logged (`reduce.json` `about_merges`).
"""
from __future__ import annotations

from collections import Counter

from eval.manifest_schema import Manifest

from .artifacts import RunView
from .common import Miss, StageMetrics, rate, select_items
from .match import about_match, split_about


def _merged(view: RunView, a: str, b: str) -> bool | None:
    """Did the run treat a and b as one key? None if it logged no merges and the keys differ."""
    if split_about(a) == split_about(b):
        return True
    groups = view.reduce.get("about_merges")
    if groups is None:
        return None
    for g in groups:
        keys = {g.get("canonical"), *g.get("merged", [])}
        if a in keys and b in keys:
            return True
    return False


def score_merge(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("merge")
    try:
        rd = manifest.run_day(day)
    except KeyError:
        sm.notes.append(f"no run_day {day} in manifest")
        return sm
    included = [ei for ei in rd.items if ei.include]
    allowed = Counter(ei.about for ei in included)
    matched_by: dict[str, set[str]] = {}          # rendered item id → expected keys it matches
    dupes = 0
    for key, n in allowed.items():
        cites = sorted({s for ei in included if ei.about == key for s in ei.cites_any})
        hits = select_items(view, manifest, {"about": key}, cites, day)
        for it in hits:
            matched_by.setdefault(it.id, set()).add(key)
        if len(hits) > n:
            dupes += 1
            sm.misses.append(Miss(f"{key}: rendered {len(hits)}×", f"{n}×",
                                  [f"{i.id}({i.placement})" for i in hits], view.link("reduce"), "merge"))
    over = 0
    for iid, keys in sorted(matched_by.items()):
        distinct = []
        for k in sorted(keys):
            if not any(about_match(k, d) for d in distinct):
                distinct.append(k)
        if len(distinct) > 1:
            over += 1
            sm.misses.append(Miss(f"{iid}: one item for {len(distinct)} expected items", "separate items", distinct,
                                  view.link("reduce"), "merge"))

    merge_ok = merge_n = unlogged = 0
    for pairs, want in ((manifest.about_keys.should_merge, True), (manifest.about_keys.should_not_merge, False)):
        for a, b in pairs:
            got = _merged(view, a, b)
            if got is None:
                unlogged += 1
                continue
            merge_n += 1
            if got == want:
                merge_ok += 1
            else:
                sm.misses.append(Miss(f"about merge {a} ~ {b}", "merge" if want else "keep apart",
                                      "merged" if got else "apart", view.link("reduce"), "merge"))
    if unlogged:
        sm.notes.append(f"{unlogged} about-key pairs not scoreable: reduce.json has no about_merges log")
    sm.metrics = {
        "expected_items_rendered_twice": dupes,
        "items_merging_expected_items": over,
        "expected_keys_checked": len(allowed),
        "about_merge_accuracy": rate(merge_ok, merge_n),
        "about_merge_pairs_unlogged": unlogged,
    }
    return sm
