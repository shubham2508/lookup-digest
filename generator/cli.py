"""`digest generate` (Track B, M2)."""
from __future__ import annotations

from datetime import date

import typer


def generate(
    world: str = typer.Option("dev", "--world", help="dev | heldout"),
    anchor: str = typer.Option(None, "--anchor", help="date of day 30 (a Thursday), YYYY-MM-DD; default from world.yaml"),
    seed: int = typer.Option(7, "--seed"),
) -> None:
    """Render world/<world>/ into data/<world>/ and eval/manifests/<world>.yaml; refuses unreviewed storylines."""
    from .build import generate as _generate

    anchor_date = date.fromisoformat(anchor) if anchor else None
    res = _generate(world=world, anchor=anchor_date, seed=seed)
    for w in res.report.warnings[:40]:
        typer.echo(f"warning: {w}")
    if res.report.warnings[40:]:
        typer.echo(f"... {len(res.report.warnings) - 40} more warnings")
    if not res.report.ok():
        for p in res.report.problems[:80]:
            typer.echo(f"PROBLEM: {p}")
        if res.report.problems[80:]:
            typer.echo(f"... {len(res.report.problems) - 80} more problems")
        typer.echo(f"digest generate: validator failed with {len(res.report.problems)} problem(s); nothing written to eval/manifests/.")
        raise typer.Exit(1)
    typer.echo(f"digest generate: {res.emails} emails → {res.data_dir}; manifest → {res.manifest_path}; "
               f"variants: {', '.join(str(v) for v in res.variants) or 'none'}")
    typer.echo("counts: " + ", ".join(f"{k}={v}" for k, v in res.report.counts.items()))
