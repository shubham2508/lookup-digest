"""Stage attribution walks read → sweep → net → merge → compose → materialize → verify and stops at the first loss."""
import json
import shutil

import pytest

from eval.scorer.artifacts import RunView
from eval.scorer.attribution import attribute_missing
from eval.scorer.match import SourceIndex
from tests.c_helpers import DAY, MINI_RUNS, ROOT, mini_manifest

RUN = "2026-09-24T06-00"
HALBERD = ("rollout:halberd:oct-6", ["t-halberd-rollout"])


@pytest.fixture
def run(tmp_path):
    d = tmp_path / RUN
    shutil.copytree(MINI_RUNS / RUN, d)
    return d


def _edit_jsonl(path, fn):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    rows = [r for r in (fn(r) for r in rows) if r is not None]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _edit_json(path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def _drop_c3(d):
    _edit_jsonl(d / "candidates.jsonl", lambda r: None if r["candidate_id"] == "c3" else r)
    _edit_jsonl(d / "triage.jsonl", lambda r: None if r["candidate_id"] == "c3" else r)


def _unplace_i2(c):
    c["sections"] = [dict(b, item_ids=[i for i in b["item_ids"] if i != "i2"]) for b in c["sections"]]


def attribute(d, about=HALBERD[0], cites=HALBERD[1], **want):
    m = mini_manifest()
    return attribute_missing(RunView(d, SourceIndex(m), ROOT, day=DAY), m, about, cites, **want)


def test_nobody_read_it(run):
    _edit_jsonl(run / "findings.jsonl", lambda r: None if r["finding_id"] == "f3" else r)
    _drop_c3(run)
    a = attribute(run)
    assert a.stage == "read" and a.evidence.startswith("no finding") and a.links[0].endswith("findings.jsonl")


def test_the_sweep_should_have_seen_a_task(run):
    _edit_jsonl(run / "findings.jsonl", lambda r: None if r["finding_id"] == "f7" else r)
    _edit_jsonl(run / "candidates.jsonl", lambda r: None if r["candidate_id"] == "c7" else r)
    assert attribute(run, "report:q2-planning", ["task:2"]).stage == "sweep"


def test_the_reader_said_no(run):
    _edit_jsonl(run / "findings.jsonl", lambda r: {**r, "needs_avery": "no", "candidate_id": None} if r["finding_id"] == "f3" else r)
    _drop_c3(run)
    a = attribute(run)
    assert a.stage == "read" and "not surfaced" in a.evidence and a.links[0].endswith("findings.jsonl#L3")


def test_wrong_priority_is_the_finding_origins():
    assert attribute(MINI_RUNS / RUN, priority="P0").stage == "read"          # Renee's reader said P1
    assert attribute(MINI_RUNS / RUN, "meeting:lumen-demo", [], priority="P2").stage == "sweep"


def test_code_floors_overrode_a_right_finding(run):
    # the reader said yes; enforce set include=false (a never_draft or cold-recruiter floor misfiring)
    _edit_jsonl(run / "triage.jsonl", lambda r: {**r, "include": False} if r["candidate_id"] == "c3" else r)
    a = attribute(run)
    assert a.stage == "net" and "code floors" in a.evidence and a.links[0].endswith("triage.jsonl#L3")


def test_lost_at_reduce_is_merge(run):
    _edit_json(run / "reduce.json", lambda r: r.update(items=[i for i in r["items"] if i["id"] != "i2"]))
    _edit_json(run / "compose.json", _unplace_i2)
    a = attribute(run)
    assert a.stage == "merge" and "lost at reduce" in a.evidence


def test_folded_into_another_item_is_merge(run):
    def fold(r):
        r["items"] = [i for i in r["items"] if i["id"] != "i2"]
        r["items"][0]["candidate_ids"].append("c3")   # i1 (the cap table) absorbed Renee's finding
    _edit_json(run / "reduce.json", fold)
    _edit_json(run / "compose.json", _unplace_i2)
    m = mini_manifest()
    view = RunView(run, SourceIndex(m), ROOT, day=DAY)
    # the cap-table item now carries Renee's finding, so it is matched as the Halberd item: the merge shows up
    # as an over-merge in the merge diagnostics rather than as a missing item
    assert [i.id for i in view.rendered if "c3" in i.candidate_ids] == ["i1"]


def test_lost_at_compose(run):
    _edit_json(run / "compose.json", _unplace_i2)
    a = attribute(run)
    assert a.stage == "compose" and "not placed by compose" in a.evidence


def test_dropped_by_verify(run):
    _edit_json(run / "verify.json", lambda v: v["violations"].append({"rule": 9, "item_id": "i2", "fix": "dropped"}))
    a = attribute(run)
    assert a.stage == "verify" and a.evidence == "dropped by verify"


def test_present_but_action_wrong_is_materialize():
    assert attribute(MINI_RUNS / RUN, action="reply").stage == "materialize"


def test_final_action_dropped_by_compose(run):
    _edit_jsonl(run / "actions.jsonl", lambda r: None if (r["item_id"] == "i2" and r["type"] == "reply") else r)
    assert attribute(run, action="reply").stage == "compose"
