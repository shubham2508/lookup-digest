"""`digest` entry point: product commands + generator + eval, one CLI (CLAUDE.md "CLI")."""
from __future__ import annotations

import typer

from digest import cli as product
from eval import cli as evaluation
from generator import cli as generation

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="Daily Digest for Avery Chen: generate synthetic worlds, run the digest, evaluate it.")

app.command("run")(product.run)
app.command("answer")(product.answer)
app.command("baseline")(product.baseline)
app.command("llm-check")(product.llm_check)
app.command("db-init")(product.db_init)
app.command("generate")(generation.generate)
app.command("eval")(evaluation.evaluate)
app.command("simulate")(evaluation.simulate)

if __name__ == "__main__":
    app()
