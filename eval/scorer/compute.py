"""Contacts / compute metrics (eval.md §2.2): relationship truth per contact, about-key merges, candidates."""
from __future__ import annotations

from eval.manifest_schema import ContactLabel, Manifest

from .artifacts import RunView
from .common import Miss, StageMetrics, prf, rate
from .match import about_match, split_about, type_matches


def stage_on(label: ContactLabel, day: int) -> str | None:
    cur = None
    for s in sorted(label.stages, key=lambda s: s.from_day):
        if s.from_day <= day:
            cur = s.stage
    return cur


def _merged(view: RunView, a: str, b: str) -> bool | None:
    """Did compute treat a and b as one key? None if the run logged no merges and the keys differ."""
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


def score_compute(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("compute")
    link = view.link("contacts")
    cat = sub = stg = tier = 0
    n_cat = n_sub = n_stg = n_tier = 0
    for label in manifest.contacts:
        got = view.contact_by_email(label.email)
        rel = (got or {}).get("relationship") or {}
        n_cat += 1
        if got and rel.get("category") == label.category:
            cat += 1
        else:
            sm.misses.append(Miss(f"contact {label.email}: category", label.category, rel.get("category") if got else "no contact", link, "compute"))
        if label.subtype:
            n_sub += 1
            if rel.get("subtype") == label.subtype:
                sub += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: subtype", label.subtype, rel.get("subtype"), link, "compute"))
        want_stage = stage_on(label, day)
        if want_stage:
            n_stg += 1
            if rel.get("stage") == want_stage:
                stg += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: stage day {day}", want_stage, rel.get("stage"), link, "compute"))
        if label.tier:
            n_tier += 1
            if got and got.get("tier") == label.tier:
                tier += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: tier", label.tier, (got or {}).get("tier"), link, "compute"))

    merge_ok = merge_n = 0
    merge_unlogged = 0
    for pairs, want in ((manifest.about_keys.should_merge, True), (manifest.about_keys.should_not_merge, False)):
        for a, b in pairs:
            got = _merged(view, a, b)
            if got is None:
                merge_unlogged += 1
                continue
            merge_n += 1
            if got == want:
                merge_ok += 1
            else:
                sm.misses.append(Miss(f"about merge {a} ~ {b}", "merge" if want else "keep apart",
                                      "merged" if got else "apart", view.link("reduce"), "compute"))

    # candidates vs run_days[].candidates: type exact (prefix for calendar_conflict) + about fuzzy
    tp = fn = 0
    matched_rows: set[int] = set()
    try:
        expected = manifest.run_day(day).candidates
    except KeyError:
        expected = []
    for ec in expected:
        hit = next((r for r in view.candidates if r.line not in matched_rows and type_matches(r.data.get("type"), ec.type)
                    and about_match(r.data.get("about"), ec.about)), None)
        if hit is None:
            fn += 1
            sm.misses.append(Miss(f"candidate {ec.type} {ec.about}", "present", "missing", view.link("candidates"), "compute"))
        else:
            tp += 1
            matched_rows.add(hit.line)
            for k, v in ec.facts_hint.items():
                if hit.data.get("facts", {}).get(k) != v:
                    sm.misses.append(Miss(f"candidate {ec.type} {ec.about}: facts.{k}", v, hit.data.get("facts", {}).get(k),
                                          view.link("candidates", hit.line), "compute"))
    fp = len(view.candidates) - len(matched_rows)

    sm.metrics = {
        "contact_category_accuracy": rate(cat, n_cat),
        "contact_subtype_accuracy": rate(sub, n_sub),
        "contact_stage_accuracy": rate(stg, n_stg),
        "contact_tier_accuracy": rate(tier, n_tier),
        "about_merge_accuracy": rate(merge_ok, merge_n),
        "about_merge_pairs_unlogged": merge_unlogged,
        "candidates": prf(tp, fp, fn),
    }
    if merge_unlogged:
        sm.notes.append(f"{merge_unlogged} about-key pairs not scoreable: reduce.json has no about_merges log")
    return sm
