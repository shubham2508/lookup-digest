from digest.runs import ARTIFACTS, RunContext, parse_as_of, run_dir_name
from digest.schemas import Candidate


def test_parse_as_of_and_dir_name():
    dt = parse_as_of("2026-09-24T06:00")
    assert dt.tzinfo is not None and dt.utcoffset().total_seconds() == -7 * 3600  # PDT
    assert run_dir_name(dt) == "2026-09-24T06-00"
    assert run_dir_name(dt, "stale_inbox") == "2026-09-24T06-00_stale_inbox"
    assert parse_as_of("2026-11-12T06:00").utcoffset().total_seconds() == -8 * 3600  # PST after Nov 1


def test_run_context_artifacts(tmp_path):
    ctx = RunContext("dev", parse_as_of("2026-09-24T06:00"), runs_dir=tmp_path)
    assert ctx.run_dir == tmp_path / "dev" / "2026-09-24T06-00" and ctx.run_id == "dev/2026-09-24T06-00"
    ctx.write_jsonl("candidates", [Candidate(candidate_id="c1", type="reply_owed", about="deal:series-a")])
    assert ctx.read_jsonl("candidates")[0]["about"] == "deal:series-a"
    ctx.write_text("digest", "# digest\n")
    ctx.degrade("extract", "t-1", "LLMOutputInvalid")
    with ctx.timed("extract"):
        pass
    ctx.cost_log.record(role="extractor", cached=False, prompt_tokens=1, completion_tokens=1, cost_usd=0.5, cost_known=True)
    summary = ctx.finish()
    assert summary["cost_usd"] == 0.5 and summary["degradations"] == 1 and "extract" in summary["timings_s"]
    for a in ("cost", "run", "degradations", "cost_log", "digest"):
        assert ctx.path(a).exists(), a
    assert set(ARTIFACTS) >= {"extractions", "candidates", "triage", "compose", "actions", "verify", "digest", "cost"}
