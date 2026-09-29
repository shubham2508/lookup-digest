from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from digest.config import load_models
from digest.llm import LLM, CostLog, LLMOutputInvalid, LLMResult, LLMRoleUnconfigured, LLMSessionRole


class Out(BaseModel):
    a: int
    b: str


class FakeClient:
    """Stands in for openai.OpenAI: client.chat.completions.create(**kw)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        content = self.responses.pop(0)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.000123)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


MSGS = [{"role": "system", "content": "x"}]


def make(tmp_path, responses):
    log = CostLog(tmp_path / "cost.jsonl")
    llm = LLM(load_models(), cache_dir=tmp_path / "cache", cost_log=log, client=FakeClient(responses))
    return llm, log


def test_call_then_cache_hit(tmp_path):
    llm, log = make(tmp_path, ['{"a": 1, "b": "x"}'])
    r1 = llm.complete("compose", "p@v1", MSGS, Out)
    assert r1.output.a == 1 and not r1.cached and r1.retries == 0
    assert r1.usage.cost_usd == pytest.approx(0.000123) and r1.usage.cost_known
    r2 = llm.complete("compose", "p@v1", MSGS, Out)
    assert r2.cached and r2.output == r1.output and r2.usage.cost_usd == 0 and r2.cache_key == r1.cache_key
    t = log.totals()
    assert t["calls"] == 2 and t["cached"] == 1 and t["cost_usd"] == pytest.approx(0.000123)
    assert t["by_role"]["compose"]["prompt_tokens"] == 10
    assert (tmp_path / "cost.jsonl").read_text().count("\n") == 2
    assert len(llm.client.calls) == 1, "second call must not hit the API"


def test_prompt_version_or_model_changes_key(tmp_path):
    llm, _ = make(tmp_path, ['{"a": 1, "b": "x"}', '{"a": 2, "b": "y"}', '{"a": 3, "b": "z"}'])
    r1 = llm.complete("compose", "p@v1", MSGS, Out)
    r2 = llm.complete("compose", "p@v2", MSGS, Out)
    assert r1.cache_key != r2.cache_key and r2.output.a == 2
    r3 = llm.complete("thread_reader", "p@v1", MSGS, Out)  # same model, different reasoning effort → different key
    assert not r3.cached and r3.cache_key not in (r1.cache_key, r2.cache_key) and r3.output.a == 3


def test_retry_once_then_succeed(tmp_path):
    llm, _ = make(tmp_path, ['{"a": "not-int", "b": "x"}', '{"a": 3, "b": "x"}'])
    r = llm.complete("thread_reader", "p@v1", MSGS, Out)
    assert r.output.a == 3 and r.retries == 1
    second = llm.client.calls[1]
    assert second["messages"][-1]["role"] == "user" and "failed schema validation" in second["messages"][-1]["content"]
    assert second["messages"][-2]["role"] == "assistant"
    assert r.usage.prompt_tokens == 20 and r.usage.completion_tokens == 10


def test_invalid_twice_raises_and_is_not_cached(tmp_path):
    llm, log = make(tmp_path, ["nope", "still nope"])
    with pytest.raises(LLMOutputInvalid) as ei:
        llm.complete("thread_reader", "p@v1", MSGS, Out)
    assert ei.value.role == "thread_reader" and len(ei.value.raw) == 2 and len(ei.value.errors) == 2
    assert log.entries[-1]["invalid"] is True and log.entries[-1]["retries"] == 1
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_session_and_unconfigured_roles(tmp_path):
    llm, _ = make(tmp_path, [])
    with pytest.raises(LLMSessionRole):
        llm.complete("generator", "p@v1", MSGS, Out)
    m = load_models()
    m.roles["judge"] = m.roles["judge"].model_copy(update={"model": None, "family": None})
    with pytest.raises(LLMRoleUnconfigured):
        LLM(m, cache_dir=tmp_path / "cache", cost_log=CostLog(tmp_path / "c.jsonl"), client=FakeClient([])).complete("judge", "p@v1", MSGS, Out)


def test_request_shape(tmp_path):
    llm, _ = make(tmp_path, ['{"a": 1, "b": "x"}'])
    llm.complete("compose", "p@v1", MSGS, Out)
    kw = llm.client.calls[0]
    assert kw["model"] == "openai/gpt-6-luna"
    rf = kw["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True and rf["json_schema"]["name"] == "Out"
    assert rf["json_schema"]["schema"]["additionalProperties"] is False
    assert kw["seed"] == 7 and "temperature" not in kw
    assert kw["extra_body"]["reasoning"]["effort"] == "high" and kw["extra_body"]["usage"] == {"include": True}


def test_no_cache_flag(tmp_path):
    llm, _ = make(tmp_path, ['{"a": 1, "b": "x"}', '{"a": 1, "b": "x"}'])
    llm.complete("compose", "p@v1", MSGS, Out, cache=False)
    llm.complete("compose", "p@v1", MSGS, Out, cache=False)
    assert len(llm.client.calls) == 2


def test_complete_many_reports_per_item(tmp_path):
    llm, _ = make(tmp_path, ['{"a": 1, "b": "x"}', "bad", "bad"])
    res = llm.complete_many([
        {"role": "compose", "prompt_version": "p@v1", "messages": MSGS, "output_model": Out},
        {"role": "compose", "prompt_version": "p@v1", "messages": [{"role": "user", "content": "y"}], "output_model": Out},
    ], max_workers=1)
    assert isinstance(res[0], LLMResult) and res[0].output.a == 1
    assert isinstance(res[1], LLMOutputInvalid)
