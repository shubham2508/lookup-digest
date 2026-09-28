"""Materializer (architecture §7, §9.3; prompt P6): LLM for reply / forward_delegate / decide, templates for the rest.
Drafts are code-checked (≤3 sentences, banned phrases) with one corrective retry, then dropped and logged."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..compute import ComputeResult
from ..config import Settings
from ..llm import LLM, LLMError, LLMOutputInvalid
from ..prompts import Prompt, load_prompt
from ..runs import RunContext
from ..schemas import (
    Candidate,
    ComposeResult,
    Contact,
    CustomizeOverrides,
    DecideOutput,
    DraftOutput,
    Evidence,
    MaterializedAction,
    ProfileConfig,
    ProposedAction,
    ReduceItem,
)

SECTION_ORDER = ["urgent", "decisions", "news", "pulse", "calendar_personal"]
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class MaterializeStats:
    actions: int = 0
    llm_calls: int = 0
    cached: int = 0
    draft_retries: int = 0
    drafts_dropped: int = 0
    fixes: list[str] = field(default_factory=list)


def draft_violations(text: str, banned: list[str], max_sentences: int) -> list[str]:
    body = text.strip()
    lines = [ln for ln in body.split("\n") if ln.strip()]
    if lines and lines[-1].strip().lower().rstrip(".,!") in ("avery", "- avery", "— avery", "thanks, avery", "thanks,\navery"):
        lines = lines[:-1]
    core = " ".join(lines)
    sentences = [s for s in _SENT_SPLIT.split(core) if s.strip()]
    out = []
    if len(sentences) > max_sentences:
        out.append(f"{len(sentences)} sentences (max {max_sentences})")
    low = body.lower()
    for b in banned:
        if b.lower() in low:
            out.append(f"banned phrase: {b}")
    if "!!" in body or body.count("!") > 1:
        out.append("effusive punctuation")
    return out


def _recipient_card(c: Contact | None, target: str | None) -> dict | None:
    if c is None:
        return {"target": target} if target else None
    return {"name": c.names[0] if c.names else target, "email": c.emails[0] if c.emails else target, "org": c.org, "title": c.title,
            "category": c.relationship.category, "subtype": c.relationship.subtype, "stage": c.relationship.stage, "rules": c.profile_rules}


def _name(c: Contact | None, target: str | None) -> str:
    if c and c.names:
        return c.names[0]
    if target and "@" in target:
        return target.split("@")[0].replace(".", " ").title()
    return target or "them"


def _first(name: str) -> str:
    return name.split(" ")[0] if name else name


def _due_text(brief: str) -> str:
    m = re.search(r"\b(\d{1,2}:\d{2}(?:\s?[ap]m)?|\d{1,2}\s?[ap]m|today|tomorrow|end of day|eod|this week|friday|monday|tuesday|wednesday|thursday)\b", brief, re.I)
    return m.group(1) if m else "today"


class Materializer:
    def __init__(self, llm: LLM, compute: ComputeResult, profile: ProfileConfig, settings: Settings, ctx: RunContext | None,
                 customize: CustomizeOverrides | None = None, prompt: Prompt | None = None):
        self.llm, self.compute, self.profile, self.settings, self.ctx = llm, compute, profile, settings, ctx
        self.customize = customize
        self.prompt = prompt or load_prompt("materializer")
        self.stats = MaterializeStats()
        self.question_n = 0
        self.effective = [f for f in compute.facts_for_prompt() if f["data_value"] is not None]

    # ------------------------------------------------------------------ LLM
    def _call(self, action: ProposedAction, recipient: dict | None, evidence: list[Evidence], out_model, tag: str, extra: str = ""):
        tone = list(self.profile.tone)
        if self.customize and self.customize.tone.formality != "default":
            tone.append(f"customize: formality = {self.customize.tone.formality}")
        text = self.prompt.render(
            avery_name=self.profile.person, action_type=action.type, brief=action.brief,
            recipient=json.dumps(recipient, ensure_ascii=False) if recipient else "null",
            assumptions=json.dumps(action.assumptions, ensure_ascii=False),
            evidence=json.dumps([e.model_dump() for e in evidence], ensure_ascii=False),
            effective_facts=json.dumps(self.effective, ensure_ascii=False, default=str),
            tone=json.dumps(tone, ensure_ascii=False),
            customize_instructions=json.dumps(self.customize.materializer_instructions) if self.customize and self.customize.materializer_instructions else "null",
        )
        msgs = [{"role": "system", "content": text}]
        if extra:
            msgs.append({"role": "user", "content": extra})
        self.stats.llm_calls += 1
        r = self.llm.complete(self.prompt.model_role, self.prompt.version_tag, msgs, out_model, tag=tag)
        self.stats.cached += 1 if r.cached else 0
        return r.output

    def _draft(self, item: ReduceItem, action: ProposedAction, contact: Contact | None) -> tuple[str | None, list[str]]:
        recipient = _recipient_card(contact, action.target)
        banned = self.settings.drafts.banned_phrases
        try:
            out: DraftOutput = self._call(action, recipient, item.citations, DraftOutput, f"draft:{item.id}:{action.type}")
            bad = draft_violations(out.text, banned, self.settings.drafts.max_sentences)
            if bad:
                self.stats.draft_retries += 1
                out = self._call(action, recipient, item.citations, DraftOutput, f"draft:{item.id}:{action.type}:retry",
                                 extra="Your draft broke these rules: " + "; ".join(bad) + ". Rewrite it: at most 3 sentences, no banned phrases, same facts. JSON only.")
                bad = draft_violations(out.text, banned, self.settings.drafts.max_sentences)
                if bad:
                    self.stats.drafts_dropped += 1
                    if self.ctx is not None:
                        self.ctx.degrade("materialize", item.id, "draft_dropped", violations=bad, action=action.type)
                    return None, list(action.assumptions) + [f"draft dropped: {'; '.join(bad)}"]
            return out.text.strip(), list(dict.fromkeys(action.assumptions + out.assumptions))
        except (LLMOutputInvalid, LLMError) as e:
            if self.ctx is not None:
                self.ctx.degrade("materialize", item.id, type(e).__name__, detail=str(e)[:200], action=action.type)
            return None, list(action.assumptions) + ["draft unavailable (model output invalid)"]

    def _decide(self, item: ReduceItem, action: ProposedAction) -> tuple[str, str | None, list[str]]:
        try:
            out: DecideOutput = self._call(action, None, item.citations, DecideOutput, f"decide:{item.id}")
            opts = " ".join(f"({i}) {o.label} — {o.consequence}" for i, o in enumerate(out.options, 1))
            rec = out.recommendation if 1 <= out.recommendation <= len(out.options) else 1
            text = f"↳ Decide: {opts} Recommended: ({rec}) {out.rationale}".strip()
            return text, (out.draft.strip() if out.draft else None), list(dict.fromkeys(action.assumptions + out.assumptions))
        except (LLMOutputInvalid, LLMError) as e:
            if self.ctx is not None:
                self.ctx.degrade("materialize", item.id, type(e).__name__, detail=str(e)[:200], action="decide")
            return f"↳ Decide: {action.brief}", None, list(action.assumptions) + ["options unavailable (model output invalid)"]

    # ------------------------------------------------------------------ one action
    def render_action(self, item: ReduceItem, action: ProposedAction, cands: dict[str, Candidate]) -> MaterializedAction:
        contact = self.compute.directory.lookup(action.target if action.target and "@" in action.target else None,
                                               action.target if action.target and "@" not in action.target else None)
        name = _name(contact, action.target)
        ma = MaterializedAction(item_id=item.id, type=action.type, target=action.target, recipient_name=name if contact else None,
                                recipient_category=contact.relationship.category if contact else None, brief=action.brief,
                                brief_assumptions=list(action.assumptions), evidence=list(item.citations[:3]))
        t = action.type
        if t == "reply":
            draft, assumptions = self._draft(item, action, contact)
            ma.llm = draft is not None
            ma.draft, ma.assumptions = draft, assumptions
            ma.text = f"↳ Draft to {_first(name)}:" if draft else f"↳ Reply to {_first(name)}: {action.brief} No draft (unavailable)."
        elif t == "forward_delegate":
            draft, assumptions = self._draft(item, action, contact)
            ma.llm = draft is not None
            ma.draft, ma.assumptions = draft, assumptions
            ma.text = f"↳ Forward to {_first(name)} with:" if draft else f"↳ Forward to {_first(name)}: {action.brief}"
        elif t == "decide":
            ma.text, ma.draft, ma.assumptions = self._decide(item, action)
            ma.llm = True
        elif t == "task":
            title = action.target or action.brief
            ma.text = f"☐ {title} — due {_due_text(action.brief)}"
        elif t == "calendar_response":
            b = action.brief.strip().rstrip(".")
            b = re.sub(r"^(propose|proposal)\s*:?\s*", "", b, flags=re.I)
            ma.text = f"↳ Propose: {b}."
        elif t == "approve":
            system = action.target or next((cands[c].facts.get("system") for c in item.candidate_ids if c in cands and cands[c].facts.get("system")), None) or "the app"
            ma.text = f"↳ Approve in {system} (~1 min)."
            if action.brief and action.brief.lower() != system.lower():
                ma.text += f" {action.brief.rstrip('.')}."
        elif t == "question":
            self.question_n += 1
            n = self.question_n
            amb = item.ambiguity
            if amb and amb.options:
                opts = " ".join(f"({i}) {o}" for i, o in enumerate(amb.options, 1))
                d = amb.default if 1 <= amb.default <= len(amb.options) else 1
                ma.text = f"Q{n} · {amb.question} {opts}. Default if unanswered: {d} → digest answer Q{n} {d}"
            else:
                ma.text = f"Q{n} · {action.brief} (1) yes (2) no. Default if unanswered: 1 → digest answer Q{n} 1"
        elif t == "read":
            subject = next((cands[c].facts.get("subject") for c in item.candidate_ids if c in cands and cands[c].facts.get("subject")), None)
            start = action.read_start or "the latest message"
            ma.text = f"↳ Open {subject or 'the thread'}; start at {start}."
        elif t == "message_person":
            never = bool(contact and "never_draft" in contact.profile_rules)
            topic = re.sub(r"\s*No draft\s*\([^)]*\)\.?\s*$", "", action.brief.strip()).rstrip(".")
            topic = re.sub(r"\s*\b(do not|don't|never)\s+draft\b[^.]*\.?\s*$", "", topic, flags=re.I).rstrip(".")
            topic = topic[:1].lower() + topic[1:] if topic[:1].isupper() and not topic[:2].isupper() else topic
            ma.text = f"↳ Message {_first(name)} about {topic}. No draft ({_first(name) if never else 'needs your words'})."
        elif t == "watch":
            trig = action.watch_trigger or "the signal changes"
            ma.text = f"Watching: {action.brief.rstrip('.')}. Flags again if {trig.rstrip('.')}."
        elif t == "profile_update":
            ma.text = f"profile.md: {action.brief.rstrip('.')}."
        else:
            ma.text = f"↳ {action.brief}"
        if ma.assumptions and t not in ("reply", "forward_delegate", "decide"):
            pass
        self.stats.actions += 1
        return ma


def materialize(llm: LLM, compose: ComposeResult, reduced_items: dict[str, ReduceItem], cands: dict[str, Candidate],
                compute: ComputeResult, profile: ProfileConfig, settings: Settings, ctx: RunContext | None,
                customize: CustomizeOverrides | None = None, prompt: Prompt | None = None) -> tuple[list[MaterializedAction], MaterializeStats]:
    m = Materializer(llm, compute, profile, settings, ctx, customize, prompt)
    order = ([compose.one_thing_id] if compose.one_thing_id else []) + [i for s in compose.sections for i in s.item_ids]
    by_id = {ci.id: ci for ci in compose.items}
    out: list[MaterializedAction] = []
    for iid in order:
        ci = by_id.get(iid)
        it = reduced_items.get(iid)
        if ci is None or it is None:
            continue
        for a in ci.final_actions[:2]:
            out.append(m.render_action(it, a, cands))
    return out, m.stats


def suggested_tasks_md(actions: list[MaterializedAction], as_of_date: str) -> str:
    lines = []
    for a in actions:
        if a.type == "task":
            title = a.target or a.brief
            lines.append(f"- [ ] {title} (due: {as_of_date})")
    return "\n".join(lines) + ("\n" if lines else "")


__all__ = ["Materializer", "MaterializeStats", "draft_violations", "materialize", "suggested_tasks_md"]
