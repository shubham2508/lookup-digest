"""LLM judge (specs/prompts.md E1): two fixed rubrics, reported, never gated.

- `draft`:  factual_consistency · tone_for_recipient · assumptions_flagged, per materialized draft.
- `digest`: answers_three_questions · no_noise · honest_about_gaps, per run day.

The judge of record is the `judge` role; until Shubham picks it, `LLMRoleUnconfigured` makes the report say
"judge: skipped (no model configured)". `calibrate()` scores the same items with `judge_reference` (Fable, one
round, ≈ $1) and the candidate judge, and reports agreement within 1 point (≥ 80% keeps the cheap judge).
`judge_reference` is never used in a real eval run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from digest.llm import LLM, LLMError, LLMOutputInvalid, LLMRoleUnconfigured, LLMSessionRole
from digest.prompts import load_prompt
from eval.scorer.artifacts import RunView

RUBRICS: dict[str, tuple[str, ...]] = {
    "draft": ("factual_consistency", "tone_for_recipient", "assumptions_flagged"),
    "digest": ("answers_three_questions", "no_noise", "honest_about_gaps"),
}
CriterionName = Literal["factual_consistency", "tone_for_recipient", "assumptions_flagged",
                        "answers_three_questions", "no_noise", "honest_about_gaps"]
AGREEMENT_WITHIN = 1
AGREEMENT_TARGET = 0.80


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CriterionName
    score: int = Field(description="1 to 5")
    reason: str = Field(description="one line, at most 25 words")

    @field_validator("score")
    @classmethod
    def _range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("score must be 1..5")
        return v


class JudgeScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteria: list[Criterion]


@dataclass
class JudgeItem:
    kind: str  # draft | digest
    id: str
    material: str


@dataclass
class JudgeResult:
    item_id: str
    kind: str
    role: str
    model: str | None = None
    scores: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    cost_usd: float = 0.0


@dataclass
class JudgeRun:
    role: str
    status: str  # ok | skipped
    note: str = ""
    results: list[JudgeResult] = field(default_factory=list)

    def means(self) -> dict[str, float]:
        out: dict[str, list[int]] = {}
        for r in self.results:
            for k, v in r.scores.items():
                out.setdefault(k, []).append(v)
        return {k: round(sum(v) / len(v), 2) for k, v in out.items()}


# ----------------------------------------------------------------------------- items
def draft_items(view: RunView, run_label: str = "") -> list[JudgeItem]:
    items = []
    for d in view.drafts():
        material = {
            "recipient": d.get("recipient_name") or d.get("target"),
            "recipient_category": d.get("recipient_category"),
            "brief": d.get("brief"),
            "evidence_quotes": [e.get("quote") for e in d.get("evidence", [])],
            "assumptions_listed": d.get("assumptions", []),
            "draft": d.get("draft"),
        }
        items.append(JudgeItem("draft", f"{run_label}{d.get('item_id')}:{d.get('type')}",
                               json.dumps(material, ensure_ascii=False, indent=2)))
    return items


def digest_item(view: RunView, run_label: str = "") -> JudgeItem | None:
    if not view.digest_text:
        return None
    return JudgeItem("digest", f"{run_label}digest", view.digest_text)


# ----------------------------------------------------------------------------- calls
def _check(scores: JudgeScores, kind: str) -> str | None:
    names = [c.name for c in scores.criteria]
    if sorted(names) != sorted(RUBRICS[kind]):
        return f"criteria {names} ≠ rubric {list(RUBRICS[kind])}"
    return None


def judge_items(items: list[JudgeItem], role: str = "judge", llm: LLM | None = None) -> JudgeRun:
    try:
        llm = llm or LLM()
        llm.role_config(role)
    except LLMRoleUnconfigured:
        return JudgeRun(role, "skipped", "no model configured")
    except (LLMSessionRole, LLMError, KeyError) as e:
        return JudgeRun(role, "skipped", str(e))
    prompt = load_prompt("judge")
    run = JudgeRun(role, "ok")
    calls = [{"role": role, "prompt_version": prompt.version_tag, "output_model": JudgeScores, "tag": f"judge:{it.id}",
              "messages": [{"role": "system", "content": prompt.render(rubric=it.kind, material=it.material)}]}
             for it in items]
    for it, res in zip(items, llm.complete_many(calls), strict=True):
        jr = JudgeResult(it.id, it.kind, role)
        if isinstance(res, LLMOutputInvalid):
            jr.error = f"invalid output after retry: {res.errors[-1][:200]}"
        elif isinstance(res, Exception):
            jr.error = f"{type(res).__name__}: {str(res)[:200]}"
            if isinstance(res, LLMError) and "not set" in str(res):
                return JudgeRun(role, "skipped", str(res))
        else:
            jr.model, jr.cost_usd = res.model, res.usage.cost_usd
            bad = _check(res.output, it.kind)
            if bad:
                jr.error = bad
            else:
                jr.scores = {c.name: c.score for c in res.output.criteria}
                jr.reasons = {c.name: c.reason for c in res.output.criteria}
        run.results.append(jr)
    return run


# ----------------------------------------------------------------------------- calibration (one-time)
@dataclass
class Calibration:
    reference: JudgeRun
    candidate: JudgeRun
    rows: list[tuple[str, str, int, int]] = field(default_factory=list)  # item, criterion, ref, cand

    @property
    def agreement(self) -> float | None:
        if not self.rows:
            return None
        return round(sum(1 for *_, r, c in self.rows if abs(r - c) <= AGREEMENT_WITHIN) / len(self.rows), 3)

    @property
    def keep_cheap_judge(self) -> bool | None:
        a = self.agreement
        return None if a is None else a >= AGREEMENT_TARGET

    def to_markdown(self) -> str:
        head = (f"Reference `{self.reference.role}` ({self.reference.status}) vs candidate `{self.candidate.role}` "
                f"({self.candidate.status}); {len(self.rows)} scored pairs.\n\n")
        if not self.rows:
            return head + f"No comparable scores. Reference: {self.reference.note or 'ok'}; candidate: {self.candidate.note or 'ok'}.\n"
        lines = ["| item | criterion | reference | candidate | within 1 |", "|---|---|---|---|---|"]
        lines += [f"| {i} | {k} | {r} | {c} | {'yes' if abs(r - c) <= AGREEMENT_WITHIN else '**no**'} |" for i, k, r, c in self.rows]
        verdict = "keep the cheap judge" if self.keep_cheap_judge else "agreement below target: consider the stronger fallback"
        return head + "\n".join(lines) + (f"\n\nAgreement within {AGREEMENT_WITHIN} point: **{self.agreement:.0%}** "
                                          f"(target {AGREEMENT_TARGET:.0%}) → {verdict}. Shubham picks the judge of record.\n")


def calibrate(items: list[JudgeItem], llm: LLM | None = None, reference_role: str = "judge_reference",
              candidate_role: str = "judge") -> Calibration:
    ref = judge_items(items, reference_role, llm)
    cand = judge_items(items, candidate_role, llm)
    cal = Calibration(ref, cand)
    by_id = {r.item_id: r for r in cand.results}
    for r in ref.results:
        c = by_id.get(r.item_id)
        if not c:
            continue
        for k, v in r.scores.items():
            if k in c.scores:
                cal.rows.append((r.item_id, k, v, c.scores[k]))
    return cal
