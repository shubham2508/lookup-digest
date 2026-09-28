"""Track A · M9: digest history (times_surfaced, resolved_later, answered-after-digest), rulings and `digest answer`."""
import json
from datetime import datetime

import yaml
from a_fakes import AVERY, msg, thread

from digest.history import load_rulings, make_ruling, mark_resolved, record_items, save_ruling, times_surfaced
from digest.runs import parse_as_of
from digest.schemas import Candidate, ComposeResult, ReduceItem, SectionBlock
from digest.store import Store
from digest.triage import ruling_matches


def _run_row(store, run_id, as_of, **kw):
    store.upsert("runs", {"run_id": run_id, "world": "w", "as_of": as_of, "variant": None, "customize": None, "baseline": False, "cost_usd": 0, "created_at": "x", **kw})


def test_times_surfaced_resolved_and_record(tmp_path):
    with Store(tmp_path / "s.sqlite") as st:
        day1, day2 = "2026-09-22T06:00:00-07:00", "2026-09-23T06:00:00-07:00"
        _run_row(st, "w/d1", day1)
        _run_row(st, "w/d2", day2)
        _run_row(st, "w/d2v", day2, variant="stale_inbox")     # variant runs never count
        items = {"i1": ReduceItem(id="i1", about="deal:series-a:cap-table", candidate_ids=["c1"], priority="P0", section="urgent"),
                 "i2": ReduceItem(id="i2", about="rollout:halberd", candidate_ids=["c2"], priority="P1", section="urgent")}
        comp = ComposeResult(one_thing_id="i1", sections=[SectionBlock(name="urgent", item_ids=["i2"])], items=[], header_notes=[], cut_ids=[])
        record_items(st, "w/d1", items, comp, [], [], {"i1": ["task"]}, {})
        record_items(st, "w/d2", items, comp, [], [], {"i1": ["task"]}, {"deal:series-a:cap-table": 1})
        record_items(st, "w/d2v", items, comp, [], [], {}, {})
        st.commit()
        ts = times_surfaced(st, "w", parse_as_of("2026-09-24T06:00"))
        assert ts == {"deal:series-a:cap-table": 2, "rollout:halberd": 2}
        assert times_surfaced(st, "w", parse_as_of("2026-09-22T06:00")) == {}
        # today only the cap table is still open → the rollout item resolves
        n = mark_resolved(st, "w", parse_as_of("2026-09-24T06:00"), [Candidate(candidate_id="c9", type="reply_owed", about="deal:series-a:cap-table")])
        assert n == 2 and times_surfaced(st, "w", parse_as_of("2026-09-24T06:00")) == {"deal:series-a:cap-table": 2}
        row = st.get("digest_items", run_id="w/d1", item_id="i2")
        assert row["resolved_later"] == 1 and row["resolved_at"].startswith("2026-09-24")


def test_answered_after_digest_suppresses_resurfacing(tmp_path):
    from digest.history import answered_after_digest
    with Store(tmp_path / "s.sqlite") as st:
        _run_row(st, "w/d1", "2026-09-23T06:00:00-07:00")
        items = {"i1": ReduceItem(id="i1", about="rollout:halberd", candidate_ids=["c1"], priority="P1", section="urgent")}
        record_items(st, "w/d1", items, ComposeResult(one_thing_id="i1", sections=[], items=[], header_notes=[], cut_ids=[]), [], [], {}, {})
        m1 = msg("r1", "2026-09-22T14:08", "renee.tan@halberd.com", subject="rollout")
        m2 = msg("a1", "2026-09-23T12:00", AVERY, to=["renee.tan@halberd.com"], subject="Re: rollout")
        t = thread(m1, m2)
        c = Candidate(candidate_id="c1", type="reply_owed", about="rollout:halberd", facts={"thread_id": t.thread_id})
        assert answered_after_digest(st, "w", parse_as_of("2026-09-24T06:00"), [c], {t.thread_id: t}) == {"c1"}
        t2 = thread(m1)
        c2 = Candidate(candidate_id="c2", type="reply_owed", about="rollout:halberd", facts={"thread_id": t2.thread_id})
        assert answered_after_digest(st, "w", parse_as_of("2026-09-24T06:00"), [c2], {t2.thread_id: t2}) == set()


def test_rulings_roundtrip_and_matching(tmp_path):
    path = tmp_path / "rulings.yaml"
    item = {"about": "rollout:northstar", "entities": ["tomas-reyes"], "candidate_types": ["reply_owed"], "question": "Northstar forward?",
            "options": ["renewal risk", "billing: delegate", "FYI"]}
    r = make_ruling("Q1", 2, item, "Q1 · Northstar forward?", datetime.fromisoformat("2026-09-24T06:10:00-07:00"))
    assert make_ruling("Q1", 1, item, "", datetime.fromisoformat("2026-09-28T13:00:00-07:00"), digest_day="2026-09-21")["id"] == "R-20260921-Q1"
    assert r["id"] == "R-20260924-Q1" and r["ruling"] == "billing: delegate" and r["scope"] == {"about": "rollout:northstar", "contact": "tomas-reyes", "thread_kind": "reply_owed"}
    save_ruling(path, r)
    save_ruling(path, dict(r, ruling="changed"))     # same id → replaced, not duplicated
    data = yaml.safe_load(path.read_text())
    assert len(data["rulings"]) == 1 and data["rulings"][0]["ruling"] == "changed"
    assert load_rulings(path, parse_as_of("2026-09-25T06:00"))[0]["from_question"] == "Q1"
    assert load_rulings(path, parse_as_of("2027-01-25T06:00")) == [], "expired rulings are not applied"
    c = Candidate(candidate_id="c1", type="reply_owed", about="rollout:northstar:plant-2", entities=["tomas-reyes"])
    assert ruling_matches(r, c)
    assert not ruling_matches({"scope": {"about": "offer:someone"}}, Candidate(candidate_id="c2", type="task_due", about="offer:mei"))


def test_answer_command_writes_ruling(tmp_path, monkeypatch):
    from digest import answer as ans
    from digest.config import load_settings
    settings = load_settings().model_copy(update={"store": load_settings().store.model_copy(update={
        "path_template": str(tmp_path / "runs/{world}/store.sqlite"), "rulings_path_template": str(tmp_path / "runs/{world}/rulings.yaml")})})
    monkeypatch.setattr(ans, "ROOT", tmp_path)
    run_dir = tmp_path / "runs" / "w" / "2026-09-24T06-00"
    run_dir.mkdir(parents=True)
    (run_dir / "actions.jsonl").write_text(json.dumps({"item_id": "i2", "type": "question", "target": None, "brief": "b",
                                                       "text": "Q1 · Is Oct 6 firm? (1) yes, confirm (2) check with Jordan first. Default if unanswered: 1 → digest answer Q1 1"}) + "\n")
    (run_dir / "reduce.json").write_text(json.dumps({"items": [{"id": "i2", "about": "rollout:halberd:oct-6", "entities": ["renee-tan"], "candidate_types": ["reply_owed"],
                                                                "ambiguity": {"type": "preference", "question": "Is Oct 6 firm?", "options": ["yes, confirm", "check with Jordan first"], "default": 1}}]}))
    r = ans.answer("q1", 2, "w", settings, now=datetime.fromisoformat("2026-09-24T06:30:00-07:00"))
    assert r["ruling"] == "check with Jordan first" and r["scope"]["about"] == "rollout:halberd:oct-6"
    assert (tmp_path / "runs/w/rulings.yaml").exists()
    with Store(tmp_path / "runs/w/store.sqlite") as st:
        assert st.get("rulings", id=r["id"])["option_chosen"] == 2
    try:
        ans.answer("Q7", 1, "w", settings)
        raise AssertionError("expected NoSuchQuestion")
    except ans.NoSuchQuestion:
        pass
