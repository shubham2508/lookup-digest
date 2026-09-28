"""Extraction metrics (eval.md §2.1), per manifest item that carries an `expected` extraction."""
from __future__ import annotations

from rapidfuzz import fuzz

from eval.manifest_schema import Manifest

from .artifacts import Row, RunView
from .common import Miss, StageMetrics, prf, rate
from .match import about_match, date_within, evidence_refs, expected_dt, majority_source, norm_text


def _payload(row: Row) -> dict:
    return row.data.get("payload") or {}


def match_extractions(view: RunView, manifest: Manifest) -> dict[str, Row]:
    """manifest source_id → the extraction row about it (own id if known, else majority of its evidence)."""
    out: dict[str, Row] = {}
    for r in view.extractions:
        sid = majority_source(view.index, evidence_refs(r.data), r.data.get("source_id"))
        if sid and sid not in out:
            out[sid] = r
    return out


class _Acc:
    def __init__(self) -> None:
        self.n = 0
        self.ok = 0

    def add(self, good: bool) -> None:
        self.n += 1
        self.ok += 1 if good else 0

    @property
    def value(self) -> float | None:
        return rate(self.ok, self.n)


def score_extraction(view: RunView, manifest: Manifest) -> StageMetrics:
    sm = StageMetrics("extraction")
    by_src = match_extractions(view, manifest)
    acc = {k: _Acc() for k in ("type", "domain", "intent_primary", "ball_awaiting", "closed_by_courtesy",
                               "automated_action_kind", "note_kind")}
    com_tp = com_fp = com_fn = 0
    ask_tp = ask_fn = 0
    due = _Acc()
    recall = {k: _Acc() for k in ("schedule_mentions", "role_changes", "claims", "stage_signals", "agreements")}
    inj = _Acc()
    missing = 0

    for item in manifest.items:
        exp = item.expected
        if exp is None:
            continue
        row = by_src.get(item.source_id)
        if row is None:
            missing += 1
            acc["type"].add(False)
            sm.misses.append(Miss(f"{item.source_id}: no extraction", exp.type, None, view.link("extractions"), "extraction"))
            continue
        link = view.link("extractions", row.line)
        p = _payload(row)
        got_type = row.data.get("type")
        acc["type"].add(got_type == exp.type)
        if got_type != exp.type:
            sm.misses.append(Miss(f"{item.source_id}: type", exp.type, got_type, link, "extraction"))

        ball = p.get("ball") or {}
        fields = [("domain", exp.domain, p.get("domain")),
                  ("intent_primary", exp.intent_primary, p.get("intent_primary")),
                  ("ball_awaiting", exp.ball_awaiting, ball.get("awaiting")),
                  ("closed_by_courtesy", exp.closed_by_courtesy, ball.get("closed_by_courtesy")),
                  ("automated_action_kind", exp.automated.action_kind if exp.automated else None, p.get("action_kind")),
                  ("note_kind", exp.note_kind, p.get("note_kind"))]
        for name, want, got in fields:
            if want is None:
                continue
            acc[name].add(want == got)
            if want != got:
                sm.misses.append(Miss(f"{item.source_id}: {name}", want, got, link, "extraction"))

        # commitments: about key (fuzzy) + owner; due date within the granularity the extractor claimed
        got_coms = list(p.get("commitments", [])) + list(p.get("action_items", []))
        used: set[int] = set()
        for ec in exp.commitments:
            hit = next((i for i, gc in enumerate(got_coms) if i not in used and gc.get("owner") == ec.owner
                        and about_match(gc.get("about"), ec.about)), None)
            if hit is None:
                com_fn += 1
                sm.misses.append(Miss(f"{item.source_id}: commitment {ec.owner} {ec.about}", "present", "missing", link, "extraction"))
                continue
            used.add(hit)
            com_tp += 1
            gd = got_coms[hit].get("due") or {}
            ok = date_within(gd.get("resolved"), expected_dt(manifest, ec.due_day, ec.due_time), gd.get("granularity"))
            if ok is not None:
                due.add(ok)
                if not ok:
                    sm.misses.append(Miss(f"{item.source_id}: commitment due {ec.about}",
                                          str(expected_dt(manifest, ec.due_day, ec.due_time)), gd.get("resolved"), link, "extraction"))
        com_fp += len(got_coms) - len(used)

        # asks carry no about key: match on kind + to_avery
        got_asks = list(p.get("asks", []))
        used = set()
        for ea in exp.asks:
            hit = next((i for i, ga in enumerate(got_asks) if i not in used and ga.get("kind") == ea.kind
                        and bool(ga.get("to_avery")) == ea.to_avery), None)
            if hit is None:
                ask_fn += 1
                sm.misses.append(Miss(f"{item.source_id}: ask {ea.kind}", "present", "missing", link, "extraction"))
            else:
                used.add(hit)
                ask_tp += 1

        # planted facts: recall only
        for em in exp.schedule_mentions:
            ok = any(g.get("action") == em.action and (em.when_day is None or date_within(
                (g.get("when") or {}).get("resolved"), expected_dt(manifest, em.when_day, em.when_time), "day"))
                for g in p.get("schedule_mentions", []))
            recall["schedule_mentions"].add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: schedule {em.action} day {em.when_day}", "present", "missing", link, "extraction"))
        for er in exp.role_changes:
            ok = any(norm_text(g.get("person", "")) == norm_text(er.person) for g in p.get("role_changes", []))
            recall["role_changes"].add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: role change {er.person}", "present", "missing", link, "extraction"))
        for ecl in exp.claims:
            ok = any(norm_text(g.get("subject", "")) == norm_text(ecl.subject)
                     and norm_text(ecl.value) in norm_text(g.get("value", "")) for g in p.get("claims", []))
            recall["claims"].add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: claim {ecl.subject}={ecl.value}", "present", "missing", link, "extraction"))
        for es in exp.stage_signals:
            ok = any(g.get("stage") == es.stage and fuzz.partial_ratio(norm_text(es.entity), norm_text(
                (g.get("entity") or {}).get("name", ""))) >= 85 for g in p.get("stage_signals", []))
            recall["stage_signals"].add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: stage {es.entity}→{es.stage}", "present", "missing", link, "extraction"))
        for eg in exp.agreements:
            ok = any(eg.cadence is None or g.get("cadence") == eg.cadence for g in p.get("agreements", []))
            recall["agreements"].add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: agreement {eg.rule}", "present", "missing", link, "extraction"))
        if exp.suspicious:
            ok = bool(p.get("suspicious_instructions"))
            inj.add(ok)
            if not ok:
                sm.misses.append(Miss(f"{item.source_id}: suspicious_instructions", "flagged", "not flagged", link, "extraction"))

    # evidence validity (degradations.jsonl, OPEN_QUESTIONS #6e): `evidence_invalid` = fact dropped for a
    # non-substring quote; `evidence_replaced` = a required singleton's quote swapped for a verbatim span
    reasons = [str(d.data.get("reason", "")) for d in view.degradations if d.data.get("stage") == "extract"]
    dropped = sum(1 for r in reasons if r == "evidence_invalid" or ("quote" in r and "replace" not in r))
    replaced = sum(1 for r in reasons if r == "evidence_replaced")
    kept = sum(len(evidence_refs(r.data.get("payload") or {})) for r in view.extractions)

    sm.metrics = {
        **{f"{k}_accuracy": a.value for k, a in acc.items()},
        "commitments": prf(com_tp, com_fp, com_fn),
        "asks_recall": rate(ask_tp, ask_tp + ask_fn),
        "due_date_accuracy": due.value,
        **{f"{k}_recall": a.value for k, a in recall.items()},
        "evidence_validity": rate(kept - replaced, kept + dropped),
        "evidence_dropped": dropped,
        "evidence_replaced": replaced,
        "injection_recall": inj.value,
        "items_labeled": sum(1 for i in manifest.items if i.expected),
        "items_without_extraction": missing,
    }
    return sm
