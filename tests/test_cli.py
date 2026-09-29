
from typer.testing import CliRunner

from cli.main import app
from digest.paths import ROOT

runner = CliRunner()


def test_help_lists_every_command():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for c in ("run", "answer", "baseline", "llm-check", "db-init", "generate", "eval", "simulate"):
        assert c in r.output, c


def test_answer_and_baseline_without_state_say_so():
    r = runner.invoke(app, ["answer", "Q1", "1", "--world", "_no_such_world_a"])
    assert r.exit_code == 2 and "no digest run found" in r.output, r.output
    r = runner.invoke(app, ["baseline", "--world", "data/_no_such_world"])
    assert r.exit_code == 2 and "no data directory" in r.output, r.output


def test_run_without_data_says_so():
    """`run` is real since A M3; with no generated world it must say so instead of crashing (exit 2)."""
    r = runner.invoke(app, ["run", "--world", "data/_no_such_world"])
    assert r.exit_code == 2, r.output
    assert "no data directory" in r.output and "digest generate" in r.output


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


def test_run_without_a_key_stops_with_the_fix(monkeypatch):
    """A world with data and no API key stops before any call, saying how to fix it (not a silent code-only digest)."""
    import digest.llm

    monkeypatch.setattr(digest.llm, "load_api_key", lambda *_a, **_k: None)
    r = runner.invoke(app, ["run", "--world", "tests/fixtures/mini"])
    assert r.exit_code == 2 and "OPENROUTER_API_KEY is not set" in r.output and ".env.example" in r.output, r.output
