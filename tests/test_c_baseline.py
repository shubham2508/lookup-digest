"""M8: the naive baseline is scored from digest.md alone, with the same digest-level metrics (eval.md §8)."""
import pytest
from typer.testing import CliRunner

from cli.main import app
from eval.scorer.artifacts import RunView
from eval.scorer.digest_md import Citation
from eval.scorer.markdown_view import infer_about, parse_actions, resolve_citation
from eval.scorer.match import SourceIndex
from eval.scorer.runner import score_world
from tests.c_helpers import DAY, MINI_RUNS, ROOT, mini_manifest


@pytest.fixture(scope="module")
def manifest():
    return mini_manifest()


@pytest.fixture(scope="module")
def index(manifest):
    return SourceIndex(manifest)


@pytest.mark.parametrize(("kind", "body", "want"), [
    ("email", "Marcus, Tue 16:42", {"t-marcus-captable"}),
    ("email", "Avery, Tue 21:30", {"t-marcus-captable"}),
    ("email", "Marcus Webb, Sep 22 16:42", {"t-marcus-captable"}),
    ("email", "Renee, 2026-09-22 14:08", {"t-halberd-rollout"}),
    ("email", "Sam, Wed 21:10", {"t-sam-daycare"}),
    ("email", "The Supply Chain Brief, Wed 07:00", {"nl-scbrief-212"}),
    ("email", "DocuSign, Tue 09:15", {"auto-docusign-mei"}),
    ("email", "Marcus, Wed 16:42", set()),     # wrong weekday
    ("email", "Renee, Tue 16:42", set()),      # right day, wrong sender for that time
    ("cal", "shared, added Wed 21:04", set()),  # calendar citations are not manifest items
])
def test_citation_resolver(manifest, index, kind, body, want):
    assert resolve_citation(Citation(kind, body), index, manifest) == want


def test_action_parser():
    acts = parse_actions([
        '↳ Draft to Renee: "renee, yes. Avery"', "Assumptions: sprint note says on track; Jordan agrees",
        "☐ Send cap table — due 11:00", "↳ Forward to Ben with: send v3", "↳ Propose: move to 11:15.",
        "↳ Approve in DocuSign (~1 min).", "Q1 · firm? (1) yes (2) no", "Default if unanswered: 1",
        "↳ Message Sam about the pediatrician. No draft (Sam).", "Watching: Northstar cadence. Flags again if >7d",
        "↳ Open the Northstar thread; start at message 11."])
    assert [a["type"] for a in acts] == ["reply", "task", "forward_delegate", "calendar_response", "approve", "question",
                                         "message_person", "watch", "read"]
    assert acts[0]["draft"] == "renee, yes. Avery" and acts[0]["assumptions"] == ["sprint note says on track", "Jordan agrees"]
    assert acts[2]["recipient_name"] == "Ben" and acts[6]["target"] == "Sam" and acts[6]["draft"] is None
    assert "Default if unanswered: 1" in acts[5]["text"]


def test_about_inferred_from_text_and_labels(manifest):
    keys = [ei.about for ei in manifest.run_day(DAY).items]
    assert infer_about("Send the updated cap table to Marcus", set(), keys, manifest) == "deal:series-a:cap-table"
    assert infer_about("Wren's pediatrician at 3pm", set(), keys, manifest) == "family:pediatrician"
    assert infer_about("Sort out Friday", {"t-sam-daycare"}, keys, manifest) == "family:daycare"  # cited source's label
    assert infer_about("Wren's pediatrician", {"t-sam-daycare"}, keys, manifest) == "family:pediatrician"  # text wins
    assert infer_about("Sort out Friday daycare", {"t-sam-daycare"}, keys, manifest) == "family:daycare"
    assert infer_about("Lunch", set(), keys, manifest) is None


def test_baseline_scores_digest_level_only(manifest, index):
    v = RunView(MINI_RUNS / "2026-09-24T06-00_baseline", index, ROOT, day=DAY)
    assert v.markdown_only and "compose" in v.missing
    ws = score_world("tests/fixtures/mini", MINI_RUNS, suffix="baseline", label="baseline", manifest=manifest)
    assert set(ws.runs[DAY].stages) == {"compose", "materializer"}
    h = ws.headline()
    assert h["p0_recall"] == pytest.approx(0.667, abs=1e-3) and h["one_thing_accuracy"] == 0.0
    assert h["must_not_rate"] == 1.0 and h["cost_per_run"] == 0.0451 and h["traps_passed"] == "1/5"
    na = [a.id for a in ws.assertions if a.passed is None]
    assert na == ["S12-lumen-flagged", "S12-jordan-not-flagged"]  # candidate kinds: n/a without pipeline artifacts
    c = ws.runs[DAY].stages["compose"]
    assert {m.stage for m in c.misses} == {"baseline"} and c.metrics["md_citations_valid_rate"] == 1.0
    mat = ws.runs[DAY].stages["materializer"]
    assert mat.metrics["no_never_draft_recipient"] == 0.5  # the draft to Sam


def test_pipeline_run_missing_compose_is_not_treated_as_baseline(manifest, index):
    v = RunView(MINI_RUNS / "2026-09-24T06-00", index, ROOT, day=DAY)
    assert not v.markdown_only


def test_eval_cli_has_baseline_column(tmp_path):
    r = CliRunner().invoke(app, ["eval", "--world", "tests/fixtures/mini", "--runs", str(MINI_RUNS), "--out", str(tmp_path),
                                 "--customize-suite"])
    assert r.exit_code == 0, r.output
    text = next(tmp_path.glob("*.md")).read_text()
    assert "| metric | pipeline · dev | baseline · dev |" in text  # found without --baseline because the run exists
    assert "### Naive baseline · dev" in text and "| weekend | customize | 30 |" in text
    assert "Not run yet: pipeline · heldout, baseline · heldout." in text
