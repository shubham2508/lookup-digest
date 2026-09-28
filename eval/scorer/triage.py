"""Triage metrics (eval.md §2.3): include P/R, priority and action-type confusion, sections, question cards."""
from __future__ import annotations

from collections import Counter

from eval.manifest_schema import ExpectedItem, Manifest

from .artifacts import Row, RunView
from .common import (
    Miss,
    StageMetrics,
    candidates_for_expected,
    claimed_abouts,
    contact_label,
    prf,
    rate,
    sender_emails,
)
from .match import PRIORITY_ORDER, max_priority

PRIORITIES = ("P0", "P1", "P2", "P3")


def triage_rows_for(view: RunView, about: str, cites_any: list[str], claimed: list[str] | None = None) -> list[Row]:
    rows: list[Row] = []
    for c in candidates_for_expected(view, about, cites_any, claimed):
        rows.extend(view.triage_for(c.data.get("candidate_id")))
    return rows


def triage_outcome(rows: list[Row]) -> dict:
    inc = [r.data for r in rows if r.data.get("include")]
    best = min(inc, key=lambda d: PRIORITY_ORDER.get(d.get("priority"), 9)) if inc else None
    return {
        "include": bool(inc),
        "priority": max_priority(d.get("priority") for d in inc),
        "section": best.get("section") if best else None,
        "actions": [a.get("type") for d in inc for a in d.get("proposed_actions", [])],
        "ambiguity": next((d.get("ambiguity") for d in inc if d.get("ambiguity")), None),
        "line": rows[0].line if rows else None,
    }


def priority_ok(ei: ExpectedItem, got: str | None) -> bool:
    if ei.priority_band:
        return got in ei.priority_band
    return got == ei.priority


def score_triage(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("triage")
    try:
        rd = manifest.run_day(day)
    except KeyError:
        sm.notes.append(f"no run_day {day} in manifest")
        return sm

    tp = fp = fn = 0
    confusion: dict[str, Counter] = {p: Counter() for p in PRIORITIES}
    prio_ok = prio_n = sec_ok = sec_n = 0
    cells = {"up": [0, 0], "down": [0, 0]}  # [correct, total]
    act_conf: dict[str, Counter] = {}
    act_hit = act_n = 0
    amb_ok = amb_n = dflt_ok = 0

    for ei in rd.items:
        rows = triage_rows_for(view, ei.about, ei.cites_any, claimed_abouts(manifest, day, ei.about))
        out = triage_outcome(rows)
        link = view.link("triage", out["line"]) if out["line"] else view.link("triage")
        if not ei.include:
            if out["include"]:
                fp += 1
                sm.misses.append(Miss(f"{ei.about}: included, expected excluded", False, True, link, "triage"))
            continue
        if not rows:
            fn += 1  # no candidate reached triage: compute's miss, counted here as a recall loss too
            sm.misses.append(Miss(f"{ei.about}: never triaged (no candidate)", "include", "no candidate", view.link("candidates"), "compute"))
            continue
        if not out["include"]:
            fn += 1
            sm.misses.append(Miss(f"{ei.about}: excluded by triage", "include", "exclude", link, "triage"))
            continue
        tp += 1
        if ei.priority or ei.priority_band:
            prio_n += 1
            want = ei.priority or ei.priority_band[0]
            confusion.setdefault(want, Counter())[out["priority"] or "none"] += 1
            if priority_ok(ei, out["priority"]):
                prio_ok += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: priority", ei.priority or ei.priority_band, out["priority"], link, "triage"))
            # sender-vs-content cell: expected priority differs from the sender's tier
            senders = [s for sid in ei.cites_any for s in sender_emails(manifest, sid)]
            tier = next((c.tier for c in (contact_label(manifest, s) for s in senders) if c and c.tier), None)
            if tier and tier != want:
                d = "up" if PRIORITY_ORDER[want] < PRIORITY_ORDER[tier] else "down"
                cells[d][1] += 1
                cells[d][0] += 1 if priority_ok(ei, out["priority"]) else 0
        if ei.section:
            sec_n += 1
            if out["section"] == ei.section:
                sec_ok += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: section", ei.section, out["section"], link, "triage"))
        for a in ei.actions:
            act_n += 1
            got = a if a in out["actions"] else (out["actions"][0] if out["actions"] else "none")
            act_conf.setdefault(a, Counter())[got] += 1
            if a in out["actions"]:
                act_hit += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: proposed action {a}", a, out["actions"], link, "triage"))
        if ei.ambiguity:
            amb_n += 1
            amb = out["ambiguity"] or {}
            if amb.get("type") == ei.ambiguity:
                amb_ok += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: ambiguity type", ei.ambiguity, amb.get("type"), link, "triage"))
            opts = amb.get("options") or []
            if isinstance(amb.get("default"), int) and 1 <= amb["default"] <= len(opts):
                dflt_ok += 1

    # included triage results that land on labeled noise or on keys that must be absent
    for about in rd.absent:
        if triage_outcome(triage_rows_for(view, about, []))["include"]:
            fp += 1
            sm.misses.append(Miss(f"{about}: included, expected absent", False, True, view.link("triage"), "triage"))
    for sid in rd.noise_source_ids:
        rows = [t for c in view.candidates for t in view.triage_for(c.data.get("candidate_id"))
                if sid in view.index.resolve_all([e.get("source_id", "") for e in c.data.get("evidence", [])])]
        if any(r.data.get("include") for r in rows):
            fp += 1
            sm.misses.append(Miss(f"noise {sid}: included by triage", False, True, view.link("triage", rows[0].line), "triage"))

    sm.metrics = {
        "include": prf(tp, fp, fn),
        "priority_accuracy": rate(prio_ok, prio_n),
        "priority_confusion": {k: dict(v) for k, v in confusion.items() if v},
        "section_accuracy": rate(sec_ok, sec_n),
        "sender_vs_content_up": rate(*cells["up"]) if cells["up"][1] else None,
        "sender_vs_content_down": rate(*cells["down"]) if cells["down"][1] else None,
        "sender_vs_content_cells": cells["up"][1] + cells["down"][1],
        "action_recall": rate(act_hit, act_n),
        "action_confusion": {k: dict(v) for k, v in act_conf.items()},
        "ambiguity_type_accuracy": rate(amb_ok, amb_n),
        "question_default_present": rate(dflt_ok, amb_n),
    }
    return sm
