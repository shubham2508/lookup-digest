"""v2 metrics (PIVOT_SPEC §6) on the fake run, whose planted defects are listed in make_fake_run.py: the digest-level
target, and the diagnostics (readers, sweeps and nets, merge, judgment, spine, materializer)."""
import pytest

from eval.manifest_schema import (
    ExpectedCandidate,
    ExpectedCommitment,
    ExpectedItem,
    ItemLabel,
    MessageLabel,
    RunDayExpectation,
)
from eval.scorer.artifacts import RunView
from eval.scorer.digest_metrics import score_digest, score_materializer, sentence_count, stale_profile_values
from eval.scorer.match import SourceIndex
from eval.scorer.merge import score_merge
from eval.scorer.readers import label_says_yes, score_readers, thread_expectation, visible
from eval.scorer.runner import score_world
from eval.scorer.spine import score_spine
from eval.scorer.sweeps import score_sweeps
from eval.scorer.triage import score_triage
from tests.c_helpers import DAY, MINI_RUNS, ROOT, finding_row, make_run, mini_manifest

MARCUS = "msg:<20260922-1642.marcus@inflectionpoint.vc>"
RENEE = "msg:<20260922-1408.renee@halberd.com>"
SAM = "msg:<20260923-2110.sam@parkfamily.example>"


@pytest.fixture(scope="module")
def manifest():
    return mini_manifest()


@pytest.fixture(scope="module")
def view(manifest):
    return RunView(MINI_RUNS / "2026-09-24T06-00", SourceIndex(manifest), ROOT, day=DAY)


def whats(sm):
    return [m.what for m in sm.misses]


def load(d, manifest, day=DAY):
    return RunView(d, SourceIndex(manifest), ROOT, day=day)


def test_rendered_view_is_built_from_compose_and_reduce(view):
    assert [(r.id, r.placement, r.section) for r in view.rendered] == [
        ("i1", "one_thing", "urgent"), ("i2", "section", "urgent"), ("i3", "section", "decisions"),
        ("i6", "section", "pulse"), ("i4", "section", "calendar_personal"), ("i5", "section", "calendar_personal")]
    i1 = view.rendered[0]
    assert i1.source_ids == {"t-marcus-captable"}
    assert i1.candidate_types == ["overdue promise to lead investor", "promise missing from tasks"]
    assert [s.origin for s in view.item_signals(i1)] == ["thread_reader", "notes_tasks_sweep"]
    assert i1.action_types == ["task", "forward_delegate"]
    assert not view.missing


def test_findings_become_signals(view):
    by_id = {s.row.data["finding_id"]: s for s in view.signals}
    assert set(by_id) == {f"f{i}" for i in range(1, 9)}  # every finding, each candidate covered by its finding
    assert by_id["f1"].thread == "t-marcus-captable" and by_id["f1"].live and by_id["f1"].stage == "read"
    assert by_id["f8"].needs_avery == "no" and not by_id["f8"].live and by_id["f8"].candidate_id is None
    assert by_id["f6"].rescued and by_id["f6"].stage == "net" and by_id["f5"].stage == "sweep"
    assert by_id["f2"].abouts == ["deal:series-a:cap-table", "deal:series-a:cap-table"]


# ----------------------------------------------------------------------------- C1 reader diagnostics
def test_reader_diagnostics(view, manifest):
    sm = score_readers(view, manifest, DAY)
    m = sm.metrics
    assert m["reader_recall"] == pytest.approx(0.667, abs=1e-3) and m["expected_yes"] == 3
    assert m["priority_in_band"] == 1.0 and m["expected_action_present"] == 1.0
    assert m["noise_items_clean"] == 1.0 and m["threads_not_fully_visible"] == 0
    [miss] = sm.misses
    assert miss.what.startswith("t-sam-daycare (S11): needs_avery") and miss.got == "no" and miss.stage == "read"
    assert miss.link.endswith("findings.jsonl#L8")


def _thread(sid="t-x", *, must_not=False, ball="avery", commitments=(), about=("other:x",), msgs=((28, "10:00"),)):
    from eval.manifest_schema import ExpectedExtraction

    return ItemLabel(source_id=sid, kind="thread", must_not_surface=must_not, must_not_reason="fyi" if must_not else None,
                     expected=ExpectedExtraction(type="human_thread", about=list(about), ball_awaiting=ball,
                                                 commitments=list(commitments)),
                     messages=[MessageLabel(message_id=f"<{d}-{t}@x>", day=d, time=t, from_email="a@x") for d, t in msgs])


def test_thread_expectation_rules():
    rd = RunDayExpectation(run_day=30, items=[ExpectedItem(about="other:x", priority="P1", actions=["reply"], cites_any=["t-x"])])
    te = thread_expectation(_thread(), rd)
    assert (te.expect, te.bands, te.actions) == ("yes", ["P1"], ["reply"])
    # a must-not thread behind an included item (recruiter pattern, cadence watch): not the reader's call
    assert thread_expectation(_thread(must_not=True), rd).expect is None
    empty = RunDayExpectation(run_day=30)
    assert thread_expectation(_thread(must_not=True), empty).expect == "no"                 # the precision set
    held = RunDayExpectation(run_day=30, absent=["other:x"])
    assert thread_expectation(_thread(), held).expect == "no"                               # timing trap (S3)
    assert thread_expectation(_thread(ball="other"), empty).expect == "no"                  # label decides
    assert thread_expectation(_thread(), empty).expect == "yes"
    fulfilled = ExpectedCommitment(owner="avery", about="other:x", fulfilled_by_source="t-y")  # S16: kept elsewhere
    assert not label_says_yes(_thread(ball="other", commitments=[fulfilled]))
    assert label_says_yes(_thread(ball="other", commitments=[ExpectedCommitment(owner="avery", about="other:x")]))


def test_visibility_follows_as_of():
    t = _thread(msgs=((28, "10:00"), (30, "05:00")))
    assert visible(t, 30, "06:00") == "all" and visible(t, 29, "06:00") == "some" and visible(t, 27, "06:00") == "none"


def test_reader_precision_on_must_not_threads(tmp_path, manifest):
    m = manifest.model_copy(deep=True)
    m.item("t-sam-daycare").must_not_surface = True
    rd = m.run_day(DAY)
    rd.items = [ei for ei in rd.items if ei.about != "family:daycare"]
    loud = finding_row("f-sam", "thread_reader", "yes", "family logistics", ["family:daycare"],
                       [{"source_id": SAM, "quote": "q"}], [], None, thread="thread:20260923-2110.sam@parkfamily.example")
    d = make_run(tmp_path, m, DAY, [{"id": "a", "about": "deal:series-a:cap-table", "cites": [MARCUS]}], findings=[loud])
    sm = score_readers(load(d, m), m, DAY)
    assert sm.metrics["must_not_precision"] == 0.0 and sm.metrics["must_not_threads"] == 1
    assert any(x.what.startswith("t-sam-daycare (S11): must not surface") for x in sm.misses)


# ----------------------------------------------------------------------------- C2 sweeps, nets, rescues, merge
def test_sweep_and_net_diagnostics(view, manifest):
    sm = score_sweeps(view, manifest, DAY)
    m = sm.metrics
    assert m["trap_recall"] == 1.0 and m["calendar_traps_found"] == "2/2" and m["notes_tasks_traps_found"] == "1/1"
    assert m["traps_found_by_origin"] == {"calendar_sweep": 1, "safety_net": 1, "notes_tasks_sweep": 1}
    assert m["rescues"] == 2 and m["rescues_by_kind"] == {"approval_pending": 1, "calendar_conflict:family": 1}
    assert m["rescues_matching_expected"] == 2
    [rescues] = sm.lists.values()
    assert rescues[0].startswith("approval_pending · 'Sign Mei Tanaka's offer letter' (P1) → offer:mei-tanaka (P1)")
    assert "findings.jsonl#L6" in rescues[1] and "family:pediatrician (P0)" in rescues[1]
    assert not sm.misses


def test_contradiction_trap_needs_the_contradiction_field(tmp_path, manifest):
    m = manifest.model_copy(deep=True)
    m.run_day(DAY).candidates.append(ExpectedCandidate(type="contradiction", about="report:q2-planning"))
    item = {"id": "q2", "about": "report:q2-planning", "ctype": "task due today", "origin": "notes_tasks_sweep",
            "cites": ["task:2"], "section": "pulse", "priority": "P2"}
    sm = score_sweeps(load(make_run(tmp_path / "a", m, DAY, [item]), m), m, DAY)
    assert "trap contradiction report:q2-planning" in whats(sm)   # the about matches, but nothing says "contradicts"
    assert "trap task_due report:q2-planning" not in whats(sm)
    assert "trap calendar_conflict:family family:pediatrician (S11)" in whats(sm)  # this run has no calendar findings
    assert {x.stage for x in sm.misses} == {"sweep"}
    flagged = finding_row("f-c", "notes_tasks_sweep", "yes", "stale number in the plan", ["report:q2-planning"],
                          [{"source_id": "task:2", "quote": "q"}], [], None, contradictions=["plan says 3.2; finance says 3.4"])
    sm = score_sweeps(load(make_run(tmp_path / "b", m, DAY, [item], findings=[flagged]), m), m, DAY)
    assert not any("report:q2-planning" in w for w in whats(sm)) and sm.metrics["notes_tasks_traps_found"] == "2/2"


def test_merge_diagnostics(view, manifest, tmp_path):
    sm = score_merge(view, manifest, DAY)
    assert sm.metrics["expected_items_rendered_twice"] == 0 and sm.metrics["items_merging_expected_items"] == 0
    assert sm.metrics["about_merge_accuracy"] == 1.0
    twice = [{"id": "a", "about": "deal:series-a:cap-table", "cites": [MARCUS]},
             {"id": "b", "about": "deal:series-a:captable", "cites": [MARCUS], "placement": "also_pending"}]
    sm = score_merge(load(make_run(tmp_path / "t", manifest, DAY, twice), manifest), manifest, DAY)
    assert sm.metrics["expected_items_rendered_twice"] == 1 and sm.misses[0].stage == "merge"
    merged = [{"id": "m", "about": "deal:series-a:cap-table", "cites": [MARCUS, RENEE],
               "about_tags": ["deal:series-a:cap-table", "rollout:halberd:oct-6"]}]
    sm = score_merge(load(make_run(tmp_path / "m", manifest, DAY, merged), manifest), manifest, DAY)
    assert sm.metrics["items_merging_expected_items"] == 1
    assert "m: one item for 2 expected items" in whats(sm)


# ----------------------------------------------------------------------------- judgment, spine, digest, materializer
def test_judgment_metrics(view, manifest):
    sm = score_triage(view, manifest, DAY)
    m = sm.metrics
    assert m["include"] == {"precision": 1.0, "recall": pytest.approx(0.833, abs=1e-3), "tp": 5, "fp": 0, "fn": 1}
    assert m["priority_accuracy"] == 0.8 and m["priority_confusion"]["P2"] == {"P3": 1}
    assert m["section_accuracy"] == 1.0 and m["hard_rule_violations"] == 0
    assert m["action_confusion"]["decide"] == {"calendar_response": 1}
    assert m["action_recall"] == pytest.approx(6 / 7, abs=1e-3)
    by = {x.what.split(" (")[0]: x.stage for x in sm.misses}
    assert by == {"family:daycare: never surfaced": "read", "meeting:lumen-demo: priority": "sweep",
                  "meeting:lumen-demo: proposed action decide": "sweep"}


def test_hard_rules(tmp_path, manifest):
    items = [{"id": "s", "about": "family:daycare", "cites": [SAM], "priority": "P0",
              "actions": [{"type": "reply", "target": "sam@parkfamily.example"}]},
             {"id": "u", "about": "other:uncited", "cites": [], "priority": "P2"}]
    sus = finding_row("f-x", "thread_reader", "yes", "invoice", ["invoice:x"], [{"source_id": RENEE, "quote": "q"}], [],
                      "c-s", priority="P0", suspicious=[{"source_id": RENEE, "quote": "pay now"}])
    d = make_run(tmp_path, manifest, DAY, items, findings=[sus])
    sm = score_triage(load(d, manifest), manifest, DAY)
    hard = [x for x in sm.misses if any(k in x.what for k in ("never-draft", "suspicious", "without a citation"))]
    assert sm.metrics["hard_rule_violations"] == 3 and {x.stage for x in hard} == {"net"}
    assert any("reply to never-draft contact sam@parkfamily.example" in x.what for x in hard)


def test_spine_metrics(view, manifest):
    sm = score_spine(view, manifest, DAY)
    m = sm.metrics
    assert m["contact_category_accuracy"] == 0.75 and m["contact_tier_accuracy"] == 1.0
    assert "contact dana@lumenanalytics.example: category" in whats(sm) and {x.stage for x in sm.misses} == {"spine"}


def test_digest_metrics_p0_gate_fails_on_the_reader(view, manifest):
    sm = score_digest(view, manifest, DAY)
    m = sm.metrics
    assert m["p0_expected"] == 3 and m["p0_recall"] == pytest.approx(0.667, abs=1e-3) and m["p0_gate"] is False
    assert m["one_thing_correct"] is True and m["must_not_rate"] == 0.0
    assert m["section_placement_accuracy"] == 1.0 and m["length_ok"] and m["header_present"]
    assert m["items_cited_rate"] == 1.0 and m["verify_unresolved"] == 0 and m["compose_reduce_flags"] == []
    [miss] = sm.misses
    assert miss.stage == "read" and miss.link.endswith("findings.jsonl#L8")


def test_materializer_checks(view, manifest):
    sm = score_materializer(view, manifest)
    m = sm.metrics
    assert m["drafts"] == 2 and m["banned_phrases_absent"] == 0.5 and m["max_sentences_ok"] == 1.0
    assert m["no_never_draft_recipient"] == 1.0 and m["assumptions_shown"] == 1.0
    assert sm.misses[0].stage == "materialize" and sm.misses[0].link.endswith("actions.jsonl#L3")


def test_sentence_count_ignores_signoff():
    assert sentence_count("renee, yes. it's on.\nAvery") == 2
    assert sentence_count("one. two! three? four.") == 4
    assert sentence_count("no punctuation at all") == 1


def test_numbers_from_data_beat_the_profile(manifest):
    from eval.manifest_schema import ExpectedClaim

    m = manifest.model_copy(deep=True)
    m.items[0].expected.claims.append(ExpectedClaim(subject="ARR", value="$3.4M"))
    stale = stale_profile_values(m)
    assert stale == {"arr": ("$3.2M", {"$3.4M"})}


def test_world_headline(manifest):
    ws = score_world("tests/fixtures/mini", MINI_RUNS, manifest=manifest)
    h = ws.headline()
    assert h == {"p0_recall": pytest.approx(0.667, abs=1e-3), "p0_gate": False, "traps_passed": "7/7", "traps_not_run": 0,
                 "must_not_rate": 0.0, "one_thing_accuracy": 1.0, "cost_per_run": 0.0123, "runs_scored": 1}
    assert set(ws.runs[DAY].stages) == {"digest", "read", "sweep", "merge", "judgment", "spine", "materialize"}


def test_missing_artifacts_are_misses_not_crashes(tmp_path, manifest):
    import shutil

    d = tmp_path / "2026-09-24T06-00"
    shutil.copytree(MINI_RUNS / "2026-09-24T06-00", d)
    for f in ("compose.json", "reduce.json", "triage.jsonl"):
        (d / f).unlink()
    ws = score_world("tests/fixtures/mini", tmp_path, manifest=manifest)
    c = ws.runs[DAY].stages["digest"]
    assert c.metrics["p0_recall"] == 0.0
    # the findings survive: the reader's cap table and the net's pediatrician have no triage row; Sam's reader said no
    assert {m.stage for m in c.misses} == {"read", "net"}
    assert set(ws.runs[DAY].missing_artifacts) == {"compose", "reduce", "triage"}
