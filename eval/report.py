"""eval/reports/<world>_<date>.md in the eval.md §9 layout, rewired for v2 (PIVOT_SPEC §6).

1. Summary: v1 / v2 / baseline on dev and held-out (P0 recall, traps, must-not rate, one thing, judge, cost).
   v1 is fixed (eval/v1_results.yaml); v2 and the baseline are scored from the runs on disk.
2. Diagnostics per run day: the digest-level metrics (the target), then where it failed: readers, sweeps and
   nets (with the rescue list), merge, judgment (triage.jsonl + hard rules), the contact spine, the materializer.
3. Failed assertions, each with its stage and artifact links.
4. Customize and variant results.
5. Judge (reported, not gated), 6. multi-day simulation, 7. label audit.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from eval.judge.judge import RUBRICS, Calibration, JudgeRun
from eval.manifest_schema import Manifest
from eval.scorer.assertions import AssertionResult
from eval.scorer.common import STAGES
from eval.scorer.runner import SECTIONS, WorldScore

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
V1_RESULTS = Path(__file__).resolve().parent / "v1_results.yaml"
HEADLINE_ROWS = [
    ("P0 recall (gate = 100%)", "p0_recall"),
    ("Trap assertions passed", "traps_passed"),
    ("Must-not rate", "must_not_rate"),
    ("One-thing accuracy", "one_thing_accuracy"),
    ("Judge · digest (3 questions / no noise / honest)", "judge_digest"),
    ("Judge · drafts (facts / tone / assumptions)", "judge_draft"),
    ("Cost / run (USD)", "cost_per_run"),
    ("Runs scored", "runs_scored"),
]
WORLDS = ("dev", "heldout")
SECTION_TITLES = {"digest": "digest (the target)", "read": "read · thread readers", "sweep": "sweep & net · planted traps, rescues",
                  "merge": "merge", "judgment": "judgment · triage.jsonl after the code floors", "spine": "spine · contacts",
                  "materialize": "materialize"}


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "pass" if v else "**FAIL**"
    if isinstance(v, float):
        return f"{v:.4g}" if v not in (0.0, 1.0) else f"{v:.0%}"
    if isinstance(v, dict) and {"precision", "recall"} <= set(v):
        return f"P {_fmt(v['precision'])} · R {_fmt(v['recall'])} (tp {v['tp']}, fp {v['fp']}, fn {v['fn']})"
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_fmt(x)}" for k, x in v.items()) or "—"
    if isinstance(v, list):
        return "; ".join(map(str, v)) or "none"
    return str(v)


def report_name(world: str, on: date | None = None, suffix: str | None = None) -> str:
    slug = world.strip("/").replace("/", "_")
    return f"{slug}_{(on or date.today()).isoformat()}{'_' + suffix if suffix else ''}.md"


def load_v1_results(path: Path | None = None) -> dict:
    p = path or V1_RESULTS
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def judge_means(judge: JudgeRun | None, kind: str, baseline: bool) -> str | None:
    """'4.2 / 3.8 / 4.5' in rubric order, over the judged items of one column (baseline items are `baseline/…`)."""
    if judge is None or judge.status != "ok":
        return None
    vals: dict[str, list[int]] = {}
    for r in judge.results:
        if r.kind != kind or r.item_id.startswith("baseline/") != baseline:
            continue
        for k, v in r.scores.items():
            vals.setdefault(k, []).append(v)
    if not vals:
        return None
    return " / ".join(f"{sum(vals[c]) / len(vals[c]):.1f}" if vals.get(c) else "—" for c in RUBRICS[kind])


def _cell(key: str, head: dict | None, fixed: dict | None, judge_cell: tuple[str | None, str | None]) -> str:
    """One table cell: the live headline when scored, else the fixed v1-era number (marked †)."""
    if key in ("judge_digest", "judge_draft"):
        v = judge_cell[0 if key == "judge_digest" else 1]
        return v if v else "—"
    if head is not None:
        v = head.get(key)
        if key == "cost_per_run":
            return f"${v:.4f}" if v is not None else "—"
        cell = _fmt(v)
        if key == "p0_recall":
            cell = f"{cell} {'✅' if head.get('p0_gate') else ('❌' if head.get('p0_gate') is False else '')}".strip()
        return cell
    if fixed is None:
        return "not run"
    v = fixed.get(key)
    if key == "cost_per_run":
        cell = f"${v:.4f}" if v is not None else "—"
        note = fixed.get("cost_note")
        return f"{cell} ({note})" if note else cell
    return _fmt(v)


def _summary(world: str, scores: dict[tuple[str, str], WorldScore], judge: JudgeRun | None,
             v1: dict | None = None) -> list[str]:
    """The v1 / v2 / baseline comparison table (PIVOT_SPEC §6), dev and held-out."""
    v1 = load_v1_results() if v1 is None else v1
    here = "heldout" if "heldout" in world else "dev"
    cols: list[tuple[str, str]] = []
    for w in WORLDS:
        cols += [("v1", w), ("v2", w), ("baseline", w)]
    extra = [k for k in scores if k[1] not in WORLDS]  # fixture worlds: their own v2 / baseline columns
    cols += [("v2" if k == "pipeline" else k, w) for k, w in extra]
    lines = ["| metric | " + " | ".join(f"{a} · {b}" for a, b in cols) + " |", "|---|" + "---|" * len(cols)]
    fallback_baseline = []
    for label, key in HEADLINE_ROWS:
        row = []
        for kind, w in cols:
            if kind == "v1":
                row.append(_cell(key, None, (v1.get("v1") or {}).get(w), (None, None)))
                continue
            ws = scores.get(("pipeline" if kind == "v2" else "baseline", w))
            head = ws.headline() if ws is not None and ws.runs else None
            jc = (judge_means(judge, "digest", kind == "baseline"), judge_means(judge, "draft", kind == "baseline")) \
                if w == here else (None, None)
            fixed = (v1.get("baseline") or {}).get(w) if kind == "baseline" and head is None else None
            if fixed is not None and key == HEADLINE_ROWS[0][1]:
                fallback_baseline.append(w)
            cell = _cell(key, head, fixed, jc)
            dagger = fixed is not None and not key.startswith("judge_") and cell not in ("—", "not run")
            row.append(f"{cell} †" if dagger else cell)
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("v1 is fixed from the v1 tag's final reports (`eval/v1_results.yaml`); v2 is scored from the runs on disk."
                 + (f" † baseline from the v1-era run ({', '.join(fallback_baseline)}): no baseline run on disk."
                    if fallback_baseline else "")
                 + " Judge cells are rubric means (1–5) for the world this report is about.")
    rescored = v1.get("rescored_with_v2_scorer") or {}
    if rescored:
        def line(kind: str) -> str:
            return "; ".join(f"{w} {_fmt(r.get('p0_recall'))} · {r.get('traps_passed')} · {_fmt(r.get('must_not_rate'))} · "
                             f"{_fmt(r.get('one_thing_accuracy'))}" for w, r in (rescored.get(kind) or {}).items())
        lines.append(f"\nThe v1 runs rescored with this scorer (P0 · traps · must-not · one thing): v1 {line('v1')}; "
                     f"baseline {line('baseline')}.")
    return lines


def _stage_section(ws: WorldScore) -> list[str]:
    out = []
    by_stage: Counter = Counter()
    for day, rs in sorted(ws.runs.items()):
        out.append(f"### Day {day} · `{rs.run_dir}`")
        if rs.missing_artifacts:
            out.append(f"Missing artifacts: {', '.join(rs.missing_artifacts)}")
        for section in SECTIONS:
            sm = rs.stages.get(section)
            if sm is None:
                continue
            out.append(f"\n**{SECTION_TITLES.get(section, section)}**\n")
            out.append("| metric | value |")
            out.append("|---|---|")
            for k, v in sm.metrics.items():
                out.append(f"| {k} | {_fmt(v)} |")
            for name, items in sm.lists.items():
                out.append(f"\n{name}:")
                out += [f"- {x}" for x in items]
            for n in sm.notes:
                out.append(f"\n_{n}_")
            if sm.misses:
                out.append("\nMisses:")
                for m in sm.misses:
                    st = m.stage or section
                    by_stage[st] += 1
                    link = f" · [{m.link}]({m.link})" if m.link else ""
                    out.append(f"- [{st}] {m.what}: expected `{_fmt(m.expected)}`, got `{_fmt(m.got)}`{link}")
        out.append("")
    if by_stage:
        order = list(STAGES) + sorted(s for s in by_stage if s not in STAGES)
        out.insert(0, "Misses by attributed stage: " + ", ".join(f"{s} {by_stage[s]}" for s in order if by_stage[s]) + "\n")
    return out


def _assertion_lines(results: list[AssertionResult]) -> list[str]:
    lines = []
    for a in results:
        links = " ".join(f"[{link.rsplit('/', 1)[-1]}]({link})" for link in a.artifact_links)
        tag = " ".join(t for t in (a.storyline, f"day {a.run_day}" if a.run_day else None,
                                   a.variant and f"variant {a.variant}", a.customize and f"customize {a.customize}") if t)
        lines.append(f"- **{a.id}** (`{a.kind}`; {tag}) → stage **{a.attributed_stage or '?'}**: {a.evidence} {links}".rstrip())
    return lines


def _conditions_section(conditions: list, loose: list[AssertionResult]) -> list[str]:
    """One row per condition (eval.md §5 honesty variants, storyline variants, §6 customize suite)."""
    if not conditions and not loose:
        return ["No customize or variant conditions defined for this world."]
    L = ["| condition | kind | runs | P0 recall | assertions | checks | status |", "|---|---|---|---|---|---|---|"]
    for c in conditions:
        judged = [a for a in c.assertions if a.passed is not None]
        ok = sum(1 for a in judged if a.passed)
        checks = "; ".join(f"{k}: {_fmt(v)}" for k, v in c.checks.items() if k != "passed") or "—"
        days = ", ".join(map(str, c.days)) or "—"
        status = {"pass": "pass", "fail": "**FAIL**", "not run": "not run"}[c.status]
        L.append(f"| {c.id} | {c.kind} | {days} | {_fmt(c.headline.get('p0_recall'))} | "
                 f"{ok}/{len(judged)}{f' ({len(c.assertions) - len(judged)} not run)' if len(judged) < len(c.assertions) else ''} "
                 f"| {checks} | {status} |")
    failed = [(c, a) for c in conditions for a in c.assertions if a.passed is False] + [(None, a) for a in loose if a.passed is False]
    if failed:
        L += ["", "Failed:", ""]
        for c, a in failed:
            links = " ".join(f"[{link.rsplit('/', 1)[-1]}]({link})" for link in a.artifact_links)
            where = f"{c.kind} {c.id}" if c else (a.variant or a.customize)
            L.append(f"- **{a.id}** ({where}, `{a.kind}`) → stage **{a.attributed_stage or '?'}**: {a.evidence} {links}".rstrip())
    notes = [f"- {c.id}: {n}" for c in conditions for n in c.notes if c.days]
    if notes:
        L += ["", "Notes:", "", *notes]
    return L


def _simulation_section(ws: WorldScore) -> list[str]:
    multi = {"ruling_applied", "escalation_framing", "resolved_disappears", "content_overrides_ruling"}
    manifest_multi = [a for a in ws.assertions if a.kind in multi]
    if ws.simulation is None and not manifest_multi:
        return ["Not run: no `simulation.json` (run `digest simulate --world <world> --days 5`)."]
    L = []
    if ws.simulation is not None:
        judged = [a for a in ws.simulation if a.passed is not None]
        L.append(f"Generic checks: {sum(1 for a in judged if a.passed)}/{len(judged)} passed.")
        L += [""] + [f"- {'pass' if a.passed else ('not run' if a.passed is None else '**FAIL**')} · **{a.id}**"
                     f"{' → stage **' + str(a.attributed_stage) + '**' if a.passed is False else ''}: {a.evidence}"
                     for a in ws.simulation]
    if manifest_multi:
        L += ["", "Manifest multi-day assertions (also counted in §3):", ""]
        L += [f"- {'pass' if a.passed else ('not run' if a.passed is None else '**FAIL**')} · **{a.id}** (`{a.kind}`): {a.evidence}"
              for a in manifest_multi]
    return L


def render_report(world: str, scores: dict[tuple[str, str], WorldScore], manifest: Manifest,
                  judge: JudgeRun | None = None, calibration: Calibration | None = None, on: date | None = None) -> str:
    label = "heldout" if "heldout" in world else "dev"   # detail the world this report is for, not always dev
    main = scores.get(("pipeline", label)) or next(iter(scores.values()))
    base = [a for a in main.assertions if not a.variant and not a.customize]
    extra = [a for a in main.assertions if a.variant or a.customize]
    failed = [a for a in base if a.passed is False]
    not_run = [a for a in base if a.passed is None]
    passed = [a for a in base if a.passed]

    L = [f"# Eval report · {world} · {(on or date.today()).isoformat()}", ""]
    L += [f"Manifest world `{manifest.meta.world}`, anchor {manifest.meta.anchor} (day 30), run days {manifest.meta.run_days}. "
          "P0 recall is the only gate; everything else is reported.", ""]
    for n in main.notes:
        L += [f"> {n}", ""]
    L += ["## 1. Summary: v1 / v2 / baseline", ""] + _summary(world, scores, judge) + [""]
    L += ["## 2. Diagnostics (PIVOT_SPEC §6: where it failed; §1 is the target)", ""] + _stage_section(main)
    L += ["## 3. Trap assertions", "",
          f"{len(passed)} passed · {len(failed)} failed · {len(not_run)} not run.", ""]
    if failed:
        L += ["### Failed", ""] + _assertion_lines(failed) + [""]
    if not_run:
        L += ["### Not run", ""] + [f"- **{a.id}** (`{a.kind}`): {a.evidence}" for a in not_run] + [""]
    if passed:
        L += ["<details><summary>Passed</summary>", ""] + [f"- {a.id} (`{a.kind}`): {a.evidence}" for a in passed] + ["", "</details>", ""]
    for (kind, w), ws in scores.items():
        if kind != "baseline" or not ws.runs:
            continue
        L += [f"### Naive baseline · {w} (eval.md §8: one long-context call, scored on digest-level metrics only)", ""]
        bf = [a for a in ws.assertions if a.passed is False]
        na = sum(1 for a in ws.assertions if a.passed is None)
        L.append(f"{sum(1 for a in ws.assertions if a.passed)} passed · {len(bf)} failed · {na} n/a (need pipeline artifacts).")
        L += [""] + [f"- **{a.id}** (`{a.kind}`): {a.evidence}" for a in bf]
        for day, rs in sorted(ws.runs.items()):
            for stage in ("digest", "materialize"):
                for m in rs.stages[stage].misses:
                    L.append(f"- day {day} · {stage}: {m.what}: expected `{_fmt(m.expected)}`, got `{_fmt(m.got)}`")
            c = rs.stages["digest"].metrics
            L.append(f"- day {day} · citations valid {_fmt(c.get('md_citations_valid_rate'))}, words {c.get('words')}")
        L.append("")
    L += ["## 4. Customize and variant results", ""] + _conditions_section(main.conditions, extra)
    L += ["", "## 5. Judge (E1, reported, not gated)", ""]
    if judge is None or judge.status == "skipped":
        L.append(f"judge: skipped ({judge.note if judge else 'not requested'})")
    else:
        L.append(f"Role `{judge.role}`, {len(judge.results)} item(s). Means: {_fmt(judge.means())}.")
        errs = [r for r in judge.results if r.error]
        if errs:
            L.append(f"{len(errs)} item(s) not scored: " + "; ".join(f"{r.item_id}: {r.error}" for r in errs[:5]))
        L += ["", "| item | " + " | ".join(["criterion", "score", "reason"]) + " |", "|---|---|---|---|"]
        for r in judge.results:
            for k, v in r.scores.items():
                L.append(f"| {r.item_id} | {k} | {v} | {r.reasons.get(k, '')} |")
    if calibration is not None:
        L += ["", "### Judge calibration (one-time)", "", calibration.to_markdown()]
    L += ["", "## 6. Multi-day simulation (eval.md §7)", ""] + _simulation_section(main)
    la = manifest.label_audit
    L += ["", "## 7. Label audit", ""]
    if la.sample_size:
        L.append(f"{la.sample_size} generator labels hand-checked by {la.checked_by or '?'} on {la.checked_on or '?'}; "
                 f"{len(la.corrections)} correction(s)" + (": " + "; ".join(la.corrections) if la.corrections else "."))
    else:
        L.append("Not done yet: ~30 labels to hand-check (eval.md §9.5).")
    return "\n".join(L) + "\n"


def write_report(text: str, name: str, out_dir: Path | None = None) -> Path:
    d = out_dir or REPORTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(text, encoding="utf-8")
    return p
