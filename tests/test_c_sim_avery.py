"""sim_avery (E2): code matches cards to intended answers; LLM only as fallback; default when nothing applies."""
import json
from types import SimpleNamespace

from digest.config import load_models
from digest.llm import LLM
from digest.prompts import load_prompt
from eval.manifest_schema import SimAveryAnswer
from eval.scorer.artifacts import RunView
from eval.scorer.match import SourceIndex
from eval.sim_avery.sim import answer_cards, card_items, simulate
from tests.c_helpers import DAY, MINI_RUNS, ROOT, mini_manifest

RUN = MINI_RUNS / "2026-09-24T06-00"


def view(m):
    return RunView(RUN, SourceIndex(m), ROOT, day=DAY)


def test_card_is_tied_to_its_item():
    m = mini_manifest()
    items = card_items(view(m))
    assert list(items) == [1] and items[1].about == "rollout:halberd:oct-6"


def test_code_match_by_about_key():
    m = mini_manifest()
    [a] = answer_cards(view(m), m, use_llm=False)
    assert (a.question, a.option, a.source, a.scope) == ("Q1", 1, "code", "rollout:halberd:oct-6")
    assert a.command("dev") == ["answer", "Q1", "1", "--world", "dev"]


def test_code_match_by_contact_and_thread_kind():
    m = mini_manifest()
    m.sim_avery = [SimAveryAnswer(scope_contact="Renee Tan", intended_option=2)]
    assert answer_cards(view(m), m, use_llm=False)[0].option == 2
    m.sim_avery = [SimAveryAnswer(scope_thread_kind="reply_owed", intended_option=2)]
    assert answer_cards(view(m), m, use_llm=False)[0].source == "code"


def test_default_when_nothing_matches():
    m = mini_manifest()
    m.sim_avery = [SimAveryAnswer(scope_about="offer:someone-else", intended_option=2)]
    [a] = answer_cards(view(m), m, use_llm=False)
    assert (a.option, a.source) == (1, "default")


def test_llm_fallback(tmp_path):
    m = mini_manifest()
    m.sim_avery = [SimAveryAnswer(scope_about="rollout:northstar:plant-2", intended_option=2, rationale="check first")]

    def create(**body):
        out = {"option": 2, "matched_scope": "rollout:northstar:plant-2", "rationale": "same rollout"}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(out)))],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, cost=0.0, model_extra={}))

    llm = LLM(load_models(), cache_dir=tmp_path, client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    [a] = answer_cards(view(m), m, llm=llm)
    assert (a.option, a.source, a.scope) == (2, "llm", "rollout:northstar:plant-2")
    assert load_prompt("sim_avery").output_model == "SimAveryChoice"


def test_simulate_stops_cleanly_when_digest_run_fails(tmp_path):
    m = mini_manifest()
    logs = []
    t = simulate("no-such-world-xyz", 1, m, tmp_path, log=logs.append)
    assert len(t) == 1 and t[0]["run_exit"] != 0 and "stopping" in logs[-1]
