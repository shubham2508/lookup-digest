"""Compose (architecture §7, prompt P5): one call over the reduced items; validated in code (ids must exist, every
item placed or cut, question budget, P0 never silently dropped). A code fallback keeps the digest honest when the
model output is invalid twice."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import Settings
from ..llm import LLM, LLMError, LLMOutputInvalid
from ..prompts import Prompt, load_prompt
from ..runs import RunContext
from ..schemas import (
    Candidate,
    ComposeItem,
    ComposeResult,
    CustomizeOverrides,
    ProfileConfig,
    ProposedAction,
    ReduceItem,
    ReduceResult,
    Section,
    SectionBlock,
)

SECTION_ORDER: list[Section] = ["urgent", "decisions", "news", "pulse", "calendar_personal"]
SUMMARY_KEYS = ("summary", "what", "title", "headline", "ask", "commitment", "reason", "subject", "system", "candidate", "org",
                "task", "field", "proposal", "instructions", "meeting_desc", "email_says", "calendar_says", "values", "cadence",
                "days_overdue", "business_days_quiet", "hours_since_inbound", "overlap_minutes", "overlaps", "block", "start",
                "deadline", "due", "created", "count", "ratio", "baseline_median_days", "recent_median_days", "current_gap_days",
                "stage", "days_since_signal", "qualifier", "freshness_note", "attaches_to", "publication", "later_references")


@dataclass
class ComposeStats:
    cached: bool = False
    fallback: bool = False
    fixes: list[str] = field(default_factory=list)
    hidden_by_focus: list[str] = field(default_factory=list)
    outside_filter: list[str] = field(default_factory=list)


def item_view(it: ReduceItem, cands: dict[str, Candidate]) -> dict:
    facts = []
    for cid in it.candidate_ids:
        c = cands.get(cid)
        if c is None:
            continue
        facts.append({"type": c.type, **{k: v for k, v in c.facts.items() if k in SUMMARY_KEYS}})
    return {"id": it.id, "about": it.about, "priority": it.priority, "section": it.section, "due_today": it.due_today,
            "confidence": it.confidence, "why": it.why, "candidate_types": it.candidate_types, "facts": facts,
            "evidence_quotes": [e.quote for e in it.citations[:4]], "proposed_actions": [a.model_dump() for a in it.proposed_actions],
            "ambiguity": it.ambiguity.model_dump() if it.ambiguity else None, "entities": it.entities,
            "times_surfaced": it.times_surfaced, "freshness_cap": it.freshness_cap}


def title_for(it: ReduceItem, cands: dict[str, Candidate]) -> str:
    """Code-made 'what' when compose did not write one (fallback and also-pending lines)."""
    c = cands.get(it.candidate_ids[0]) if it.candidate_ids else None
    f = c.facts if c else {}
    t = c.type if c else it.candidate_types[0] if it.candidate_types else "item"
    name = (f.get("contact") or "").replace("-", " ").title()
    return {
        "commitment_overdue": f"Deliver: {f.get('what', it.about)} (overdue {f.get('days_overdue', '?')}d)",
        "commitment_due": f"Deliver today: {f.get('what', it.about)}",
        "commitment_not_in_tasks": f"Track the promise: {f.get('what', it.about)}",
        "reply_owed": f"Reply to {name or 'the sender'}: {f.get('subject', it.about)}",
        "quiet_thread": f"Re-engage {name or 'the thread'}: {f.get('summary', it.about)[:60]}",
        "approval_pending": f"Approve: {f.get('what', it.about)}",
        "calendar_conflict:deep_work": f"{f.get('title', 'Meeting')} overlaps your deep-work block",
        "calendar_conflict:family": f"Family: {f.get('title', it.about)} ({f.get('day', '')})",
        "calendar_conflict:double_book": "Two meetings overlap today",
        "task_due": f"Task: {f.get('title', it.about)}",
        "news_attachment": f"News: {f.get('headline', it.about)}",
        "hiring_stall": f"Hiring stall: {f.get('candidate', it.about)} at {f.get('stage', '?')}",
        "recruiter_pattern": f"Recruiter pattern: {f.get('org', it.about)} ({f.get('count', '?')} in 7 days)",
        "cadence_drop": f"Customer signal: {f.get('org', it.about)} reply cadence slowed",
        "contradiction": f"Sources disagree: {f.get('subject') or f.get('meeting_desc') or f.get('task') or it.about}",
        "profile_drift": f"Profile drift: {f.get('field', it.about)}",
        "suspicious_content": f"Suspicious instructions in: {f.get('subject', it.about)}",
        "obligation_cadence": f"Board update overdue under {f.get('cadence', '?')} cadence",
        "declined_meeting": f"Fallout from the declined {f.get('title', 'meeting')}",
        "stale_source": f"Source stale: {f.get('source', it.about)}",
    }.get(t, it.about)


def fallback_compose(reduced: ReduceResult, cands: dict[str, Candidate], k_items: int = 12) -> ComposeResult:
    items = [it for it in reduced.items if it.id not in reduced.overflow]
    keep = items[:k_items]
    cut = [it.id for it in items[k_items:]] + list(reduced.overflow)
    for it in items[k_items:]:
        if it.priority == "P0":
            keep.append(it)
            cut.remove(it.id)
    one = keep[0].id if keep else None
    sections = {s: [] for s in SECTION_ORDER}
    for it in keep:
        if it.id != one:
            sections[it.section].append(it.id)
    return ComposeResult(one_thing_id=one, sections=[SectionBlock(name=s, item_ids=ids) for s, ids in sections.items()],
                         items=[ComposeItem(id=it.id, what=title_for(it, cands), why=it.why, final_actions=list(it.proposed_actions)) for it in keep],
                         header_notes=["compose unavailable: items shown in triage order"], cut_ids=cut)


def validate_compose(result: ComposeResult, reduced: ReduceResult, question_budget: int, stats: ComposeStats) -> ComposeResult:
    known = {it.id: it for it in reduced.items}
    items: list[ComposeItem] = []
    seen_ids: set[str] = set()
    for ci in result.items:
        if ci.id in known and ci.id not in seen_ids:
            seen_ids.add(ci.id)
            acts, seen_a = [], set()
            for a in ci.final_actions:
                key = (a.type, (a.target or "").lower(), a.brief.strip().lower()[:40])
                if key not in seen_a:
                    seen_a.add(key)
                    acts.append(a)
            items.append(ci.model_copy(update={"final_actions": acts}))
    if len(items) != len(result.items):
        stats.fixes.append(f"dropped {len(result.items) - len(items)} unknown or duplicate item entries")
    ids_in_items = {ci.id for ci in items}
    sections: list[SectionBlock] = []
    placed: set[str] = set()
    for s in SECTION_ORDER:
        block = next((b for b in result.sections if b.name == s), None)
        ids: list[str] = []
        for i in (block.item_ids if block else []):
            if i in known and i not in placed and i not in ids:
                ids.append(i)
        placed.update(ids)
        sections.append(SectionBlock(name=s, item_ids=ids))
    one = result.one_thing_id if result.one_thing_id in known else None
    if result.one_thing_id and one is None:
        stats.fixes.append("one_thing_id unknown; cleared")
    if one:
        placed.add(one)
        for b in sections:
            if one in b.item_ids:
                b.item_ids.remove(one)
                stats.fixes.append("one thing removed from its section (no repeats)")
    cut = [i for i in result.cut_ids if i in known and i not in placed]
    # every reduced item must be placed, cut, or overflow; unplaced items → cut
    for it in reduced.items:
        if it.id not in placed and it.id not in cut:
            cut.append(it.id)
            stats.fixes.append(f"{it.id} unplaced → also pending")
    # a P0 never sits in the overflow list: it goes back to its own section (integration: Jordan's incident was buried)
    for iid in [i for i in cut if known[i].priority == "P0"]:
        cut.remove(iid)
        block = next(b for b in sections if b.name == known[iid].section)
        block.item_ids.append(iid)
        placed.add(iid)
        stats.fixes.append(f"{iid} is P0 → restored from also pending to {known[iid].section}")
    # items placed but without a compose item entry → synthesize from the reduced item
    for iid in placed:
        if iid not in ids_in_items:
            it = known[iid]
            items.append(ComposeItem(id=iid, what=it.why or it.about, why=it.why, final_actions=list(it.proposed_actions)))
            stats.fixes.append(f"{iid} had no item entry; synthesized")
    if one is None and placed:
        first = next(i for b in sections for i in b.item_ids)
        one = first
        for b in sections:
            if first in b.item_ids:
                b.item_ids.remove(first)
        stats.fixes.append("no one thing chosen; top item promoted")
    # question budget
    order = ([one] if one else []) + [i for b in sections for i in b.item_ids]
    budget = question_budget
    new_items: list[ComposeItem] = []
    by_id = {ci.id: ci for ci in items}
    for iid in order:
        ci = by_id[iid]
        acts: list[ProposedAction] = []
        for a in ci.final_actions[:2]:
            if a.type == "question":
                if budget > 0:
                    budget -= 1
                    acts.append(a)
                else:
                    acts.append(a.model_copy(update={"type": "read", "brief": f"(question budget used) {a.brief}"}))
                    stats.fixes.append(f"{iid}: question → read (budget)")
            else:
                acts.append(a)
        new_items.append(ci.model_copy(update={"final_actions": acts}))
    return ComposeResult(one_thing_id=one, sections=sections, items=new_items, header_notes=list(result.header_notes)[:4], cut_ids=cut)


def apply_focus(reduced: ReduceResult, cands: dict[str, Candidate], compute, overrides: CustomizeOverrides | None) -> tuple[list[str], list[str]]:
    """mode 'only': items outside the focus are hidden (cut); P0 items outside it still render as one-liners under
    'Also outside your filter' (locked invariant). → (hidden non-P0 ids, outside-filter P0 ids)."""
    if overrides is None or overrides.focus.mode != "only" or not (overrides.focus.categories or overrides.focus.entities):
        return [], []
    cats = {c.lower() for c in overrides.focus.categories}
    ents = {e.lower() for e in overrides.focus.entities}
    hidden: list[str] = []
    outside: list[str] = []
    for it in reduced.items:
        in_focus = False
        for e in it.entities:
            c = compute.directory.by_slug.get(e)
            if c and (c.relationship.category in cats or any(x in ents for x in [c.contact_id.lower(), *(n.lower() for n in c.names)])):
                in_focus = True
            if e.lower() in ents:
                in_focus = True
        if any(w in cats for w in ("family",)) and any(t.startswith("calendar_conflict:family") for t in it.candidate_types):
            in_focus = True
        if any(x in it.about.lower() for x in ents):
            in_focus = True
        if in_focus:
            continue
        (outside if it.priority == "P0" else hidden).append(it.id)
    return hidden, outside


def compose_digest(llm: LLM, reduced: ReduceResult, cands: dict[str, Candidate], profile: ProfileConfig, settings: Settings,
                   ctx: RunContext | None, *, freshness_line: str, rulings_applied: int, customize: CustomizeOverrides | None = None,
                   stage_notes: list[str] | None = None, prompt: Prompt | None = None, as_of: str = "",
                   compute=None) -> tuple[ComposeResult, ComposeStats]:
    prompt = prompt or load_prompt("compose")
    stats = ComposeStats()
    budget_words = (customize.length_words if customize and customize.length_words else settings.budget.length_words)
    hidden, outside = apply_focus(reduced, cands, compute, customize) if compute is not None else ([], [])
    items = [it for it in reduced.items if it.id not in reduced.overflow and it.id not in hidden and it.id not in outside]
    text = prompt.render(
        avery_name=profile.person, as_of=as_of, freshness=freshness_line, rulings_applied=rulings_applied,
        length_budget=budget_words, question_budget=settings.budget.question_budget,
        digest_prefs=json.dumps(profile.digest_prefs, ensure_ascii=False),
        customize=json.dumps(customize.model_dump(), ensure_ascii=False) if customize else "null",
        stage_notes=json.dumps(stage_notes or [], ensure_ascii=False),
        items=json.dumps([item_view(it, cands) for it in items], ensure_ascii=False, default=str),
    )
    try:
        r = llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": text}], ComposeResult, tag="compose")
        stats.cached = r.cached
        result = r.output
    except (LLMOutputInvalid, LLMError) as e:
        stats.fallback = True
        if ctx is not None:
            ctx.degrade("compose", "digest", type(e).__name__, detail=str(e)[:300])
        result = fallback_compose(reduced, cands)
    out = validate_compose(result, reduced, settings.budget.question_budget, stats)
    if hidden or outside:
        placed = {out.one_thing_id} | {i for b in out.sections for i in b.item_ids}
        for iid in hidden + outside:
            if iid in placed:
                if iid == out.one_thing_id:
                    out.one_thing_id = None
                for b in out.sections:
                    if iid in b.item_ids:
                        b.item_ids.remove(iid)
                stats.fixes.append(f"{iid} removed by focus filter")
        out.cut_ids = [i for i in out.cut_ids if i not in hidden] + [i for i in outside if i not in out.cut_ids]
        stats.hidden_by_focus = list(hidden)
        stats.outside_filter = list(outside)
    return out, stats


__all__ = ["SECTION_ORDER", "ComposeStats", "apply_focus", "compose_digest", "fallback_compose", "item_view", "title_for", "validate_compose"]
