import pytest
from pydantic import ValidationError

from digest.llm import strict_schema
from digest.schemas import (
    LLM_OUTPUT_MODELS,
    Ambiguity,
    Evidence,
    ProposedAction,
    TriageResult,
    validate_about_key,
)


def test_about_key_format():
    for ok in ("deal:series-a:cap-table", "offer:mei-tanaka", "renewal:veritas", "hiring-req:designer"):
        assert validate_about_key(ok) == ok
    for bad in ("Deal:x", "unknown:x", "deal", "deal:", "deal:x:y:z", "deal:Cap-Table", "deal:-x"):
        with pytest.raises(ValueError):
            validate_about_key(bad)


def test_evidence_word_limit():
    Evidence(source_id="msg:a", quote="will send it tonight")
    Evidence(source_id="msg:a", quote=" ".join(["w"] * 20))
    with pytest.raises(ValidationError):
        Evidence(source_id="msg:a", quote=" ".join(["w"] * 21))
    with pytest.raises(ValidationError):
        Evidence(source_id="msg:a", quote="   ")


def _triage() -> dict:
    return {
        "candidate_id": "c1", "include": True, "section": "urgent", "priority": "P0", "due_today": True,
        "confidence": "high", "why": "promised cap table Tuesday night; nothing sent; term sheet waits on it",
        "citations": [{"source_id": "msg:<20260922-2130.avery@tessera.io>", "quote": "will send it tonight"}],
        "ambiguity": None,
        "proposed_actions": [{"type": "task", "target": "Send cap table to Marcus", "brief": "due 11:00",
                              "assumptions": [], "watch_trigger": None, "read_start": None}],
    }


def test_triage_roundtrip_and_extra_forbidden():
    t = TriageResult.model_validate(_triage())
    assert t.proposed_actions[0].type == "task"
    assert TriageResult.model_validate_json(t.model_dump_json()) == t
    bad = _triage()
    bad["bonus"] = 1
    with pytest.raises(ValidationError):
        TriageResult.model_validate(bad)
    bad = _triage()
    bad["priority"] = "P4"
    with pytest.raises(ValidationError):
        TriageResult.model_validate(bad)


def test_ambiguity_and_action_shapes():
    a = Ambiguity(type="preference", question="renewal risk or billing?", options=["renewal risk", "billing"], default=2)
    assert a.default == 2
    p = ProposedAction(type="watch", target=None, brief="cadence 1.2 -> 4.8 days", assumptions=[],
                       watch_trigger="gap passes 7 days", read_start=None)
    assert p.watch_trigger


def _walk(node, path="", in_properties=False):
    if isinstance(node, dict):
        if not in_properties and node.get("type") == "object":
            assert "properties" in node, f"{path}: free-form object (dict) is not allowed in an LLM output model"
            assert node.get("additionalProperties") is False, f"{path}: additionalProperties must be false"
            assert set(node.get("required", [])) == set(node["properties"]), f"{path}: all properties must be required"
        if not in_properties:   # keys of a `properties` map are field names (Ambiguity.default), not keywords
            for k in ("format", "pattern", "minLength", "maxLength", "default"):
                assert k not in node, f"{path}: keyword {k} is not allowed in strict schema"
        for k, v in node.items():
            _walk(v, f"{path}/{k}", in_properties=(k == "properties"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]")


@pytest.mark.parametrize("name", sorted(LLM_OUTPUT_MODELS))
def test_llm_output_models_have_strict_schemas(name):
    schema = strict_schema(LLM_OUTPUT_MODELS[name])
    assert schema["type"] == "object"
    _walk(schema, name)
