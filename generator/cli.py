"""`digest generate` (Track B, M2)."""
from __future__ import annotations

import typer

from digest.cli import NOT_IMPLEMENTED_EXIT


def generate(
    world: str = typer.Option("dev", "--world", help="dev | heldout"),
    anchor: str = typer.Option(None, "--anchor", help="date of day 30 (a Thursday), YYYY-MM-DD"),
    seed: int = typer.Option(7, "--seed"),
) -> None:
    """Render world/<world>/ into data/<world>/ and eval/manifests/<world>.yaml; refuses unreviewed storylines."""
    typer.echo("digest generate: not implemented yet (Track B, M2). See docs/handoffs/B-data.md.")
    raise typer.Exit(NOT_IMPLEMENTED_EXIT)
