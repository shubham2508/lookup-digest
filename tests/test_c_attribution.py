"""Stage attribution walks extraction → compute → triage → compose → materializer and stops at the first loss."""
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


def _edit_jsonl(path, keep):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows if keep(r)))


def _edit_json(path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def attribute(d, **want):
    m = mini_manifest()
    return attribute_missing(RunView(d, SourceIndex(m), ROOT, day=DAY), m, HALBERD[0], HALBERD[1], **want)


def test_lost_at_extraction(run):
    # the sprint note shares the about key, but only the cited thread's own extraction counts
    _edit_jsonl(run / "extractions.jsonl", lambda r: "renee" not in r["source_id"])
    _edit_jsonl(run / "candidates.jsonl", lambda r: r["candidate_id"] != "c3")
    a = attribute(run)
    assert a.stage == "extraction" and a.links[0].endswith("extractions.jsonl")


def test_lost_at_compute(run):
    _edit_jsonl(run / "candidates.jsonl", lambda r: r["candidate_id"] != "c3")
    assert attribute(run).stage == "compute"


def test_lost_at_triage(run):
    lines = (run / "triage.jsonl").read_text().splitlines()
    rows = [json.loads(x) for x in lines]
    rows[2]["include"] = False
    (run / "triage.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    a = attribute(run)
    assert a.stage == "triage" and a.links[0].endswith("triage.jsonl#L3")
    assert attribute(MINI_RUNS / RUN, priority="P0").stage == "triage"


def test_lost_at_compose(run):
    def drop(c):
        c["sections"] = [dict(b, item_ids=[i for i in b["item_ids"] if i != "i2"]) for b in c["sections"]]
    _edit_json(run / "compose.json", drop)
    a = attribute(run)
    assert a.stage == "compose" and "not placed by compose" in a.evidence


def test_dropped_by_verify_is_compose(run):
    _edit_json(run / "verify.json", lambda v: v["violations"].append({"rule": 9, "item_id": "i2", "fix": "dropped"}))
    a = attribute(run)
    assert a.stage == "compose" and a.evidence == "dropped by verify"


def test_present_but_action_wrong_is_materializer():
    a = attribute(MINI_RUNS / RUN, action="reply")
    assert a.stage == "materializer"


def test_final_action_dropped_by_compose(run):
    _edit_jsonl(run / "actions.jsonl", lambda r: not (r["item_id"] == "i2" and r["type"] == "reply"))
    assert attribute(run, action="reply").stage == "compose"
