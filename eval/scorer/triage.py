"""Judgment diagnostics on `triage.jsonl` (eval.md §2.3, MIGRATION_PLAN §1): include P/R, priority and action-type
confusion, sections, question cards, and the hard-rule checks.

In v2 `triage.jsonl` is the Finding → TriageResult mapping after the code floors (digest/findings.py `to_triage`,
then `enforce`): include ← needs_avery, priority, section, actions, ambiguity come from the reader, sweep or net that
found the item. A miss is attributed to that finding's stage (read / sweep / net), or to `net` when the finding was
right and the code floors changed it. Diagnostics, not targets.

Hard rules checked on every included row: no reply / forward / decide draft action to a never-draft contact
(Sam, cold inbound, recruiters: `message_person` instead), suspicious content never P0, at least one citation.
"""
from __future__ import annotations

from collections import Counter

from eval.manifest_schema import ExpectedItem, Manifest

from .artifacts import Row, RunView
from .common import (
    Miss,
    StageMetrics,
    claimed_abouts,
    contact_label,
    is_never_draft,
    prf,
    rate,
    sender_emails,
    signals_for_expected,
)
from .match import PRIORITY_ORDER, max_priority

PRIORITIES = ("P0", "P1", "P2", "P3")
DRAFT_ACTIONS = ("reply", "forward_delegate", "decide")


def triage_rows_for(view: RunView, about: str, cites_any: list[str], claimed: list[str] | None = None) -> list[Row]:
    rows: list[Row] = []
    for s in signals_for_expected(view, about, cites_any, claimed):
        if s.candidate_id:
            rows.extend(view.triage_for(s.candidate_id))
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


def _stage_of(view: RunView, rows: list[Row]) -> str:
    """The stage of the finding behind these triage rows (read if unknown)."""
    from .attribution import lead_signal  # attribution imports this module

    sigs = [s for r in rows for s in view.signals_for(r.data.get("candidate_id"))]
    lead = lead_signal(sigs)
    return lead.stage if lead else "read"


def hard_rule_violations(view: RunView, manifest: Manifest) -> list[Miss]:
    out: list[Miss] = []
    for r in view.triage:
        d = r.data
        if not d.get("include"):
            continue
        link = view.link("triage", r.line)
        cid = d.get("candidate_id")
        for a in d.get("proposed_actions", []):
            if a.get("type") in DRAFT_ACTIONS and is_never_draft(manifest, a.get("target")):
                out.append(Miss(f"{cid}: {a['type']} to never-draft contact {a.get('target')}", "message_person",
                                a["type"], link, "net"))
        sigs = view.signals_for(cid)
        if d.get("priority") == "P0" and (any(s.suspicious for s in sigs) or (view.candidate(cid) or Row({}, 0)).data.get("type") == "suspicious_content"):
            out.append(Miss(f"{cid}: suspicious content at P0", "never P0", "P0", link, "net"))
        if not d.get("citations"):
            out.append(Miss(f"{cid}: included without a citation", "≥1 citation", 0, link, "net"))
    return out


def score_triage(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("judgment")
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
        claimed = claimed_abouts(manifest, day, ei.about)
        rows = triage_rows_for(view, ei.about, ei.cites_any, claimed)
        out = triage_outcome(rows)
        link = view.link("triage", out["line"]) if out["line"] else view.link("triage")
        stage = _stage_of(view, rows)
        if not ei.include:
            if out["include"]:
                fp += 1
                sm.misses.append(Miss(f"{ei.about}: included, expected excluded", False, True, link, stage))
            continue
        if not rows:
            fn += 1  # no finding reached triage: the reader, sweep or net that should have noticed it
            from .attribution import attribute_missing

            att = attribute_missing(view, manifest, ei.about, ei.cites_any)
            sm.misses.append(Miss(f"{ei.about}: never surfaced ({att.evidence})", "include", "no candidate",
                                  att.links[0] if att.links else view.link("findings"), att.stage))
            continue
        if not out["include"]:
            fn += 1
            sm.misses.append(Miss(f"{ei.about}: excluded", "include", "exclude", link, stage))
            continue
        tp += 1
        if ei.priority or ei.priority_band:
            prio_n += 1
            want = ei.priority or ei.priority_band[0]
            confusion.setdefault(want, Counter())[out["priority"] or "none"] += 1
            if priority_ok(ei, out["priority"]):
                prio_ok += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: priority", ei.priority or ei.priority_band, out["priority"], link, stage))
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
                sm.misses.append(Miss(f"{ei.about}: section", ei.section, out["section"], link, stage))
        for a in ei.actions:
            act_n += 1
            got = a if a in out["actions"] else (out["actions"][0] if out["actions"] else "none")
            act_conf.setdefault(a, Counter())[got] += 1
            if a in out["actions"]:
                act_hit += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: proposed action {a}", a, out["actions"], link, stage))
        if ei.ambiguity:
            amb_n += 1
            amb = out["ambiguity"] or {}
            if amb.get("type") == ei.ambiguity:
                amb_ok += 1
            else:
                sm.misses.append(Miss(f"{ei.about}: ambiguity type", ei.ambiguity, amb.get("type"), link, stage))
            opts = amb.get("options") or []
            if isinstance(amb.get("default"), int) and 1 <= amb["default"] <= len(opts):
                dflt_ok += 1

    # included results that land on labeled noise or on keys that must be absent
    for about in rd.absent:
        rows = triage_rows_for(view, about, [])
        if triage_outcome(rows)["include"]:
            fp += 1
            sm.misses.append(Miss(f"{about}: included, expected absent", False, True, view.link("triage"), _stage_of(view, rows)))
    for sid in rd.noise_source_ids:
        rows = [t for s in view.signals if s.candidate_id and sid in s.sources for t in view.triage_for(s.candidate_id)]
        inc = [r for r in rows if r.data.get("include")]
        if inc:
            fp += 1
            sm.misses.append(Miss(f"noise {sid}: included", False, True, view.link("triage", inc[0].line), _stage_of(view, inc)))

    hard = hard_rule_violations(view, manifest)
    sm.misses += hard
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
        "hard_rule_violations": len(hard),
    }
    return sm
