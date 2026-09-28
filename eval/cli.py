"""`digest eval` and `digest simulate` (Track C, M6 and M9)."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from digest.paths import ROOT
from eval.manifest_schema import load_manifest


def _runs_root(world: str, runs: Path | None) -> Path:
    return runs if runs else ROOT / "runs" / world


def evaluate(
    world: str = typer.Option("dev", "--world", help="dev | heldout | a fixture dir such as tests/fixtures/mini"),
    variant: str = typer.Option(None, "--variant", help="stale_inbox | no_notes | corrupt_ics"),
    customize_suite: bool = typer.Option(False, "--customize-suite", help="also score profile/customize/* runs"),
    baseline: bool = typer.Option(False, "--baseline", help="also score the naive baseline (runs …_baseline/)"),
    runs: Path = typer.Option(None, "--runs", help="runs root; default runs/<world>"),
    judge: bool = typer.Option(False, "--judge", help="run the LLM judge (reported, not gated)"),
    calibrate_judge: bool = typer.Option(False, "--calibrate-judge",
                                         help="one-time: judge_reference (Fable) vs judge on the same items"),
    out: Path = typer.Option(None, "--out", help="report directory; default eval/reports/"),
) -> None:
    """Score runs against the world's manifest and write eval/reports/<world>_<date>.md."""
    from eval.judge.judge import calibrate, digest_item, draft_items, judge_items
    from eval.report import render_report, report_name, write_report
    from eval.scorer.runner import load_views, manifest_path, score_world

    mpath = manifest_path(world)
    if not mpath.exists():
        typer.echo(f"no manifest at {mpath} (Track B writes eval/manifests/<world>.yaml)")
        raise typer.Exit(2)
    manifest = load_manifest(mpath)
    root = _runs_root(world, runs)
    label = "heldout" if "heldout" in world else "dev"

    scores = {("pipeline", label): score_world(world, root, suffix=variant, manifest=manifest,
                                               customize_suite=customize_suite)}
    if baseline:
        scores[("baseline", label)] = score_world(world, root, suffix="baseline", label="baseline", manifest=manifest)
    other = "dev" if label == "heldout" else "heldout"
    if "/" not in world and manifest_path(other).exists():
        scores[("pipeline", other)] = score_world(other, ROOT / "runs" / other, manifest=load_manifest(manifest_path(other)))

    jrun = cal = None
    if judge or calibrate_judge:
        items = []
        for day, view in sorted(load_views(manifest, root, variant).items()):
            items += draft_items(view, f"d{day}/")
            di = digest_item(view, f"d{day}/")
            if di:
                items.append(di)
        if calibrate_judge:
            cal = calibrate(items[:20])
        if judge:
            jrun = judge_items(items)

    text = render_report(world, scores, manifest, jrun, cal)
    path = write_report(text, report_name(world, suffix=variant), out)
    head = scores[("pipeline", label)].headline()
    typer.echo(json.dumps(head, indent=2))
    typer.echo(f"report: {path}")
    if head.get("p0_gate") is False:
        typer.echo("P0 GATE FAILED")


def simulate(
    world: str = typer.Option("dev", "--world"),
    days: int = typer.Option(5, "--days"),
    runs: Path = typer.Option(None, "--runs", help="runs root; default runs/<world>"),
) -> None:
    """Run the last N days in order with sim_avery answering question cards, then score the multi-day assertions."""
    from eval.report import render_report, report_name, write_report
    from eval.scorer.runner import manifest_path, score_world
    from eval.sim_avery.sim import simulate as run_sim

    mpath = manifest_path(world)
    if not mpath.exists():
        typer.echo(f"no manifest at {mpath} (Track B writes eval/manifests/<world>.yaml)")
        raise typer.Exit(2)
    manifest = load_manifest(mpath)
    root = _runs_root(world, runs)
    transcript = run_sim(world, days, manifest, root, log=typer.echo)
    ws = score_world(world, root, manifest=manifest)
    text = render_report(world, {("pipeline", "heldout" if "heldout" in world else "dev"): ws}, manifest)
    text += "\n## Simulation transcript\n\n```json\n" + json.dumps(transcript, indent=2) + "\n```\n"
    path = write_report(text, report_name(world, suffix="simulate"))
    typer.echo(f"report: {path}")
