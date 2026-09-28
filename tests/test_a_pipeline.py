"""Track A · v2 acceptance: `digest run` on the fixture reads every human thread, writes findings.jsonl (and the other
run artifacts), and produces a verified digest from readers alone."""
import json
from pathlib import Path

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
    rows = [json.loads(ln) for ln in (run_dir / "findings.jsonl").read_text().splitlines()]
    readers = [r for r in rows if r["origin"] == "thread_reader"]
    assert len(readers) == 4 and all(r["thread_id"] for r in readers) and {r["origin"] for r in rows} >= {"calendar_sweep", "safety_net"}
    assert sum(1 for r in rows if r["candidate_id"] is None) == 1
    assert all(r["rescued_by_safety_net"] is (r["origin"] == "safety_net") for r in rows), "only uncovered nets are rescues"
    n_cands = sum(1 for r in rows if r["candidate_id"])
    from digest.runs import ARTIFACTS
    for key, name in ARTIFACTS.items():
        assert (run_dir / name).exists() or key == "extractions", name
    assert not (run_dir / "extractions.jsonl").exists(), "v2 has no extractor"
    run = json.loads((run_dir / "run.json").read_text())
    assert run["owner_email"] == "avery@tessera.io" and run["read"]["threads_read"] == 3 and run["pending_stages"] == []
    assert run["read"]["findings"] == 4 and run["read"]["citations_dropped"] == 4 and set(run["timings_s"]) >= {"spine", "read", "enforce"}
    assert run["freshness"]["email"]["state"] == "ok" and run["cost_usd"] > 0 and run["verify"]["stats"]["header_present"]
    assert run["compute"]["candidates"] == n_cands and run["triage"]["fixes"] >= 1 and run["compose"]["one_thing"]
    assert r.freshness_line.startswith("inbox synced Wed 21:10 · calendar ok")
    md = (run_dir / "digest.md").read_text()
    assert md.startswith("# Daily Digest — Thursday, September 24, 2026\n\nAs of Thu 06:00 PT · inbox synced Wed 21:10")
    assert "## If there is one thing you must do right now" in md and "*[email: " in md and "No draft (Sam)" in md
    verify = json.loads((run_dir / "verify.json").read_text())
    assert verify["stats"]["items_cited"] == verify["stats"]["items"] and verify["stats"]["words"] <= 350
    with store:
        assert store.count("messages") == 7 and store.count("threads") == 6 and store.count("events") == 19
        assert store.count("notes") == 1 and store.count("tasks") == 3
        assert store.get("threads", thread_id="thread:20260922-1642.marcus@inflectionpoint.vc")["router_type"] == "human"
        assert store.count("candidates") == n_cands and store.count("triage_results") == n_cands and store.count("digest_items") >= 3
        assert store.get("runs", run_id="tests/fixtures/mini/2026-09-24T06-00")["cost_usd"] > 0


def test_variant_and_missing_notes_degrade_visibly(tmp_path):
    llm = fake_llm(tmp_path)
    (tmp_path / "profile.md").write_text("# Avery Chen — Profile\n")
    r = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", variant="no_notes", runs_dir=tmp_path / "runs", llm=llm,
                     profile_path=tmp_path / "profile.md", profile_out=tmp_path / "profile.yaml", store=Store(tmp_path / "s.sqlite"))
    assert r.ctx.run_dir.name == "2026-09-24T06-00_no_notes"
    assert any(d["stage"] == "ingest" and d["reason"] == "source_missing" for d in r.ctx.degradations)
    assert "notes missing" in r.freshness_line and r.summary["notes"] == 0 and r.summary["read"]["threads_read"] == 3
    assert "notes missing" in r.digest_md.split("\n")[2]


def test_customize_and_history_across_two_days(tmp_path):
    llm = fake_llm(tmp_path)
    (tmp_path / "profile.md").write_text("# Avery Chen — Profile\n")
    store = Store(tmp_path / "s.sqlite")
    kw = {"runs_dir": tmp_path / "runs", "llm": llm, "profile_path": tmp_path / "profile.md", "profile_out": tmp_path / "profile.yaml", "store": store}
    r1 = run_pipeline("tests/fixtures/mini", "2026-09-23T06:00", **kw)
    r2 = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", **kw)
    renee = next(c for c in r2.compute.candidates if "renee-tan" in c.entities)
    assert renee.times_surfaced == 1, "Renee's reply owed was surfaced on the 23rd already"
    assert r2.summary["history"]["resolved_later"] >= 0
    wk = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", customize=Path("profile/customize/weekend.md"), **kw)
    assert wk.ctx.run_dir.name == "2026-09-24T06-00_customize-weekend"
    md = wk.digest_md
    assert "customize: weekend.md applied" in md.split("\n")[2] and wk.verify.stats.budget == 100
    body = md.split("## Urgent To-Do Today", 1)[1]
    assert "Sam" in md and "Renee" not in body.split("## Also")[0], "focus 'family only' hides the customer reply"
    outside = [i for i in wk.reduce.items if i.priority == "P0" and "sam-park" not in i.entities]
    assert ("## Also outside your filter" in md) == bool(outside), "a P0 outside the filter is still a one-liner"
    nc = run_pipeline("tests/fixtures/mini", "2026-09-24T06:00", customize=Path("profile/customize/no_citations.md"), **kw)
    assert "rejected" in nc.digest_md.split("\n")[2] and "*[email: " in nc.digest_md
    del r1
