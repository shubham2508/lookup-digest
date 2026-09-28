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
    matrix: bool = typer.Option(False, "--matrix", help="integration: every run, variant, customize, baseline, "
                                "simulate --fresh, then this eval (eval/integrate.py)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="with --matrix: print the plan, run nothing"),
    keep_going: bool = typer.Option(False, "--keep-going", help="with --matrix: don't stop at the first blocked step"),
) -> None:
    """Score runs against the world's manifest and write eval/reports/<world>_<date>.md."""
    if matrix:
        _matrix(world, dry_run, keep_going)
        return
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
    if baseline or load_views(manifest, root, "baseline"):
        scores[("baseline", label)] = score_world(world, root, suffix="baseline", label="baseline", manifest=manifest)
    # the other world's column (dev ↔ held-out), never tuned on: scored whenever its manifest exists
    other = "dev" if label == "heldout" else "heldout"
    if "/" not in world and manifest_path(other).exists():
        om = load_manifest(manifest_path(other))
        oroot = ROOT / "runs" / other
        scores[("pipeline", other)] = score_world(other, oroot, manifest=om, conditions=False)
        if baseline or load_views(om, oroot, "baseline"):
            scores[("baseline", other)] = score_world(other, oroot, suffix="baseline", label="baseline", manifest=om)

    jrun = cal = None
    if judge or calibrate_judge:
        items = []
        for day, view in sorted(load_views(manifest, root, variant).items()):
            items += draft_items(view, f"d{day}/")
            di = digest_item(view, f"d{day}/")
            if di:
                items.append(di)
        for day, view in sorted(load_views(manifest, root, "baseline").items()):  # eval.md §8: baseline is judged too
            di = digest_item(view, f"baseline/d{day}/")
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


def _matrix(world: str, dry_run: bool, keep_going: bool) -> None:
    from eval.integrate import run_matrix
    from eval.scorer.runner import manifest_path

    mpath = manifest_path(world)
    if not mpath.exists():
        typer.echo(f"no manifest at {mpath} (Track B writes eval/manifests/<world>.yaml)")
        raise typer.Exit(2)
    res = run_matrix(world, load_manifest(mpath), dry_run=dry_run, keep_going=keep_going, log=typer.echo)
    typer.echo("")
    typer.echo(res.table())
    typer.echo(f"\nmatrix: {res.outcome}" + ("" if dry_run else f" · log: runs/{world}/integration.json"))
    raise typer.Exit(res.exit_code)


def simulate(
    world: str = typer.Option("dev", "--world"),
    days: int = typer.Option(5, "--days"),
    runs: Path = typer.Option(None, "--runs", help="runs root; default runs/<world>"),
    fresh: bool = typer.Option(False, "--fresh", help="set aside rulings.yaml and store.sqlite first (renamed, not deleted)"),
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
    transcript = run_sim(world, days, manifest, root, log=typer.echo, fresh=fresh)
    ws = score_world(world, root, manifest=manifest)
    text = render_report(world, {("pipeline", "heldout" if "heldout" in world else "dev"): ws}, manifest)
    text += "\n## Simulation transcript\n\n```json\n" + json.dumps(transcript, indent=2) + "\n```\n"
    path = write_report(text, report_name(world, suffix="simulate"))
    typer.echo(f"report: {path}")
    stopped = next((st for st in transcript if st.get("run_exit") or st.get("error")), None)
    if stopped:  # the matrix (eval/integrate.py) reads this exit code: 3/2 = blocked on the product, else failed
        code = stopped.get("run_exit") or 1
        typer.echo(f"simulation stopped on day {stopped['day']}: {stopped.get('error', '')[-160:]}")
        raise typer.Exit(code if code in (2, 3) else 1)
