"""Score a world: every run day's artifacts against the manifest, every assertion, headline numbers.

Where runs live (digest/runs.py): runs/<world>/<as_of>[_<suffix>]/ with the suffix
- `<variant>` for honesty variants (stale_inbox, no_notes, corrupt_ics),
- `customize-<stem>` for customize-suite runs, `baseline` for the naive baseline (OPEN_QUESTIONS.md #6),
and storyline variants as their own world, runs/<world>__<variant id>/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

import yaml

from digest.paths import ROOT
from digest.runs import run_dir_name
from eval.manifest_schema import Assertion, Manifest, load_manifest

from .artifacts import RunView
from .assertions import AssertionResult, CheckContext, run_assertions
from .common import StageMetrics
from .compute import score_compute
from .digest_metrics import score_digest, score_materializer
from .extraction import score_extraction
from .match import PT, SourceIndex
from .triage import score_triage

EVAL_DIR = Path(__file__).resolve().parents[1]
CUSTOMIZE_SUITE = EVAL_DIR / "customize_suite.yaml"


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

    # ------------------------------------------------------------------ headline (eval.md §9.1)
    def headline(self) -> dict:
        p0_hit = p0_n = noise_hit = noise_n = one_ok = one_n = 0
        costs = []
        for r in self.runs.values():
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
        judged = [a for a in self.assertions if a.passed is not None]
        return {
            "p0_recall": round(p0_hit / p0_n, 3) if p0_n else None,
            "p0_gate": (p0_hit == p0_n) if p0_n else None,
            "traps_passed": f"{sum(1 for a in judged if a.passed)}/{len(judged)}" if judged else None,
            "traps_not_run": sum(1 for a in self.assertions if a.passed is None),
            "must_not_rate": round(noise_hit / noise_n, 3) if noise_n else None,
            "one_thing_accuracy": round(one_ok / one_n, 3) if one_n else None,
            "cost_per_run": round(sum(costs) / len(costs), 4) if costs else None,
            "runs_scored": len(self.runs),
        }


def score_run(view: RunView, manifest: Manifest, day: int) -> RunScore:
    stages = {
        "extraction": score_extraction(view, manifest),
        "compute": score_compute(view, manifest, day),
    }
    stages["triage"] = score_triage(view, manifest, day)
    stages["compose"] = score_digest(view, manifest, day)
    stages["materializer"] = score_materializer(view, manifest)
    return RunScore(day=day, run_dir=str(view.dir), stages=stages, cost_usd=view.cost.get("cost_usd"),
                    missing_artifacts=view.missing)


def _extraction_misses(score: RunScore | None) -> dict[str, list]:
    out: dict[str, list] = {}
    if score is None:
        return out
    for m in score.stages["extraction"].misses:
        out.setdefault(m.what.split(":", 1)[0], []).append(m)
    return out


def load_views(manifest: Manifest, runs_root: Path, suffix: str | None = None) -> dict[int, RunView]:
    index = SourceIndex(manifest)
    return {d: RunView(p, index, ROOT, day=d) for d, p in find_runs(manifest, runs_root, suffix).items()}


def load_customize_suite(path: Path | None = None) -> list[Assertion]:
    p = path or CUSTOMIZE_SUITE
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [Assertion.model_validate(a) for a in data.get("assertions", [])]


def score_world(world: str, runs_root: Path | None = None, *, suffix: str | None = None, label: str = "pipeline",
                manifest: Manifest | None = None, customize_suite: bool = False) -> WorldScore:
    """Score every run day found under runs_root; then every assertion whose variant/customize matches `suffix`."""
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
    ex_misses = _extraction_misses(ws.runs[max(ws.runs)] if ws.runs else None)

    if suffix in (None, "baseline"):
        base = [a for a in manifest.assertions if not a.variant and not a.customize]
        ws.assertions += run_assertions(base, CheckContext(manifest, views, ex_misses))
        for v in manifest.variants:
            if v.kind == "honesty":
                vviews = load_views(manifest, runs_root, v.id)
                ws.assertions += run_assertions(v.assertions, CheckContext(manifest, vviews, ex_misses))
            elif v.data_dir or v.kind == "storyline":
                vroot = runs_root.parent / f"{runs_root.name}__{v.id}"
                ws.assertions += run_assertions(v.assertions, CheckContext(manifest, load_views(manifest, vroot), ex_misses))
        by_variant: dict[str, list[Assertion]] = {}
        for a in manifest.assertions:
            if a.variant:
                by_variant.setdefault(a.variant, []).append(a)
        for vid, al in by_variant.items():
            ws.assertions += run_assertions(al, CheckContext(manifest, load_views(manifest, runs_root, vid), ex_misses))
        cz = [a for a in manifest.assertions if a.customize]
        if customize_suite:
            cz += load_customize_suite()
        by_cz: dict[str, list[Assertion]] = {}
        for a in cz:
            by_cz.setdefault(a.customize or "", []).append(a)
        for stem, al in by_cz.items():
            ws.assertions += run_assertions(al, CheckContext(manifest, load_views(manifest, runs_root, f"customize-{stem}"), ex_misses))
    elif suffix.startswith("customize-"):
        stem = suffix.removeprefix("customize-")
        cz = [a for a in manifest.assertions + (load_customize_suite() if customize_suite else []) if a.customize == stem]
        ws.assertions += run_assertions(cz, CheckContext(manifest, views, ex_misses))
    else:  # an honesty variant scored on its own
        va = [a for a in manifest.assertions if a.variant == suffix]
        va += [a for v in manifest.variants if v.id == suffix for a in v.assertions]
        ws.assertions += run_assertions(va, CheckContext(manifest, views, ex_misses))
    return ws
