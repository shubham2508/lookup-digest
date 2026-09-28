"""The debug UI's API over a fake runs directory, plus the LLM trace log."""
import json
import threading
import urllib.request
from pathlib import Path

import pytest

from digest.llm import TraceLog
from digest.runs import ARTIFACTS
from ui.server import Handler, launch_args, list_runs, make_server, read_artifact


def _fake_run(root: Path, world: str, name: str) -> Path:
    d = root / world / name
    d.mkdir(parents=True)
    (d / ARTIFACTS["run"]).write_text(json.dumps({"as_of": "2026-09-24T06:00:00-07:00", "cost_usd": 0.05, "llm_calls": 3,
                                                  "reduce": {"items": 4}, "compose": {"placed": 3}, "verify": {"violations": []}}))
    (d / ARTIFACTS["digest"]).write_text("# Daily Digest\n\nAs of Thu 06:00 PT\n")
    (d / ARTIFACTS["candidates"]).write_text(json.dumps({"candidate_id": "c1", "type": "reply_owed", "about": "deal:x"}) + "\n")
    (d / ARTIFACTS["trace"]).write_text(json.dumps({"role": "triage", "messages": [{"role": "user", "content": "hi"}], "raw": "{}", "cached": False}) + "\n")
    return d


def test_list_runs_and_read_artifacts(tmp_path):
    _fake_run(tmp_path, "dev", "2026-09-24T06-00")
    _fake_run(tmp_path, "dev", "2026-09-24T06-00_baseline")
    runs = list_runs(tmp_path)
    assert [r["name"] for r in runs] == ["2026-09-24T06-00", "2026-09-24T06-00_baseline"]
    assert runs[0]["world"] == "dev" and runs[0]["items"] == 4 and runs[0]["has_trace"] and runs[0]["has_digest"]
    code, rows = read_artifact("dev/2026-09-24T06-00", "candidates", tmp_path)
    assert code == 200 and rows[0]["candidate_id"] == "c1"
    code, obj = read_artifact("dev/2026-09-24T06-00", "digest", tmp_path)
    assert code == 200 and obj["text"].startswith("# Daily Digest")
    assert read_artifact("dev/2026-09-24T06-00", "compose", tmp_path)[0] == 404
    assert read_artifact("dev/2026-09-24T06-00", "nope", tmp_path)[0] == 400
    assert read_artifact("../../etc", "digest", tmp_path)[0] == 400


def test_launch_args():
    assert launch_args({"world": "dev", "as_of": "2026-09-24T06:00", "variant": "", "tag": "sim"}) == ["run", "--world", "dev", "--as-of", "2026-09-24T06:00", "--tag", "sim"]
    assert launch_args({"world": "dev", "baseline": True, "as_of": "x"}) == ["baseline", "--world", "dev", "--as-of", "x"]
    assert launch_args({"world": ""}) is None
    assert launch_args({"world": "dev", "action": "eval"}) == ["eval", "--world", "dev", "--customize-suite", "--baseline"]
    assert launch_args({"world": "dev", "action": "matrix"}) == ["eval", "--matrix", "--world", "dev", "--keep-going"]
    assert launch_args({"world": "dev", "action": "simulate"}) == ["simulate", "--world", "dev", "--days", "5", "--fresh"]
    assert launch_args({"world": "heldout", "action": "generate"}) == ["generate", "--world", "heldout"]
    assert launch_args({"world": "dev", "action": "rm -rf"}) is None


def test_http_api(tmp_path):
    _fake_run(tmp_path, "dev", "2026-09-24T06-00")
    srv = make_server("127.0.0.1", 0, runs_dir=tmp_path)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        def get(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                return r.status, r.read()
        code, body = get("/")
        assert code == 200 and b"<title>" in body
        code, body = get("/api/runs")
        assert code == 200 and json.loads(body)[0]["name"] == "2026-09-24T06-00"
        code, body = get("/api/run?dir=dev/2026-09-24T06-00&artifact=trace")
        assert code == 200 and json.loads(body)[0]["role"] == "triage"
        code, body = get("/api/launch")
        assert code == 200 and json.loads(body)["running"] is False
        with pytest.raises(urllib.error.HTTPError) as ei:
            get("/api/run?dir=dev/2026-09-24T06-00&artifact=compose")
        assert ei.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()
        Handler.runs_dir = None


def test_trace_log_records_full_calls(tmp_path):
    tl = TraceLog(tmp_path / "trace.jsonl")
    tl.record(role="extractor", messages=[{"role": "system", "content": "x"}], raw="{}", output={"a": 1}, cached=False)
    tl.record(role="extractor", messages=[], raw="{}", output=None, cached=True)
    rows = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert len(rows) == 2 and rows[0]["output"] == {"a": 1} and rows[0]["ts"] and rows[1]["cached"] is True
    TraceLog(None).record(role="x")  # a disabled trace log is a no-op


def test_worlds_list_run_mornings():
    from ui.server import list_customize, list_worlds
    ws = {w["world"]: w for w in list_worlds()}
    mini = ws["tests/fixtures/mini"]
    assert mini["mornings"] and mini["mornings"][-1]["as_of"] == "2026-09-24T06:00" and "Thu" in mini["mornings"][-1]["label"]
    if "dev" in ws:
        assert [m["as_of"] for m in ws["dev"]["mornings"]][0] == "2026-09-20T06:00" and len(ws["dev"]["mornings"]) == 5
    presets = list_customize()
    assert any(c["path"] == "profile/customize/weekend.md" and c["text"] for c in presets)


def test_custom_prompt_file(tmp_path, monkeypatch):
    import ui.server as s
    monkeypatch.setattr(s, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(s, "ROOT", tmp_path)
    rel = s.save_custom_prompt("Only investors, under 120 words")
    assert rel.startswith("runs/_ui/customize/only-investors-under-12") and (tmp_path / rel).read_text().startswith("Only investors")
