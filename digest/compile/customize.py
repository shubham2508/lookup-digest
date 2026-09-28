"""Customize compiler (architecture §5.2, prompt P2): a per-run prompt → CustomizeOverrides. Layered config
defaults ← profile ← customize with locked invariants enforced in code, never only in the prompt."""
from __future__ import annotations

import re
from pathlib import Path

from ..llm import LLM, LLMError, LLMOutputInvalid
from ..prompts import Prompt, load_prompt
from ..runs import RunContext
from ..schemas import CustomizeOverrides, Focus, RejectedInstruction, Section, ToneOverride

DEFAULT_SECTIONS: list[Section] = ["urgent", "decisions", "news", "pulse", "calendar_personal"]
LOCKED_PATTERNS = [
    (re.compile(r"\b(skip|drop|remove|omit|no|without|hide)\b[^.]{0,40}\b(citation|source|reference)s?\b", re.I), "honesty rule: citations are locked"),
    (re.compile(r"\b(skip|drop|remove|omit|no|hide|ignore)\b[^.]{0,40}\b(stale|staleness|contradiction|freshness)\b", re.I), "honesty rule: staleness and contradiction flags are locked"),
    (re.compile(r"\b(draft|write|reply)\b[^.]{0,40}\b(sam)\b", re.I), "hard rule: never draft for never_draft contacts"),
    (re.compile(r"\b(hide|drop|skip|suppress)\b[^.]{0,40}\b(p0|family)\b", re.I), "hard rule: P0 items are never hidden"),
]


def default_overrides(not_understood: bool = False) -> CustomizeOverrides:
    return CustomizeOverrides(sections_order=list(DEFAULT_SECTIONS), sections_exclude=[], length_words=None,
                              focus=Focus(entities=[], categories=[], mode="boost"), include_newsletters=False,
                              calendar_full_schedule=False, tone=ToneOverride(formality="default"), horizon_days=0,
                              compose_instructions=None, materializer_instructions=None, rejected=[], not_understood=not_understood)


def enforce_invariants(o: CustomizeOverrides, text: str) -> CustomizeOverrides:
    """Code guarantees what the prompt only promises: locked instructions land in `rejected`, sections stay valid."""
    rejected = list(o.rejected)
    for pat, reason in LOCKED_PATTERNS:
        m = pat.search(text)
        if m and not any(reason == r.reason for r in rejected):
            rejected.append(RejectedInstruction(instruction=m.group(0).strip(), reason=reason))
    order = [s for s in o.sections_order if s in DEFAULT_SECTIONS]
    for s in DEFAULT_SECTIONS:
        if s not in order and s not in o.sections_exclude:
            order.append(s)
    order = list(dict.fromkeys(order)) or list(DEFAULT_SECTIONS)
    length = o.length_words if o.length_words and o.length_words >= 40 else (None if not o.length_words else 40)
    horizon = max(0, min(o.horizon_days, 14))
    instructions = o.compose_instructions
    if instructions and any(w in instructions.lower() for w in ("citation", "no source")):
        instructions = None
    return o.model_copy(update={"rejected": rejected, "sections_order": order, "length_words": length, "horizon_days": horizon,
                                "compose_instructions": instructions})


def header_notes(o: CustomizeOverrides, name: str) -> list[str]:
    notes: list[str] = []
    if o.not_understood:
        notes.append(f"customize file {name} not understood; default digest")
    for r in o.rejected:
        notes.append(f"customize: rejected \"{r.instruction[:60]}\" ({r.reason})")
    if not o.not_understood and not o.rejected:
        notes.append(f"customize: {name} applied")
    return notes


def compile_customize(llm: LLM, path: Path, ctx: RunContext | None = None, *, prompt: Prompt | None = None,
                      avery_name: str = "Avery") -> tuple[CustomizeOverrides, list[str]]:
    prompt = prompt or load_prompt("customize_compiler")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        if ctx is not None:
            ctx.degrade("compile_customize", str(path), "unreadable", detail=str(e)[:200])
        o = default_overrides(not_understood=True)
        return o, header_notes(o, path.name)
    if not text.strip():
        o = default_overrides(not_understood=True)
        return o, header_notes(o, path.name)
    try:
        r = llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": prompt.render(avery_name=avery_name, customize_md=text)}],
                         CustomizeOverrides, tag=f"customize:{path.stem}")
        o = r.output
    except (LLMOutputInvalid, LLMError) as e:
        if ctx is not None:
            ctx.degrade("compile_customize", str(path), type(e).__name__, detail=str(e)[:200])
        o = default_overrides(not_understood=True)
    o = enforce_invariants(o, text)
    return o, header_notes(o, path.name)


__all__ = ["DEFAULT_SECTIONS", "compile_customize", "default_overrides", "enforce_invariants", "header_notes"]
