"""Judge (E1): skipped without a model; with a (fake) model, both rubrics score and calibration compares roles."""
import json
from types import SimpleNamespace

import pytest

from digest.config import load_models
from digest.llm import LLM
from digest.prompts import load_prompt
from eval.judge.judge import RUBRICS, JudgeScores, calibrate, digest_item, draft_items, judge_items
from eval.scorer.artifacts import RunView
from eval.scorer.match import SourceIndex
from tests.c_helpers import DAY, MINI_RUNS, ROOT, mini_manifest


@pytest.fixture(scope="module")
def view():
    return RunView(MINI_RUNS / "2026-09-24T06-00", SourceIndex(mini_manifest()), ROOT, day=DAY)


@pytest.fixture
def items(view):
    return draft_items(view, "d30/") + [digest_item(view, "d30/")]


class FakeClient:
    """Stands in for the OpenAI SDK client: scores every criterion of the requested rubric."""

    def __init__(self, by_model: dict[str, int]):
        self.by_model = by_model
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **body):
        self.calls += 1
        system = body["messages"][0]["content"]
        rubric = "digest" if "RUBRIC: which rubric to apply: `digest`" in system else "draft"
        score = self.by_model[body["model"]]
        out = {"criteria": [{"name": n, "score": score, "reason": "fake"} for n in RUBRICS[rubric]]}
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.001, model_extra={})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(out)))], usage=usage)


def fake_llm(tmp_path, by_model):
    models = load_models()
    models.roles["judge"].model = "google/fake-judge"
    models.roles["judge"].family = "google"
    return LLM(models, cache_dir=tmp_path, client=FakeClient(by_model))


def test_prompt_file_is_well_formed():
    p = load_prompt("judge")
    assert (p.model_role, p.output_model) == ("judge", "JudgeScores")
    assert set(p.variables) == {"rubric", "material"}
    for names in RUBRICS.values():
        for n in names:
            assert f"`{n}`" in p.text


def test_items_cover_drafts_and_digest(items):
    assert [i.kind for i in items] == ["draft", "draft", "digest"]
    assert "just wanted to" in items[1].material and items[2].material.startswith("# Daily Digest")


def test_skipped_without_a_judge_model(tmp_path, items):
    from digest.config import load_models
    from digest.llm import LLM, CostLog

    m = load_models()   # the real config names a judge now; this test is about a config without one
    m.roles["judge"] = m.roles["judge"].model_copy(update={"model": None, "family": None})
    run = judge_items(items, llm=LLM(m, cache_dir=tmp_path / "cache", cost_log=CostLog(tmp_path / "c.jsonl")))
    assert run.status == "skipped" and run.note == "no model configured" and not run.results


def test_scores_both_rubrics(tmp_path, items):
    run = judge_items(items, llm=fake_llm(tmp_path, {"google/fake-judge": 4}))
    assert run.status == "ok" and all(not r.error for r in run.results)
    assert set(run.results[0].scores) == set(RUBRICS["draft"])
    assert set(run.results[2].scores) == set(RUBRICS["digest"])
    assert run.means() == dict.fromkeys(RUBRICS["draft"] + RUBRICS["digest"], 4.0)


def test_calibration_agreement(tmp_path, items):
    ref = "anthropic/claude-fable-5.1"
    close = calibrate(items, llm=fake_llm(tmp_path / "a", {ref: 5, "google/fake-judge": 4}))
    assert close.agreement == 1.0 and close.keep_cheap_judge is True and len(close.rows) == 9
    far = calibrate(items, llm=fake_llm(tmp_path / "b", {ref: 5, "google/fake-judge": 2}))
    assert far.agreement == 0.0 and far.keep_cheap_judge is False
    assert "| within 1 |" in far.to_markdown()


def test_scores_outside_range_fail_validation():
    with pytest.raises(ValueError):
        JudgeScores.model_validate({"criteria": [{"name": "no_noise", "score": 6, "reason": "x"}]})
