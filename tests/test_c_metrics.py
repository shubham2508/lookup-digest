"""Per-stage metrics (eval.md §2) on the fake run, whose planted defects are listed in make_fake_run.py."""
import pytest

from eval.scorer.artifacts import RunView
from eval.scorer.compute import score_compute
from eval.scorer.digest_metrics import score_digest, score_materializer, sentence_count, stale_profile_values
from eval.scorer.extraction import score_extraction
from eval.scorer.match import SourceIndex
from eval.scorer.runner import score_world
from eval.scorer.triage import score_triage
from tests.c_helpers import DAY, MINI_RUNS, ROOT, mini_manifest


@pytest.fixture(scope="module")
def manifest():
    return mini_manifest()


@pytest.fixture(scope="module")
def view(manifest):
    return RunView(MINI_RUNS / "2026-09-24T06-00", SourceIndex(manifest), ROOT, day=DAY)


def whats(sm):
    return [m.what for m in sm.misses]


def test_rendered_view_is_built_from_compose_and_reduce(view):
    assert [(r.id, r.placement, r.section) for r in view.rendered] == [
        ("i1", "one_thing", "urgent"), ("i2", "section", "urgent"), ("i3", "section", "decisions"),
        ("i6", "section", "pulse"), ("i4", "section", "calendar_personal"), ("i5", "section", "calendar_personal")]
    i1 = view.rendered[0]
    assert i1.source_ids == {"t-marcus-captable"} and i1.candidate_types == ["commitment_overdue", "commitment_not_in_tasks"]
    assert i1.action_types == ["task", "forward_delegate"]
    assert not view.missing


def test_extraction_metrics(view, manifest):
    sm = score_extraction(view, manifest)
    m = sm.metrics
    assert m["type_accuracy"] == 1.0 and m["items_without_extraction"] == 0
    assert m["intent_primary_accuracy"] == pytest.approx(0.667, abs=1e-3)  # Sam's thread: fyi, label ask
    assert m["commitments"] == {"precision": 1.0, "recall": 1.0, "tp": 1, "fp": 0, "fn": 0}  # captable ~ cap-table
    assert m["due_date_accuracy"] == 1.0 and m["asks_recall"] == 1.0
    assert m["evidence_dropped"] == 1 and m["evidence_validity"] == pytest.approx(10 / 11, abs=1e-3)
    assert m["automated_action_kind_accuracy"] == 1.0
    assert whats(sm) == ["t-sam-daycare: intent_primary"]
    assert all(x.stage == "extraction" for x in sm.misses)


def test_compute_metrics(view, manifest):
    sm = score_compute(view, manifest, DAY)
    m = sm.metrics
    assert m["contact_category_accuracy"] == 0.75 and m["contact_tier_accuracy"] == 1.0
    assert m["about_merge_accuracy"] == 1.0 and m["about_merge_pairs_unlogged"] == 0
    assert m["candidates"] == {"precision": 0.875, "recall": 0.875, "tp": 7, "fp": 1, "fn": 1}
    assert "candidate news_attachment rollout:halberd:oct-6" in whats(sm)
    assert "contact dana@lumenanalytics.example: category" in whats(sm)


def test_triage_metrics(view, manifest):
    sm = score_triage(view, manifest, DAY)
    m = sm.metrics
    assert m["include"] == {"precision": 1.0, "recall": pytest.approx(0.833, abs=1e-3), "tp": 5, "fp": 0, "fn": 1}
    assert m["priority_accuracy"] == 0.8 and m["priority_confusion"]["P2"] == {"P3": 1}
    assert m["section_accuracy"] == 1.0
    assert m["action_confusion"]["decide"] == {"calendar_response": 1}
    assert m["action_recall"] == pytest.approx(6 / 7, abs=1e-3)
    assert set(whats(sm)) == {"family:daycare: excluded by triage", "meeting:lumen-demo: priority",
                              "meeting:lumen-demo: proposed action decide"}


def test_digest_metrics_p0_gate_fails_on_the_triage_drop(view, manifest):
    sm = score_digest(view, manifest, DAY)
    m = sm.metrics
    assert m["p0_expected"] == 3 and m["p0_recall"] == pytest.approx(0.667, abs=1e-3) and m["p0_gate"] is False
    assert m["one_thing_correct"] is True and m["must_not_rate"] == 0.0
    assert m["section_placement_accuracy"] == 1.0 and m["length_ok"] and m["header_present"]
    assert m["items_cited_rate"] == 1.0 and m["verify_unresolved"] == 0 and m["compose_reduce_flags"] == []
    [miss] = sm.misses
    assert miss.stage == "triage" and miss.link.endswith("triage.jsonl#L8")


def test_materializer_checks(view, manifest):
    sm = score_materializer(view, manifest)
    m = sm.metrics
    assert m["drafts"] == 2 and m["banned_phrases_absent"] == 0.5 and m["max_sentences_ok"] == 1.0
    assert m["no_never_draft_recipient"] == 1.0 and m["assumptions_shown"] == 1.0
    assert sm.misses[0].stage == "materializer" and sm.misses[0].link.endswith("actions.jsonl#L3")


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


def test_missing_artifacts_are_misses_not_crashes(tmp_path, manifest):
    import shutil

    d = tmp_path / "2026-09-24T06-00"
    shutil.copytree(MINI_RUNS / "2026-09-24T06-00", d)
    for f in ("compose.json", "reduce.json", "triage.jsonl"):
        (d / f).unlink()
    ws = score_world("tests/fixtures/mini", tmp_path, manifest=manifest)
    c = ws.runs[DAY].stages["compose"]
    assert c.metrics["p0_recall"] == 0.0
    assert {m.stage for m in c.misses} == {"triage"}
    assert set(ws.runs[DAY].missing_artifacts) == {"compose", "reduce", "triage"}
