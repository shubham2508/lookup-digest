"""Entity-spine diagnostics (PIVOT_SPEC §6 "contact classification accuracy"): category, subtype, stage and tier per
labeled contact, read from `contacts.json`. Reported, never gated; misses are attributed to `spine`."""
from __future__ import annotations

from eval.manifest_schema import ContactLabel, Manifest

from .artifacts import RunView
from .common import Miss, StageMetrics, rate


def stage_on(label: ContactLabel, day: int) -> str | None:
    cur = None
    for s in sorted(label.stages, key=lambda s: s.from_day):
        if s.from_day <= day:
            cur = s.stage
    return cur


def score_spine(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("spine")
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
            sm.misses.append(Miss(f"contact {label.email}: category", label.category, rel.get("category") if got else "no contact", link, "spine"))
        if label.subtype:
            n_sub += 1
            if rel.get("subtype") == label.subtype:
                sub += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: subtype", label.subtype, rel.get("subtype"), link, "spine"))
        want_stage = stage_on(label, day)
        if want_stage:
            n_stg += 1
            if rel.get("stage") == want_stage:
                stg += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: stage day {day}", want_stage, rel.get("stage"), link, "spine"))
        if label.tier:
            n_tier += 1
            if got and got.get("tier") == label.tier:
                tier += 1
            else:
                sm.misses.append(Miss(f"contact {label.email}: tier", label.tier, (got or {}).get("tier"), link, "spine"))
    sm.metrics = {
        "contact_category_accuracy": rate(cat, n_cat),
        "contact_subtype_accuracy": rate(sub, n_sub),
        "contact_stage_accuracy": rate(stg, n_stg),
        "contact_tier_accuracy": rate(tier, n_tier),
    }
    return sm
