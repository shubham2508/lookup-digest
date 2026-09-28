"""Integration matrix (eval/integrate.py) and the #13 rulings: plan, stop cleanly, keep going, log; rulings path and
count; plus the fixes found by running it on Track A's real fixture output."""
import json

import pytest
from typer.testing import CliRunner

from cli.main import app
from eval.integrate import plan, run_matrix
from eval.scorer.artifacts import RunView
from eval.scorer.digest_md import parse_digest
from eval.scorer.markdown_view import parse_actions
from eval.scorer.match import SourceIndex
from eval.scorer.runner import load_views, score_world
from eval.scorer.simulation import rulings_applied, rulings_path, state_path
from eval.sim_avery.sim import set_aside_state
from tests.c_helpers import DAY, ROOT, make_run, mini_manifest


@pytest.fixture
def manifest():
    return mini_manifest()


@pytest.fixture
def five_days():
    m = mini_manifest()
    m.meta.run_days = [26, 27, 28, 29, 30]
    return m


# ----------------------------------------------------------------------------- plan
def test_plan_for_a_five_day_world(five_days):
    steps = plan("heldout", five_days)
    groups = [s.group for s in steps]
    assert groups == ["runs"] * 5 + ["variants"] * 3 + ["customize"] * 6 + ["baseline", "simulate", "eval"]
    assert steps[0].args == ["run", "--world", "heldout", "--as-of", "2026-09-20T06:00"]
    assert steps[4].args[-1] == "2026-09-24T06:00"
    assert steps[5].args[-2:] == ["--variant", "stale_inbox"] and steps[5].args[4] == "2026-09-24T06:00"
    assert steps[8].args[-2:] == ["--customize", "profile/customize/board_prep.md"]
    assert steps[-3].args == ["baseline", "--world", "heldout", "--as-of", "2026-09-24T06:00"]
    assert steps[-2].args == ["simulate", "--world", "heldout", "--days", "5", "--fresh"]
    assert steps[-1].args == ["eval", "--world", "heldout", "--customize-suite", "--baseline"]


def test_plan_on_the_one_day_fixture(manifest):
    steps = plan("tests/fixtures/mini", manifest)
    assert len(steps) == 13 and steps[-2].args[4] == "1"  # simulate --days = number of run days, at most 5


# ----------------------------------------------------------------------------- execution
class Fake:
    def __init__(self, codes=None):
        self.codes, self.calls = codes or {}, []

    def __call__(self, args):
        self.calls.append(args)
        key = args[0] if args[0] != "run" else ("variant" if "--variant" in args else "customize" if "--customize" in args else "run")
        code = self.codes.get(key, 0)
        return code, "digest run: stages compute..render not implemented (M5)" if code == 3 else "ok"


def test_all_ok(tmp_path, manifest):
    fake = Fake()
    res = run_matrix("w", manifest, cmd=fake, log=lambda _: None, runs_root=tmp_path)
    assert res.outcome == "ok" and res.exit_code == 0 and len(fake.calls) == 13
    log = json.loads((tmp_path / "integration.json").read_text())
    assert log["outcome"] == "ok" and [s["status"] for s in log["steps"]] == ["ok"] * 13


def test_stops_cleanly_where_a_stage_is_missing(tmp_path, manifest):
    logs = []
    res = run_matrix("w", manifest, cmd=Fake({"variant": 3}), log=logs.append, runs_root=tmp_path)
    assert [s.status for s in res.steps] == ["ok", "blocked"] + ["skipped"] * 11
    assert res.outcome == "blocked" and res.exit_code == 3
    assert "not implemented (M5)" in logs[1] and "not implemented" in res.steps[1].tail


def test_keep_going_and_failures(tmp_path, manifest):
    res = run_matrix("w", manifest, cmd=Fake({"baseline": 3, "simulate": 1}), keep_going=True, log=lambda _: None,
                     runs_root=tmp_path)
    by = {s.group: s.status for s in res.steps}
    assert by["baseline"] == "blocked" and by["simulate"] == "failed" and by["eval"] == "ok"
    assert res.outcome == "failed" and res.exit_code == 1


def test_dry_run_runs_nothing(tmp_path, manifest):
    fake = Fake()
    res = run_matrix("w", manifest, cmd=fake, dry_run=True, log=lambda _: None, runs_root=tmp_path)
    assert fake.calls == [] and res.outcome == "planned" and not (tmp_path / "integration.json").exists()
    assert "| 13 | eval |" in res.table()


def test_cli_matrix_without_manifest_is_blocked():
    r = CliRunner().invoke(app, ["eval", "--matrix", "--world", "heldout"])
    assert r.exit_code == 2 and "no manifest" in r.output


def test_cli_matrix_dry_run_on_fixture():
    r = CliRunner().invoke(app, ["eval", "--matrix", "--world", "tests/fixtures/mini", "--dry-run"])
    assert r.exit_code == 0 and "matrix: planned" in r.output and "simulate --world tests/fixtures/mini --days 1 --fresh" in r.output


# ----------------------------------------------------------------------------- #13a / #13c (ruled)
def test_rulings_path_from_settings_template(tmp_path):
    assert rulings_path(ROOT / "runs" / "dev", "dev") == ROOT / "runs" / "dev" / "rulings.yaml"
    assert rulings_path(tmp_path) == tmp_path / "rulings.yaml"  # a --runs root carries its state with it
    assert state_path("state/{world}/rulings.yaml", tmp_path, "heldout") == ROOT / "state" / "heldout" / "rulings.yaml"


def test_fresh_uses_settings_templates(tmp_path):
    (tmp_path / "rulings.yaml").write_text("[]")
    (tmp_path / "store.sqlite").write_text("x")
    (tmp_path / "store.sqlite-wal").write_text("x")
    moved = set_aside_state(tmp_path, "dev")
    assert len(moved) == 3 and not list(tmp_path.glob("store.sqlite")) and not (tmp_path / "rulings.yaml").exists()
    assert set_aside_state(tmp_path, "dev") == []  # backups are never renamed again


def test_rulings_applied_prefers_run_json(tmp_path, manifest):
    d = make_run(tmp_path, manifest, DAY, [], header="As of 06:00 PT · applied 2 learned rules")
    idx = SourceIndex(manifest)
    assert rulings_applied(RunView(d, idx, ROOT, day=DAY)) == 2  # header fallback
    (d / "run.json").write_text(json.dumps({"rulings_applied": 1}))
    assert rulings_applied(RunView(d, idx, ROOT, day=DAY)) == 1  # run.json wins
    (d / "run.json").write_text(json.dumps({"rulings_applied": 0}))
    assert rulings_applied(RunView(d, idx, ROOT, day=DAY)) == 0
    d2 = make_run(tmp_path / "x", manifest, DAY, [], header="As of 06:00 PT · applied 1 learned rule")
    assert rulings_applied(RunView(d2, idx, ROOT, day=DAY)) == 1


# ----------------------------------------------------------------------------- found on Track A's real output
def test_malformed_contacts_are_reported_not_fatal(tmp_path, manifest):
    d = make_run(tmp_path, manifest, DAY, [])
    (d / "contacts.json").write_text(json.dumps(["contact_id='sam-park' names=['Sam Park']"]))
    ws = score_world("x", tmp_path, manifest=manifest, conditions=False)
    assert ws.runs[DAY].stages["compute"].metrics["contact_category_accuracy"] == 0.0
    assert any("malformed artifact: contacts.json: 1 of 1" in n for n in ws.notes)


def test_quoted_draft_line_under_an_action():
    md = ("As of now\n\n## Urgent To-Do Today\n\n- **Confirm the rollout to Renee.** She asked Tuesday. *[email: Renee, Tue 14:08]*\n"
          "  ↳ Draft to Renee:\n  \"renee, yes, it's on. Avery\"\n  Assumptions: sprint note holds\n"
          "- **Send Diane the update.** Overdue. *[task: Send Q2 board update to Diane]*\n"
          "  ↳ Decide: (1) send today (2) review first. Recommended: (1)\n  \"Diane, sending it today. Avery\"\n")
    d = parse_digest(md)
    a, b = d.sections["urgent"]
    assert a.text.endswith("*[email: Renee, Tue 14:08]*") and len(a.action_lines) == 3
    assert d.word_count == 13  # the quoted drafts are action text, not item words
    acts = parse_actions(a.action_lines) + parse_actions(b.action_lines)
    assert [x["type"] for x in acts] == ["reply", "decide"]
    assert acts[0]["draft"] == "renee, yes, it's on. Avery" and acts[0]["assumptions"] == ["sprint note holds"]
    assert acts[1]["draft"] == "Diane, sending it today. Avery"


def test_item_matches_by_candidate_fallback(tmp_path, manifest):
    """Compute keyed the pediatrician conflict by the child's name; #9 still finds it (type + evidence token)."""
    ped = {"id": "w", "about": "family:wren", "priority": "P0", "section": "calendar_personal",
           "ctype": "calendar_conflict:family", "cites": ["event:wren-pediatrician-20260924@parkfamily.example"]}
    make_run(tmp_path, manifest, DAY, [ped])
    ws = score_world("x", tmp_path, manifest=manifest, conditions=False)
    c, t = ws.runs[DAY].stages["compose"], ws.runs[DAY].stages["triage"]
    assert "P0 missing: family:pediatrician" not in " ".join(m.what for m in c.misses)
    assert "family:pediatrician: never triaged" not in " ".join(m.what for m in t.misses)
    # but a key another expectation owns is never borrowed: the daycare item stays missing
    assert any(m.what.startswith("P0 missing: family:daycare") for m in c.misses)
    assert load_views(manifest, tmp_path)[DAY].rendered[0].about == "family:wren"
