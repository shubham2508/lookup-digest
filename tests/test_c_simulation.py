"""M9: `digest simulate` with sim_avery, rulings, and the eval.md §7 multi-day checks, on a fake `digest` command."""
from datetime import date

import pytest
import yaml

from eval.manifest_schema import Assertion
from eval.report import render_report
from eval.scorer.runner import score_world
from eval.scorer.simulation import load_rulings, score_simulation
from eval.sim_avery.sim import set_aside_state, simulate
from tests.c_helpers import make_run, mini_manifest

RENEE = "msg:<20260922-1408.renee@halberd.com>"
MARCUS = "msg:<20260922-1642.marcus@inflectionpoint.vc>"
DAY_OF = {"2026-09-22T06:00": 28, "2026-09-23T06:00": 29, "2026-09-24T06:00": 30}


@pytest.fixture
def manifest():
    m = mini_manifest()
    m.meta.run_days = [28, 29, 30]
    return m


def fake_digest(root, m, *, good: bool):
    """Stands in for `digest run` / `digest answer`: a product that learns from rulings (good) or ignores them."""

    def cmd(args):
        if args[0] == "answer":
            if good:
                p = root / "rulings.yaml"
                rs = yaml.safe_load(p.read_text()) if p.exists() else []
                rs.append({"id": f"r{len(rs) + 1}", "scope": {"about": "rollout:halberd:oct-6"}, "ruling": "confirm",
                           "option_chosen": int(args[2]), "from_question": args[1], "created": "2026-09-22"})
                p.write_text(yaml.safe_dump(rs))
            return 0, "ok"
        day = DAY_OF[args[args.index("--as-of") + 1]]
        ruled = good and (root / "rulings.yaml").exists()
        halberd = {"id": "h", "about": "rollout:halberd:oct-6", "priority": "P1", "cites": [RENEE],
                   "actions": [{"type": "reply", "target": "renee.tan@halberd.com", "draft": "renee, yes."}]}
        if not ruled:
            halberd["actions"].append({"type": "question", "text": "Q1 · Is Oct 6 firm? (1) yes (2) check Default if unanswered: 1"})
        times = {28: 0, 29: 1, 30: 2}[day]
        cap = {"id": "k", "about": "deal:series-a:cap-table", "priority": "P0", "placement": "one_thing", "cites": [MARCUS],
               "ctype": "commitment_overdue", "times_surfaced": times,
               "why": "third time flagged; still not sent" if (good and times >= 2) else "promised Tuesday night"}
        header = "As of 06:00 PT · inbox ok" + (" · applied 1 learned rule" if ruled else "")
        items = [cap, halberd] if not (good and day == 30) else [cap]  # the good product sent the reply on day 29
        make_run(root, m, day, items, header=header)
        return 0, "ok"

    return cmd


def test_simulation_happy_path(tmp_path, manifest):
    logs = []
    t = simulate("mini", 3, manifest, tmp_path, log=logs.append, digest_cmd=fake_digest(tmp_path, manifest, good=True),
                 use_llm=False)
    assert [s["day"] for s in t] == [28, 29, 30]
    assert [(a["question"], a["option"], a["source"]) for a in t[0]["answers"]] == [("Q1", 1, "code")]
    assert t[1]["answers"] == [] and (tmp_path / "simulation.json").exists()
    assert load_rulings(tmp_path)[0]["scope"] == {"about": "rollout:halberd:oct-6"}
    ws = score_world("mini", tmp_path, manifest=manifest)
    assert ws.simulation and all(r.passed for r in ws.simulation), [(r.id, r.evidence) for r in ws.simulation]
    assert {r.kind for r in ws.simulation} == {"sim_ruling_recorded", "sim_ruling_applied", "sim_escalation"}
    text = render_report("mini", {("pipeline", "dev"): ws}, manifest, on=date(2026, 9, 28))
    assert "Generic checks: 3/3 passed." in text


def test_simulation_catches_a_product_that_ignores_rulings(tmp_path, manifest):
    simulate("mini", 3, manifest, tmp_path, log=lambda _: None, digest_cmd=fake_digest(tmp_path, manifest, good=False),
             use_llm=False)
    ws = score_world("mini", tmp_path, manifest=manifest)
    rec = [r for r in ws.simulation if r.kind == "sim_ruling_recorded"]
    assert rec and all(r.passed is False and r.attributed_stage == "triage" for r in rec)
    applied = [r for r in ws.simulation if r.kind == "sim_ruling_applied"]
    assert applied[0].passed is False and "carded again" in applied[0].evidence and applied[0].attributed_stage == "triage"
    [esc] = [r for r in ws.simulation if r.kind == "sim_escalation" and "cap-table" in r.id]
    halberd = [r for r in ws.simulation if r.kind == "sim_escalation" and "halberd" in r.id]
    assert halberd and halberd[0].attributed_stage == "compute"  # times_surfaced never incremented
    assert esc.passed is False and esc.attributed_stage == "compose" and "flat framing" in esc.evidence


def test_manifest_multi_day_assertions_run_over_all_days(tmp_path, manifest):
    manifest.assertions += [
        Assertion(id="S5-ruling", kind="ruling_applied", run_day=28,
                  args={"about": "rollout:halberd:oct-6", "run_day": 28, "expect": {"priority": "P1"}}),
        Assertion(id="S1-escalates", kind="escalation_framing", args={"about": "deal:series-a:cap-table", "min_times_surfaced": 2})]
    simulate("mini", 3, manifest, tmp_path, log=lambda _: None, digest_cmd=fake_digest(tmp_path, manifest, good=True),
             use_llm=False)
    ws = score_world("mini", tmp_path, manifest=manifest)
    got = {a.id: a.passed for a in ws.assertions if a.id in ("S5-ruling", "S1-escalates")}
    assert got == {"S5-ruling": True, "S1-escalates": True}


def test_no_transcript_means_not_run(tmp_path, manifest):
    assert score_simulation(manifest, {}, None, [])[0].passed is None
    make_run(tmp_path, manifest, 30, [])
    assert score_world("mini", tmp_path, manifest=manifest).simulation is None


def test_fresh_sets_state_aside_without_deleting(tmp_path, manifest):
    (tmp_path / "rulings.yaml").write_text("[]")
    (tmp_path / "store.sqlite").write_text("x")
    moved = set_aside_state(tmp_path)
    assert len(moved) == 2 and not (tmp_path / "rulings.yaml").exists()
    assert len(list(tmp_path.glob("rulings.yaml.bak-*"))) == 1 and len(list(tmp_path.glob("store.sqlite.bak-*"))) == 1
    logs = []
    (tmp_path / "rulings.yaml").write_text("[]")
    simulate("mini", 1, manifest, tmp_path, log=logs.append, fresh=True,
             digest_cmd=fake_digest(tmp_path, manifest, good=True), use_llm=False)
    assert logs[0].startswith("fresh: rulings.yaml")
