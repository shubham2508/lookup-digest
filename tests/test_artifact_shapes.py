from digest.runs import RunContext, parse_as_of
from digest.schemas import MaterializedAction, ReduceItem, ReduceResult, VerifyResult, VerifyViolation


def test_reduce_and_verify_roundtrip():
    r = ReduceResult(items=[ReduceItem(id="i1", about="deal:series-a:cap-table", candidate_ids=["c1", "c2"],
                                       candidate_types=["commitment_overdue", "commitment_not_in_tasks"],
                                       priority="P0", section="urgent", why="promised Tuesday night; nothing sent")],
                     overflow=["i9"], about_merges=[{"canonical": "deal:series-a:cap-table", "merged": ["deal:series-a:captable"]}])
    assert ReduceResult.model_validate_json(r.model_dump_json()) == r
    v = VerifyResult(violations=[VerifyViolation(rule=1, item_id="i3", detail="draft to Sam", fix="dropped")])
    assert v.stats.header_present is False and v.violations[0].fix == "dropped"
    a = MaterializedAction(item_id="i1", type="task", target="Send cap table to Marcus", text="☐ Send cap table — due 11:00")
    assert a.draft is None and not a.llm


def test_run_dir_suffix_for_customize_and_baseline(tmp_path):
    dt = parse_as_of("2026-09-24T06:00")
    assert RunContext("dev", dt, runs_dir=tmp_path).suffix is None
    assert RunContext("dev", dt, runs_dir=tmp_path, customize=tmp_path / "board_prep.md").run_dir.name == "2026-09-24T06-00_customize-board_prep"
    assert RunContext("dev", dt, runs_dir=tmp_path, baseline=True).run_dir.name == "2026-09-24T06-00_baseline"
    both = RunContext("dev", dt, runs_dir=tmp_path, variant="stale_inbox", customize=tmp_path / "weekend.md")
    assert both.run_dir.name == "2026-09-24T06-00_stale_inbox+customize-weekend"
    assert both.finish()["suffix"] == "stale_inbox+customize-weekend"


def test_write_json_handles_lists_of_models(tmp_path):
    from digest.schemas import Contact
    ctx = RunContext("dev", parse_as_of("2026-09-24T06:00"), runs_dir=tmp_path)
    ctx.write_json("contacts", [Contact(contact_id="sam-park", names=["Sam Park"]), Contact(contact_id="x")])
    data = ctx.read_json("contacts")
    assert isinstance(data, list) and data[0]["contact_id"] == "sam-park" and data[0]["names"] == ["Sam Park"]
    ctx.write_json("reduce", {"items": [ReduceItem(id="i1", about="deal:x", candidate_ids=[], priority="P1", section="pulse")]})
    assert ctx.read_json("reduce")["items"][0]["about"] == "deal:x"


def test_tag_in_suffix(tmp_path):
    dt = parse_as_of("2026-09-24T06:00")
    assert RunContext("dev", dt, runs_dir=tmp_path, tag="sim").run_dir.name == "2026-09-24T06-00_sim"
    assert RunContext("dev", dt, runs_dir=tmp_path, variant="no_notes", tag="sim").run_dir.name == "2026-09-24T06-00_no_notes+sim"
