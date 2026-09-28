from digest.store import SCHEMA, Store


def test_upsert_get_query(tmp_path):
    with Store(tmp_path / "s.sqlite") as s:
        assert set(s.tables()) == set(SCHEMA)
        s.upsert("tasks", {"task_id": "t1", "title": "a", "due": "2026-09-24", "status": "open", "extra": {"x": 1}})
        s.upsert("tasks", {"task_id": "t1", "title": "b", "due": "2026-09-24", "status": "done", "extra": {"x": 2}})
        s.commit()
        assert s.count("tasks") == 1
        row = s.get("tasks", task_id="t1")
        assert row["title"] == "b" and row["status"] == "done" and row["extra"] == {"x": 2}
        n = s.upsert_many("candidates", [
            {"run_id": "r", "candidate_id": "c2", "type": "task_due", "about": "report:q2"},
            {"run_id": "r", "candidate_id": "c1", "type": "reply_owed", "about": "deal:x", "facts": {"hours": 3}},
        ])
        assert n == 2
        rows = s.query("candidates", "run_id=?", ("r",), order="candidate_id")
        assert [r["candidate_id"] for r in rows] == ["c1", "c2"] and rows[0]["facts"] == {"hours": 3}
        assert s.get("candidates", run_id="r", candidate_id="zz") is None


def test_reopen_keeps_data(tmp_path):
    p = tmp_path / "s.sqlite"
    with Store(p) as s:
        s.upsert("rulings", {"id": "R1", "ruling": "delegate Northstar forwards to Tomás", "option_chosen": 2,
                             "from_question": "Q1", "created": "2026-09-24", "expires": None, "scope": {"about": "x"}})
        s.commit()
    with Store(p) as s:
        r = s.get("rulings", id="R1")
        assert r["option_chosen"] == 2 and r["scope"] == {"about": "x"}
