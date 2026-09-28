"""v2 Findings → the v1 downstream contract (specs/PIVOT_SPEC.md §4, MIGRATION_PLAN.md §0). Orchestrator-owned.

Readers, sweeps and safety nets emit `Finding`. This module turns each one into the `Candidate` and `TriageResult`
that reduce → compose → materialize → verify → render already consume, and checks citations the way v1 checked
extraction evidence: a quote that is not a substring of its source is dropped; a finding with no citation left is
dropped and logged. Nothing here judges; it reshapes and verifies."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from .schemas import Candidate, Evidence, Finding, TriageResult, validate_about_key
from .util import slugify

Log = Callable[[str, dict], None] | None


def about_key(tag: str, title: str) -> str:
    """A reader's light tag → a valid about key. Bare words get 'other:'; an unusable tag falls back to the title."""
    t = (tag or "").strip().lower().replace(" ", "-")
    if t and ":" not in t:
        t = f"other:{t}"
    try:
        return validate_about_key(t)
    except ValueError:
        return f"other:{slugify(title)[:40] or 'finding'}"


def check_citations(findings: Iterable[Finding], idx, log: Log = None) -> list[Finding]:
    """`idx` is an extract.evidence.SourceIndex over the sources this call saw (msg:<id> → text, event:, note:, task:).
    Invalid citations are dropped; a finding with none left is dropped. Suspicious-instruction quotes must be real too."""
    out: list[Finding] = []
    for f in findings:
        good = [e for e in f.citations if idx.contains(e.source_id, e.quote)]
        for e in f.citations:
            if e not in good and log:
                log("citation_invalid", {"finding": f.finding_id, "title": f.title, "source_id": e.source_id, "quote": e.quote})
        if not good:
            if log:
                log("finding_dropped_no_citation", {"finding": f.finding_id, "title": f.title, "origin": f.origin})
            continue
        sus = [e for e in f.suspicious_instructions if idx.contains(e.source_id, e.quote)]
        out.append(f.model_copy(update={
            "citations": [Evidence(source_id=idx.canonical(e.source_id), quote=e.quote) for e in good],
            "suspicious_instructions": [Evidence(source_id=idx.canonical(e.source_id), quote=e.quote) for e in sus],
        }))
    return out


def to_candidate(f: Finding, candidate_id: str, *, thread_id: str | None = None, context_refs: Iterable[str] = (),
                 rescued: bool = False, times_surfaced: int = 0) -> Candidate:
    """Safety nets keep their v1 rule name in `kind` (e.g. calendar_conflict:family), so `type` stays comparable with
    the answer key; readers' kinds are free text. Computed facts the v1 stages and the UI read live in `facts`."""
    facts: dict = {
        "finding_id": f.finding_id, "title": f.title, "kind": f.kind, "origin": f.origin, "needs_avery": f.needs_avery,
        "urgency": f.urgency, "stakes": f.stakes, "summary": f.why, "about_tags": list(f.about),
        "contradictions": list(f.contradictions), "rescued_by_safety_net": rescued,
    }
    if f.deadline is not None:
        facts["deadline"] = f.deadline.resolved.isoformat() if f.deadline.resolved else None
        facts["deadline_raw"] = f.deadline.raw
    if f.freshness_caveat:
        facts["freshness_note"] = f.freshness_caveat
    if thread_id:
        facts["thread_id"] = thread_id
    if f.suspicious_instructions:
        facts["instructions"] = [e.quote for e in f.suspicious_instructions]
    return Candidate(candidate_id=candidate_id, type=f.kind, about=about_key(f.about[0] if f.about else "", f.title),
                     entities=[e for e in f.entities if e], facts=facts, evidence=list(f.citations),
                     context_refs=list(context_refs), times_surfaced=times_surfaced)


def to_triage(f: Finding, candidate_id: str) -> TriageResult:
    """`unsure` surfaces only with its ambiguity card (a question for Avery), never as a guess."""
    include = f.needs_avery == "yes" or (f.needs_avery == "unsure" and f.ambiguity is not None)
    return TriageResult(candidate_id=candidate_id, include=include, section=f.section, priority=f.priority,
                        due_today=f.urgency == "today", confidence=f.confidence, why=f.why, citations=list(f.citations),
                        ambiguity=f.ambiguity, proposed_actions=list(f.proposed_actions)[:2])


def finding_row(f: Finding, candidate_id: str, *, thread_id: str | None, rescued: bool = False) -> dict:
    """One line of findings.jsonl: the Finding plus the code-set fields the scorer and UI join on."""
    return {**f.model_dump(mode="json"), "candidate_id": candidate_id, "thread_id": thread_id, "rescued_by_safety_net": rescued}


__all__ = ["about_key", "check_citations", "finding_row", "to_candidate", "to_triage"]
