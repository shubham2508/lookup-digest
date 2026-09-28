"""Simulated Avery (specs/prompts.md E2, eval.md §7): answers question cards the way the answer key says.

Code first: each card in digest.md is tied to its item (compose/actions), and the item is matched to
`manifest.sim_avery` by about key, contact, or thread kind (candidate type). Only when nothing matches does the
`sim_avery` LLM role pick, from the same intended answers; if that role is unavailable, the card's default stands.
`simulate()` drives `digest run` → answers → `digest answer` over the last N run days, then scores the world.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from digest.llm import LLM, LLMError
from digest.paths import ROOT
from digest.prompts import load_prompt
from eval.manifest_schema import Manifest, SimAveryAnswer
from eval.scorer.artifacts import RenderedItem, RunView
from eval.scorer.common import contact_label, sender_emails
from eval.scorer.digest_md import QuestionCard
from eval.scorer.match import SourceIndex, about_match, norm_text, type_matches
from eval.scorer.runner import as_of_for, find_runs
from eval.scorer.simulation import rulings_path

SIM_TAG = "sim"  # OPEN_QUESTIONS #15: simulation runs live in runs/<world>/<as_of>_sim/; plain runs stay rulings-free


class SimAveryChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option: int
    matched_scope: str | None
    rationale: str


@dataclass
class Answer:
    question: str  # "Q1"
    option: int
    source: str  # code | llm | default
    scope: str | None
    about: str | None
    rationale: str | None = None

    def command(self, world: str) -> list[str]:
        return ["answer", self.question, str(self.option), "--world", world, "--tag", SIM_TAG]


def card_items(view: RunView) -> dict[int, RenderedItem | None]:
    """Q number → the rendered item that carries the card (by the Q<n> in its action text, else by render order)."""
    out: dict[int, RenderedItem | None] = {}
    q_items = [i for i in view.rendered if "question" in i.action_types]
    for it in q_items:
        for a in it.actions:
            m = re.search(r"\bQ(\d+)\b", str(a.get("text") or ""))
            if a.get("type") == "question" and m:
                out[int(m.group(1))] = it
    unassigned = [i for i in q_items if i not in out.values()]
    for card in view.digest.questions:
        if card.number not in out:
            out[card.number] = unassigned.pop(0) if unassigned else None
    return out


def _scope_matches(ans: SimAveryAnswer, item: RenderedItem, manifest: Manifest) -> bool:
    if ans.scope_about and about_match(item.about, ans.scope_about):
        return True
    if ans.scope_contact:
        c = contact_label(manifest, ans.scope_contact)
        keys = {norm_text(ans.scope_contact)} | ({norm_text(c.email), norm_text(c.name)} if c else set())
        people = {norm_text(e) for e in item.entities} | {norm_text(s) for sid in item.source_ids for s in sender_emails(manifest, sid)}
        people |= {norm_text(a.get("target") or "") for a in item.actions}
        if keys & people:
            return True
    return bool(ans.scope_thread_kind and any(type_matches(t, ans.scope_thread_kind) for t in item.candidate_types))


def _scope_label(ans: SimAveryAnswer) -> str:
    return ans.scope_about or ans.scope_contact or ans.scope_thread_kind or "?"


def answer_cards(view: RunView, manifest: Manifest, llm: LLM | None = None, use_llm: bool = True) -> list[Answer]:
    items = card_items(view)
    answers = []
    for card in view.digest.questions:
        item = items.get(card.number)
        n_opts = max(len(card.options), 1)
        hit = next((a for a in manifest.sim_avery if item and _scope_matches(a, item, manifest)), None)
        if hit and 1 <= hit.intended_option <= n_opts:
            answers.append(Answer(f"Q{card.number}", hit.intended_option, "code", _scope_label(hit),
                                  item.about if item else None, hit.rationale))
            continue
        choice = _llm_choice(card, item, manifest, llm) if use_llm and manifest.sim_avery else None
        if choice and 1 <= choice.option <= n_opts:
            answers.append(Answer(f"Q{card.number}", choice.option, "llm", choice.matched_scope,
                                  item.about if item else None, choice.rationale))
        else:
            answers.append(Answer(f"Q{card.number}", card.default or 1, "default", None, item.about if item else None,
                                  "no intended answer for this scope"))
    return answers


def _llm_choice(card: QuestionCard, item: RenderedItem | None, manifest: Manifest, llm: LLM | None) -> SimAveryChoice | None:
    try:
        llm = llm or LLM()
        prompt = load_prompt("sim_avery")
        card_txt = json.dumps({"question": card.question, "options": card.options, "default": card.default,
                               "item": item.what if item else card.item_text, "about": item.about if item else None},
                              ensure_ascii=False)
        intended = json.dumps([a.model_dump(exclude_none=True) for a in manifest.sim_avery], ensure_ascii=False)
        res = llm.complete("sim_avery", prompt.version_tag,
                           [{"role": "system", "content": prompt.render(card=card_txt, intended=intended)}],
                           SimAveryChoice, tag=f"sim_avery:Q{card.number}")
        return res.output
    except (LLMError, KeyError, OSError):
        return None


# ----------------------------------------------------------------------------- multi-day driver
DigestCmd = Callable[[list[str]], tuple[int, str]]


def run_digest_cli(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "cli.main", *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def set_aside_state(runs_root: Path, world: str | None = None) -> list[str]:
    """OPEN_QUESTIONS #13b `--fresh`: rename the world's rulings.yaml and store.sqlite* (paths from settings.store)
    to *.bak-<ts>. Reversible; never deletes."""
    from digest.config import load_settings
    from eval.scorer.simulation import state_path

    store = load_settings().store
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rulings = state_path(store.rulings_path_template, runs_root, world)
    db = state_path(store.path_template, runs_root, world)
    moved = []
    for p in [rulings, *sorted(db.parent.glob(db.name + "*"))]:
        if p.exists() and ".bak-" not in p.name:
            dst = p.with_name(f"{p.name}.bak-{ts}")
            p.rename(dst)
            moved.append(f"{p.name} → {dst.name}")
    return moved


def simulate(world: str, days: int, manifest: Manifest, runs_root: Path, log=print, *, fresh: bool = False,
             digest_cmd: DigestCmd = run_digest_cli, use_llm: bool = True) -> list[dict]:
    """Run the last `days` run days in order; after each, sim_avery answers the cards through `digest answer`.
    The transcript is saved to runs_root/simulation.json for `digest eval` (eval/scorer/simulation.py)."""
    index = SourceIndex(manifest)
    runs_root.mkdir(parents=True, exist_ok=True)
    transcript: list[dict] = []
    if fresh:
        for m in set_aside_state(runs_root, world):
            log(f"fresh: {m}")
    elif rulings_path(runs_root, world).exists():
        log("note: rulings.yaml already exists; earlier rulings will shape this simulation (use --fresh)")
    for day in manifest.meta.run_days[-days:]:
        as_of = as_of_for(manifest, day).strftime("%Y-%m-%dT%H:%M")
        code, output = digest_cmd(["run", "--world", world, "--as-of", as_of, "--tag", SIM_TAG])
        step: dict = {"day": day, "as_of": as_of, "run_exit": code, "answers": []}
        if code != 0:
            step["error"] = output[-300:]
            transcript.append(step)
            log(f"day {day}: digest run failed ({code}); stopping the simulation")
            break
        run_dir = find_runs(manifest, runs_root, SIM_TAG).get(day)
        if run_dir is None:
            step["error"] = "run wrote no artifacts"
            transcript.append(step)
            log(f"day {day}: no run directory under {runs_root}; stopping the simulation")
            break
        view = RunView(run_dir, index, ROOT, day=day)
        for ans in answer_cards(view, manifest, use_llm=use_llm):
            acode, _ = digest_cmd(ans.command(world))
            step["answers"].append({**ans.__dict__, "exit": acode})
            log(f"day {day}: {ans.question} → {ans.option} ({ans.source}, scope {ans.scope})")
        transcript.append(step)
    (runs_root / "simulation.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    return transcript
