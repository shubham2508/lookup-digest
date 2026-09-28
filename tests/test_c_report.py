"""Report (eval.md §9), eval/history.md rows, the expected profile and its diff, and the `digest eval` CLI."""
import copy
from datetime import date

import yaml
from typer.testing import CliRunner

from cli.main import app
from digest.schemas import ProfileConfig
from eval.history import append
from eval.judge.judge import JudgeRun
from eval.report import render_report, report_name
from eval.scorer.digest_metrics import EXPECTED_PROFILE
from eval.scorer.profile_diff import diff_profile
from eval.scorer.runner import score_world
from tests.c_helpers import MINI_RUNS, mini_manifest


def test_report_has_every_section_and_links():
    m = mini_manifest()
    ws = score_world("tests/fixtures/mini", MINI_RUNS, manifest=m)
    text = render_report("tests/fixtures/mini", {("pipeline", "dev"): ws}, m, JudgeRun("judge", "skipped", "no model configured"),
                         on=date(2026, 9, 28))
    for h in ("## 1. Summary", "## 2. Per-stage metrics", "## 3. Trap assertions", "## 4. Customize and variant results",
              "## 5. Judge", "## 6. Label audit"):
        assert h in text, h
    assert "| P0 recall (gate = 100%) | 0.667 ❌ |" in text
    assert "judge: skipped (no model configured)" in text
    assert "[triage] P0 missing: family:daycare" in text and "triage.jsonl#L8" in text
    assert "Not run yet: pipeline · heldout, baseline · dev, baseline · heldout." in text
    assert report_name("tests/fixtures/mini", date(2026, 9, 28)) == "tests_fixtures_mini_2026-09-28.md"
    assert report_name("dev", date(2026, 9, 28), "stale_inbox") == "dev_2026-09-28_stale_inbox.md"


def test_history_append(tmp_path):
    p = tmp_path / "history.md"
    p.write_text("| date | prompt |\n|---|---|")
    row = append("2026-09-28", "triage", 2, {"p0_recall": 0.8, "traps_passed": "20/30"},
                 {"p0_recall": 1.0, "traps_passed": "24/30", "cost_per_run": 0.31}, note="rubric | anchors", path=p)
    assert row == "| 2026-09-28 | triage | 2 | 0.8 → 1 | 20/30 → 24/30 | — | — | 0.31 | rubric / anchors |"
    assert p.read_text().splitlines()[-1] == row


def test_expected_profile_is_a_valid_profile_config():
    data = yaml.safe_load(EXPECTED_PROFILE.read_text())
    cfg = ProfileConfig.model_validate(data)
    assert cfg.hard_rules.never_draft_for == ["Sam Park"]
    assert cfg.thresholds.investor_quiet_business_days == 3


def test_profile_diff():
    exp = yaml.safe_load(EXPECTED_PROFILE.read_text())
    same = diff_profile(exp, exp)
    assert same.accuracy == 1.0 and not same.diffs and set(same.coverage.values()) == {1.0}
    got = copy.deepcopy(exp)
    got["contacts"][0]["rules"] = []                       # Sam loses never_draft
    got["contacts"][7]["role_at_org"]["role"] = "procurement leads"  # wording varies: still matched by orgs
    got["facts"][0]["value"] = "$3.4M"
    got["thresholds"]["investor_quiet_business_days"] = 5
    got["tone"] = got["tone"][:2]
    d = diff_profile(exp, got)
    assert d.accuracy < 1.0
    assert any("sam park.rules" in x for x in d.diffs)
    assert any(x.startswith("fact ARR") for x in d.diffs)
    assert any("investor_quiet_business_days" in x for x in d.diffs)
    assert not any("procurement" in x and "missing" in x for x in d.diffs)
    assert d.coverage["tone"] < 1.0


def test_eval_cli_writes_a_report(tmp_path):
    r = CliRunner().invoke(app, ["eval", "--world", "tests/fixtures/mini", "--runs", str(MINI_RUNS), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "P0 GATE FAILED" in r.output
    [report] = list(tmp_path.glob("tests_fixtures_mini_*.md"))
    assert "## 3. Trap assertions" in report.read_text()


def test_eval_cli_without_manifest_exits_2():
    r = CliRunner().invoke(app, ["eval", "--world", "no-such-world-xyz"])
    assert r.exit_code == 2 and "no manifest" in r.output
