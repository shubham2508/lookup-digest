import pytest

from digest.config import PIPELINE_ROLES, ModelsConfig, load_models, load_settings


def test_models_yaml_loads_and_pipeline_is_luna():
    m = load_models()
    for r in PIPELINE_ROLES:
        assert m.role(r).model == "openai/gpt-6-luna", r
    assert m.role("compose").reasoning_effort == "high"
    assert m.role("generator").is_session
    assert m.role("judge").model == "deepseek/deepseek-v4.1-flash" and m.role("judge").family == "deepseek", \
        "Shubham's pick (OPEN_QUESTIONS.md #1): a third family"


def test_family_rule():
    base = load_models().model_dump()
    for bad in ({"model": "openai/gpt-6-sol", "family": "openai"}, {"model": "anthropic/claude-sonnet-5", "family": "anthropic"}):
        base["roles"]["judge"] = bad
        with pytest.raises(ValueError, match="family rule"):
            ModelsConfig.model_validate(base)
    base["roles"]["judge"] = {"model": "google/gemini-3.8-flash", "family": "google"}
    assert ModelsConfig.model_validate(base).role("judge").family == "google"
    base["roles"]["judge"] = {"model": "x-ai/grok-4.7"}
    with pytest.raises(ValueError, match="no family"):
        ModelsConfig.model_validate(base)


def test_unknown_role():
    with pytest.raises(KeyError):
        load_models().role("oracle")


def test_settings_defaults():
    s = load_settings()
    assert s.timezone == "America/Los_Angeles"
    assert s.budget.length_words == 350 and s.budget.k_cap == 25 and s.budget.question_budget == 2
    assert s.thresholds_default.investor_quiet_business_days == 3
    assert s.thresholds_default.recruiter_pattern.count == 3
    assert "circling back" in s.drafts.banned_phrases
