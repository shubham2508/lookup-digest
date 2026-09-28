
from typer.testing import CliRunner

from cli.main import app
from digest.cli import NOT_IMPLEMENTED_EXIT
from digest.paths import ROOT

runner = CliRunner()


def test_help_lists_every_command():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for c in ("run", "answer", "baseline", "llm-check", "db-init", "generate", "eval", "simulate"):
        assert c in r.output, c


def test_stubs_say_not_implemented():
    for args in (["run"], ["generate"], ["eval"], ["simulate"], ["baseline"], ["answer", "Q1", "2"]):
        r = runner.invoke(app, args)
        assert r.exit_code == NOT_IMPLEMENTED_EXIT, (args, r.output)
        assert "not implemented" in r.output and "Track" in r.output


def test_db_init_creates_store():
    world = "_m0_test"
    path = ROOT / "runs" / world / "store.sqlite"
    try:
        r = runner.invoke(app, ["db-init", "--world", world])
        assert r.exit_code == 0 and path.exists() and "rulings" in r.output
    finally:
        for p in path.parent.glob("store.sqlite*"):
            p.unlink()
        if path.parent.exists():
            path.parent.rmdir()
