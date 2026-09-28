"""Code floors on every TriageResult (MIGRATION_PLAN.md §2.2). v2 has no triage LLM call: readers, sweeps and safety
nets judge, and digest/findings.py maps each Finding to a TriageResult. What stays here is what code enforces no
matter what a model said: P0 only when earned (a P0-tier contact, family, or an incident/escalation), suspicious
content never P0, never_draft → message_person, no drafts to cold recruiters, citations only from the finding's own
verified evidence, a freshness cap on confidence, and complete watch/read actions. Plus `ruling_matches`."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..compute import ComputeResult
from ..runs import RunContext
from ..schemas import Candidate, Contact, Evidence, ProposedAction, TriageResult

RECRUITER_WORDS = ("recruit", "talent", "search", "staffing", "headhunt", "sourcer")
P0_ABOUT_KINDS = ("incident:", "family:")


@dataclass
class TriageStats:
    candidates: int = 0
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


def _find_contact(compute: ComputeResult, target: str | None) -> Contact | None:
    if not target:
        return None
    return compute.directory.lookup(target if "@" in target else None, target if "@" not in target else None)


def _suspicious(c: Candidate) -> bool:
    return c.type == "suspicious_content" or bool(c.facts.get("instructions"))


def _p0_earned(c: Candidate, compute: ComputeResult) -> bool:
    """The rubric's P0 is 'action today AND (family, capital during the raise, co-founder, or an escalation)'. Who is
    family / capital-during-the-raise / co-founder comes from the profile as contact tiers (P0 there: the partner,
    the co-founder, the lead investor, deal counsel, and colleagues who inherit their firm's tier), so code checks the
    tier or the family category, not a name. Content can still earn P0: an escalation or incident (a v1 escalation
    fact, or an incident: tag), or a family matter (a family calendar conflict, or a family: tag)."""
    if c.type == "calendar_conflict:family" or c.facts.get("escalation") or c.about.startswith(P0_ABOUT_KINDS):
        return True
    if any(str(t).startswith(P0_ABOUT_KINDS) for t in c.facts.get("about_tags") or []):
        return True
    for e in c.entities:
        ct = compute.directory.by_slug.get(e) if e else None
        if ct is not None and (ct.tier == "P0" or ct.relationship.category == "family"):
            return True
    return False


def enforce(r: TriageResult, c: Candidate, compute: ComputeResult, stats: TriageStats, ctx: RunContext | None) -> TriageResult:
    fixes: list[str] = []
    upd: dict = {}
    if c.freshness_cap != "none" and r.confidence == "high":
        upd["confidence"] = "medium"
        fixes.append("confidence capped (freshness)")
    if _suspicious(c) and r.priority == "P0":
        upd["priority"] = "P2"
        fixes.append("suspicious content demoted from P0")
    elif r.priority == "P0" and not _p0_earned(c, compute):
        upd["priority"] = "P1"
        fixes.append("P0 → P1: no P0 or family contact, no escalation/incident, no family matter")
    # citations: only the finding's own verified evidence
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


def enforce_all(results: list[TriageResult], cands: list[Candidate], compute: ComputeResult, rulings: list[dict],
                ctx: RunContext | None = None, rulings_applied: int | None = None) -> tuple[list[TriageResult], TriageStats]:
    """The floors on every result, in candidate order. `rulings_applied`: how many learned rules the judging stages
    were shown (readers); None counts the rulings whose scope matches a candidate exactly."""
    by_id = {c.candidate_id: c for c in cands}
    stats = TriageStats(candidates=len(cands))
    out = [enforce(r, by_id[r.candidate_id], compute, stats, ctx) for r in results if r.candidate_id in by_id]
    stats.rulings_applied = rulings_applied if rulings_applied is not None else len(
        {str(r.get("id")) for r in rulings for c in cands if ruling_matches(r, c)})
    return out, stats


__all__ = ["RECRUITER_WORDS", "TriageStats", "enforce", "enforce_all", "ruling_matches"]
