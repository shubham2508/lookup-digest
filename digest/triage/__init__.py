"""Triage stage (architecture §7, prompt P4): per candidate, packed 5–10 per call, parallel via complete_many.
Every result is validated (TriageBatch) and then checked in code: freshness caps, never_draft, recruiters,
citations copied from candidate evidence only, watch/read completeness, suspicious_content never P0."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from ..compute import ComputeResult
from ..config import Settings
from ..llm import LLM, LLMResult
from ..prompts import Prompt, load_prompt
from ..runs import RunContext
from ..schemas import Candidate, Contact, Evidence, ProfileConfig, ProposedAction, TriageBatch, TriageResult

PACK_SIZE = 6
RECRUITER_WORDS = ("recruit", "talent", "search", "staffing", "headhunt", "sourcer")


@dataclass
class TriageStats:
    candidates: int = 0
    packs: int = 0
    cached: int = 0
    invalid_packs: int = 0
    missing: list[str] = field(default_factory=list)
    fixes: list[dict] = field(default_factory=list)
    rulings_applied: int = 0


def ruling_matches(r: dict, c: Candidate) -> bool:
    """A learned rule applies only where it was learned: every scope field present must match exactly (topic AND
    person AND kind). The old any-one-field match let a Thanksgiving answer touch every 'reply owed' item."""
    scope = r.get("scope") or {}
    checks = []
    if scope.get("about"):  # the same topic or one of its sub-topics (key hierarchy, not similarity)
        checks.append(c.about == scope["about"] or c.about.startswith(scope["about"] + ":"))
    if scope.get("contact"):
        checks.append(scope["contact"] in c.entities)
    if scope.get("thread_kind"):
        checks.append(scope["thread_kind"] == c.type)
    return bool(checks) and all(checks)


def _contact_card(c: Contact) -> dict:
    b = c.behavior
    return {"contact_id": c.contact_id, "names": c.names, "org": c.org, "title": c.title,
            "category": c.relationship.category, "subtype": c.relationship.subtype, "stage": c.relationship.stage,
            "tier": c.tier, "rules": c.profile_rules,
            "behavior": {"avery_reply_rate": b.avery_reply_rate, "median_avery_reply_hours": b.median_avery_reply_hours,
                         "last_inbound": b.last_inbound.isoformat() if b.last_inbound else None,
                         "last_outbound": b.last_outbound.isoformat() if b.last_outbound else None,
                         "shared_meetings_30d": b.shared_meetings_30d},
            "drift": [{"field": d.field, "profile": d.profile_value, "data": d.data_value} for d in c.drift]}


def candidate_card(c: Candidate, compute: ComputeResult, rulings: list[dict]) -> dict:
    contacts = [compute.directory.by_slug[e] for e in c.entities if e in compute.directory.by_slug]
    return {
        "candidate_id": c.candidate_id, "type": c.type, "about": c.about, "entities": c.entities,
        "facts": {k: v for k, v in c.facts.items() if k not in ("entity_keys", "extra_dependencies")},
        "evidence": [e.model_dump() for e in c.evidence],
        "context": [{"source_id": s, "summary": compute.context.summary_of(s)} for s in c.context_refs],
        "contacts": [_contact_card(x) for x in contacts],
        "freshness_cap": c.freshness_cap, "times_surfaced": c.times_surfaced,
        "rulings": [r for r in rulings if ruling_matches(r, c)],
    }


def _pack_text(cards: list[dict], compute: ComputeResult) -> str:
    drift = [f for f in compute.facts_for_prompt() if f["drift"]]
    return json.dumps({"effective_facts_drift": drift, "candidates": cards}, ensure_ascii=False, default=str)


def _find_contact(compute: ComputeResult, target: str | None) -> Contact | None:
    if not target:
        return None
    return compute.directory.lookup(target if "@" in target else None, target if "@" not in target else None)


def _p0_earned(c: Candidate, compute: ComputeResult) -> bool:
    """The rubric's P0 is 'action today AND (family, capital during the raise, co-founder, or an escalation)'. Who is
    family / capital-during-the-raise / co-founder comes from the profile as contact tiers (P0 there: Sam, Priya,
    Marcus, Ben, and colleagues who inherit their firm's tier), so code checks the tier, not a name. Content can still
    earn P0: an escalation or incident, or a family calendar conflict."""
    if c.type == "calendar_conflict:family" or c.facts.get("escalation") or c.about.startswith("incident:"):
        return True
    for e in c.entities:
        ct = compute.directory.by_slug.get(e) if e else None
        if ct is not None and ct.tier == "P0":
            return True
    return False


def enforce(r: TriageResult, c: Candidate, compute: ComputeResult, stats: TriageStats, ctx: RunContext | None) -> TriageResult:
    fixes: list[str] = []
    upd: dict = {}
    if c.freshness_cap != "none" and r.confidence == "high":
        upd["confidence"] = "medium"
        fixes.append("confidence capped (freshness)")
    if c.type == "suspicious_content" and r.priority == "P0":
        upd["priority"] = "P2"
        fixes.append("suspicious_content demoted from P0")
    elif r.priority == "P0" and not _p0_earned(c, compute):
        upd["priority"] = "P1"
        fixes.append("P0 → P1: no P0 contact in the profile and no escalation content")
    # citations: only verbatim candidate evidence
    allowed = {(e.source_id, e.quote) for e in c.evidence}
    quotes = {e.quote for e in c.evidence}
    cits: list[Evidence] = []
    for e in r.citations:
        if (e.source_id, e.quote) in allowed:
            cits.append(e)
        elif e.quote in quotes:
            src = next(x.source_id for x in c.evidence if x.quote == e.quote)
            cits.append(Evidence(source_id=src, quote=e.quote))
    if not cits:
        cits = list(c.evidence[:2])
        fixes.append("citations replaced with candidate evidence")
    if list(cits) != list(r.citations):
        upd["citations"] = cits
    # actions
    acts: list[ProposedAction] = []
    for a in r.proposed_actions[:2]:
        contact = _find_contact(compute, a.target)
        rules = contact.profile_rules if contact else []
        cat, sub = (contact.relationship.category, contact.relationship.subtype or "") if contact else ("", "")
        if a.type in ("reply", "forward_delegate") and "never_draft" in rules:
            acts.append(a.model_copy(update={"type": "message_person"}))
            fixes.append(f"{a.type}→message_person (never_draft)")
            continue
        if a.type in ("reply", "forward_delegate") and cat == "cold_inbound" and any(w in sub.lower() for w in RECRUITER_WORDS):
            fixes.append(f"{a.type} to recruiter dropped")
            continue
        if a.type == "watch" and not a.watch_trigger:
            a = a.model_copy(update={"watch_trigger": "a new inbound message on this thread or a deadline appears"})
            fixes.append("watch_trigger filled")
        if a.type == "read" and not a.read_start:
            tid = c.facts.get("thread_id")
            if tid:
                a = a.model_copy(update={"read_start": tid})
                fixes.append("read_start filled with the thread id")
        acts.append(a)
    if acts != list(r.proposed_actions):
        upd["proposed_actions"] = acts
    if fixes:
        stats.fixes.append({"candidate_id": c.candidate_id, "fixes": fixes})
        if ctx is not None:
            ctx.degrade("triage", c.candidate_id, "code_fix", fixes=fixes)
    return r.model_copy(update=upd) if upd else r


def fallback_result(c: Candidate) -> TriageResult:
    """When a pack fails validation twice: include P0-shaped types conservatively so nothing important is lost."""
    section = {"calendar_conflict:deep_work": "calendar_personal", "calendar_conflict:family": "calendar_personal",
               "calendar_conflict:double_book": "calendar_personal", "declined_meeting": "calendar_personal",
               "approval_pending": "decisions", "news_attachment": "news", "hiring_stall": "pulse", "cadence_drop": "pulse",
               "recruiter_pattern": "pulse", "contradiction": "decisions"}.get(c.type, "urgent")
    prio = "P0" if c.type in ("commitment_overdue", "calendar_conflict:family") else "P2"
    return TriageResult(candidate_id=c.candidate_id, include=c.type not in ("stale_source",), section=section, priority=prio,
                        due_today=c.type in ("commitment_overdue", "commitment_due", "task_due"), confidence="low",
                        why=f"triage unavailable for this item ({c.type}); shown from computed facts", citations=list(c.evidence[:2]),
                        ambiguity=None, proposed_actions=[ProposedAction(type="read", target=None, brief="open the source and decide",
                                                                          assumptions=["triage model output was invalid"], watch_trigger=None,
                                                                          read_start=c.facts.get("thread_id"))])


def triage_candidates(llm: LLM, cands: list[Candidate], compute: ComputeResult, profile: ProfileConfig, settings: Settings,
                      ctx: RunContext | None = None, rulings: list[dict] | None = None, prompt: Prompt | None = None,
                      pack_size: int = PACK_SIZE, as_of: datetime | None = None) -> tuple[list[TriageResult], TriageStats]:
    prompt = prompt or load_prompt("triage")
    rulings = rulings or []
    stats = TriageStats(candidates=len(cands))
    cards = [candidate_card(c, compute, rulings) for c in cands]
    stats.rulings_applied = len({r.get("id") for card in cards for r in card["rulings"]})
    packs = [list(zip(cands[i:i + pack_size], cards[i:i + pack_size], strict=True)) for i in range(0, len(cands), pack_size)]
    calls = []
    for pack in packs:
        text = prompt.render(avery_name=profile.person, as_of=(as_of or compute.context.as_of).isoformat(),
                             judgment_rules=json.dumps(profile.judgment_rules, ensure_ascii=False),
                             rulings=json.dumps(rulings, ensure_ascii=False, default=str),
                             candidates=_pack_text([card for _, card in pack], compute))
        calls.append({"role": prompt.model_role, "prompt_version": prompt.version_tag, "messages": [{"role": "system", "content": text}],
                      "output_model": TriageBatch, "tag": "triage:" + ",".join(c.candidate_id for c, _ in pack)})
    stats.packs = len(calls)
    outcomes = llm.complete_many(calls, max_workers=settings.llm.max_workers) if calls else []
    by_id = {c.candidate_id: c for c in cands}
    results: list[TriageResult] = []

    def one_call(pack) -> dict[str, TriageResult] | Exception:
        text = prompt.render(avery_name=profile.person, as_of=(as_of or compute.context.as_of).isoformat(),
                             judgment_rules=json.dumps(profile.judgment_rules, ensure_ascii=False),
                             rulings=json.dumps(rulings, ensure_ascii=False, default=str),
                             candidates=_pack_text([card for _, card in pack], compute))
        try:
            r = llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": text}], TriageBatch,
                             tag="triage:" + ",".join(c.candidate_id for c, _ in pack))
        except Exception as e:  # noqa: BLE001 - reported per candidate below
            return e
        stats.cached += 1 if r.cached else 0
        return {x.candidate_id: x for x in r.output.results if x.candidate_id in by_id}

    for pack, res in zip(packs, outcomes, strict=True):
        ids = [c.candidate_id for c, _ in pack]
        if isinstance(res, LLMResult):
            stats.cached += 1 if res.cached else 0
            got = {r.candidate_id: r for r in res.output.results if r.candidate_id in by_id}
        else:
            stats.invalid_packs += 1
            if ctx is not None:
                ctx.degrade("triage", ",".join(ids), type(res).__name__, detail=str(res)[:300], recovery="retrying each candidate alone")
            got = {}
        for cid in ids:
            if cid in got:
                results.append(enforce(got[cid], by_id[cid], compute, stats, ctx))
                continue
            single = one_call([next(p for p in pack if p[0].candidate_id == cid)])   # the pack lost it: ask for it alone
            if isinstance(single, dict) and cid in single:
                stats.packs += 1
                results.append(enforce(single[cid], by_id[cid], compute, stats, ctx))
                continue
            stats.missing.append(cid)
            if ctx is not None:
                ctx.degrade("triage", cid, "fallback_result", detail=str(single)[:200] if isinstance(single, Exception) else "missing from output")
            results.append(enforce(fallback_result(by_id[cid]), by_id[cid], compute, stats, ctx))
    return results, stats


__all__ = ["PACK_SIZE", "TriageStats", "candidate_card", "enforce", "fallback_result", "ruling_matches", "triage_candidates"]
