"""`digest eval` and `digest simulate` (Track C, M6 and M9)."""
from __future__ import annotations

import typer

from digest.cli import NOT_IMPLEMENTED_EXIT


def evaluate(
    world: str = typer.Option("dev", "--world", help="dev | heldout"),
    variant: str = typer.Option(None, "--variant", help="stale_inbox | no_notes | corrupt_ics"),
    customize_suite: bool = typer.Option(False, "--customize-suite"),
    baseline: bool = typer.Option(False, "--baseline", help="also score the naive baseline"),
) -> None:
    """Score runs against eval/manifests/<world>.yaml and write eval/reports/<world>_<date>.md."""
    typer.echo("digest eval: not implemented yet (Track C, M6). See docs/handoffs/C-grader.md.")
    raise typer.Exit(NOT_IMPLEMENTED_EXIT)


def simulate(
    world: str = typer.Option("dev", "--world"),
    days: int = typer.Option(5, "--days"),
) -> None:
    """Run the last N days in order with sim_avery answering question cards."""
    typer.echo("digest simulate: not implemented yet (Track C, M9). See docs/handoffs/C-grader.md.")
    raise typer.Exit(NOT_IMPLEMENTED_EXIT)
