"""Score a world: every run day's artifacts against the manifest, every assertion, headline numbers.

Where runs live (digest/runs.py `RunContext.suffix`, OPEN_QUESTIONS #7c): runs/<world>/<as_of>[_<suffix>]/ with
- `<variant>` for honesty variants (stale_inbox, no_notes, corrupt_ics),
- `customize-<stem>` for customize-suite runs, `baseline` for the naive baseline, joined with `+` when combined,
and storyline variants as their own world, runs/<world>__<variant id>/. Conditions (variants, customize) are
scored in `conditions.py`; this module scores the default runs (or one suffix) and the base assertions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

from digest.paths import ROOT
from digest.runs import run_dir_name
from eval.manifest_schema import Manifest, load_manifest

from .artifacts import RunView
from .assertions import AssertionResult, CheckContext, run_assertions
from .common import StageMetrics
from .compute import score_compute
from .digest_metrics import score_digest, score_materializer
from .extraction import score_extraction
from .match import PT, SourceIndex
from .triage import score_triage

EVAL_DIR = Path(__file__).resolve().parents[1]


def manifest_path(world: str) -> Path:
    if "/" in world:
        p = Path(world)
        p = p if p.is_absolute() else ROOT / p
        return p / "manifest.yaml" if p.is_dir() else p
    return EVAL_DIR / "manifests" / f"{world}.yaml"


def as_of_for(manifest: Manifest, day: int) -> datetime:
    return datetime.combine(manifest.meta.day_to_date(day), time.fromisoformat(manifest.meta.as_of_time), tzinfo=PT)


def find_runs(manifest: Manifest, runs_root: Path, suffix: str | None = None) -> dict[int, Path]:
    out = {}
    for day in manifest.meta.run_days:
        d = runs_root / run_dir_name(as_of_for(manifest, day), suffix)
        if d.is_dir():
            out[day] = d
    return out


@dataclass
class RunScore:
    day: int
    run_dir: str
    stages: dict[str, StageMetrics]
    cost_usd: float | None
    missing_artifacts: list[str]


@dataclass
class WorldScore:
    world: str
    label: str
    runs: dict[int, RunScore] = field(default_factory=dict)
    assertions: list[AssertionResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    conditions: list = field(default_factory=list)  # conditions.ConditionScore
    simulation: list[AssertionResult] | None = None  # simulation.score_simulation, when simulation.json exists

    def headline(self) -> dict:
        return headline_of(self.runs, self.assertions)


def headline_of(runs: dict[int, RunScore], assertions: list[AssertionResult]) -> dict:
    """The eval.md §9.1 headline numbers over a set of run days and assertions."""
    p0_hit = p0_n = noise_hit = noise_n = one_ok = one_n = 0
    costs = []
    for r in runs.values():
        c = r.stages.get("compose")
        if c and c.metrics:
            n = c.metrics.get("p0_expected", 0)
            p0_n += n
            p0_hit += round((c.metrics.get("p0_recall") or 0) * n)
            if c.metrics.get("must_not_rate") is not None:
                noise_n += 1
                noise_hit += c.metrics["must_not_rate"]
            if c.metrics.get("one_thing_correct") is not None:
                one_n += 1
                one_ok += 1 if c.metrics["one_thing_correct"] else 0
        if r.cost_usd is not None:
            costs.append(r.cost_usd)
    judged = [a for a in assertions if a.passed is not None]
    return {
        "p0_recall": round(p0_hit / p0_n, 3) if p0_n else None,
        "p0_gate": (p0_hit == p0_n) if p0_n else None,
        "traps_passed": f"{sum(1 for a in judged if a.passed)}/{len(judged)}" if judged else None,
        "traps_not_run": sum(1 for a in assertions if a.passed is None),
        "must_not_rate": round(noise_hit / noise_n, 3) if noise_n else None,
        "one_thing_accuracy": round(one_ok / one_n, 3) if one_n else None,
        "cost_per_run": round(sum(costs) / len(costs), 4) if costs else None,
        "runs_scored": len(runs),
    }


def score_run(view: RunView, manifest: Manifest, day: int, digest_only: bool = False) -> RunScore:
    """All five stages; only compose (digest-level) + materializer for markdown-only runs or `digest_only`."""
    stages: dict[str, StageMetrics] = {}
    if not (digest_only or view.markdown_only):
        stages["extraction"] = score_extraction(view, manifest)
        stages["compute"] = score_compute(view, manifest, day)
        stages["triage"] = score_triage(view, manifest, day)
    stages["compose"] = score_digest(view, manifest, day)
    stages["materializer"] = score_materializer(view, manifest)
    return RunScore(day=day, run_dir=str(view.dir), stages=stages, cost_usd=view.cost.get("cost_usd"),
                    missing_artifacts=view.missing)


def _extraction_misses(score: RunScore | None) -> dict[str, list]:
    out: dict[str, list] = {}
    if score is None:
        return out
    for m in score.stages["extraction"].misses if "extraction" in score.stages else []:
        out.setdefault(m.what.split(":", 1)[0], []).append(m)
    return out


SIM_KINDS = {"ruling_applied", "escalation_framing", "resolved_disappears", "content_overrides_ruling"}


def load_views(manifest: Manifest, runs_root: Path, suffix: str | None = None) -> dict[int, RunView]:
    index = SourceIndex(manifest)
    return {d: RunView(p, index, ROOT, day=d) for d, p in find_runs(manifest, runs_root, suffix).items()}


def score_world(world: str, runs_root: Path | None = None, *, suffix: str | None = None, label: str = "pipeline",
                manifest: Manifest | None = None, customize_suite: bool = False, conditions: bool = True) -> WorldScore:
    """Score every run day found under runs_root (with `suffix`, if any) and the assertions that belong to it:
    the base assertions for the default runs and the baseline, that condition's assertions for a variant or
    customize suffix. With `conditions`, the default scoring also scores every variant and customize condition."""
    from .conditions import BUILTIN_VARIANTS, condition_assertions, score_conditions

    manifest = manifest or load_manifest(manifest_path(world))
    runs_root = runs_root or ROOT / "runs" / world
    views = load_views(manifest, runs_root, suffix)
    ws = WorldScore(world=manifest.meta.world, label=label)
    unlabeled = [i.source_id for i in manifest.items if i.kind in ("thread", "newsletter", "automated", "marketing")
                 and not i.messages]
    if unlabeled:
        ws.notes.append(f"{len(unlabeled)} manifest item(s) have no message labels, so product evidence cannot be mapped "
                        f"to them and absence checks on them pass vacuously: {', '.join(unlabeled[:8])}")
    if not views:
        ws.notes.append(f"no runs found under {runs_root} for days {manifest.meta.run_days} (suffix {suffix!r})")
    for day, view in sorted(views.items()):
        ws.runs[day] = score_run(view, manifest, day)
        ws.notes += [f"day {day}: malformed artifact: {m}" for m in view.malformed]
    ex_misses = _extraction_misses(ws.runs[max(ws.runs)] if ws.runs else None)

    if suffix in (None, "baseline"):
        base = [a for a in manifest.assertions if not a.variant and not a.customize]
        # OPEN_QUESTIONS #15: simulation runs live in *_sim dirs; multi-day (rulings, escalation) assertions read those,
        # everything else reads the plain, rulings-free runs. Older fixtures without *_sim dirs fall back to the plain views.
        sim_views = (load_views(manifest, runs_root, "sim") or views) if suffix is None else views
        sim_only = [a for a in base if a.kind in SIM_KINDS or a.args.get("mode") == "simulate"]
        plain = [a for a in base if a not in sim_only]
        ws.assertions += run_assertions(plain, CheckContext(manifest, views, ex_misses))
        if sim_only:
            ws.assertions += run_assertions(sim_only, CheckContext(manifest, sim_views, ex_misses))
        if suffix is None and conditions:
            ws.conditions = score_conditions(manifest, runs_root, views, customize_suite=customize_suite)
        if suffix is None:
            from .simulation import load_rulings, load_transcript, rulings_path, score_simulation

            transcript = load_transcript(runs_root)
            if transcript is not None:
                rp = rulings_path(runs_root, world)
                ws.simulation = score_simulation(manifest, sim_views, transcript, load_rulings(runs_root, world),
                                                 rp if rp.exists() else None)
    else:
        kind, cid = ("customize", suffix.removeprefix("customize-")) if suffix.startswith("customize-") else ("honesty", suffix)
        if cid in BUILTIN_VARIANTS:
            ws.notes.append(f"{cid} is built into the world; its assertions are scored on the default runs")
        ws.assertions += run_assertions(condition_assertions(manifest, kind, cid, customize_suite=True),
                                        CheckContext(manifest, views, ex_misses))
    return ws
