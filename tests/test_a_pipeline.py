"""Track A · M3 acceptance: `digest run` on the fixture writes extractions.jsonl (and the other run artifacts)."""
import json

from a_fakes import fake_llm

from digest.pipeline import run_pipeline
from digest.store import Store


def test_run_pipeline_on_fixture(tmp_path):
    llm = fake_llm(tmp_path)
    (tmp_path / "profile.md").write_text("# Avery Chen — Profile\n\nI'm Avery Chen.\n")
    store = Store(tmp_path / "store.sqlite")
    r = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", runs_dir=tmp_path / "runs", llm=llm,
                     profile_path=tmp_path / "profile.md", profile_out=tmp_path / "profile.yaml", store=store)
    run_dir = r.ctx.run_dir
    assert run_dir == tmp_path / "runs" / "tests/fixtures/mini" / "2026-09-24T06-00"
    rows = [json.loads(ln) for ln in (run_dir / "extractions.jsonl").read_text().splitlines()]
    assert len(rows) == 10 and {row["type"] for row in rows} == {"marketing", "automated", "human_thread", "newsletter", "note", "task"}
    for name in ("cost.json", "cost.jsonl", "run.json", "degradations.jsonl"):
        assert (run_dir / name).exists(), name
    run = json.loads((run_dir / "run.json").read_text())
    assert run["owner_email"] == "avery@tessera.io" and run["extractions"] == 10 and run["pending_stages"][0] == "compute"
    assert run["freshness"]["email"]["state"] == "ok" and run["llm_calls"] == 10 and run["cost_usd"] > 0
    assert r.freshness_line.startswith("inbox synced Wed 21:10 · calendar ok")
    with store:
        assert store.count("messages") == 7 and store.count("threads") == 6 and store.count("events") == 19
        assert store.count("notes") == 1 and store.count("tasks") == 3 and store.count("extractions") == 10
        assert store.get("threads", thread_id="thread:20260922-1642.marcus@inflectionpoint.vc")["router_type"] == "human"


def test_variant_and_missing_notes_degrade_visibly(tmp_path):
    llm = fake_llm(tmp_path)
    (tmp_path / "profile.md").write_text("# Avery Chen — Profile\n")
    r = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", variant="no_notes", runs_dir=tmp_path / "runs", llm=llm,
                     profile_path=tmp_path / "profile.md", profile_out=tmp_path / "profile.yaml", store=Store(tmp_path / "s.sqlite"))
    assert r.ctx.run_dir.name == "2026-09-24T06-00_no_notes"
    assert any(d["stage"] == "ingest" and d["reason"] == "source_missing" for d in r.ctx.degradations)
    assert "notes missing" in r.freshness_line and r.summary["notes"] == 0 and r.summary["extractions"] == 9
