"""Compute stage.

BRIDGE on branch v2-b-spine (Track B): Track A owns this file and replaces it with the v2 orchestration (spine → read →
sweeps → nets → reconcile → merge). Until then `compute_world` keeps the v1 pipeline running on B's branch over B's v2
functions: the contact spine, and the safety nets mapped to Candidates. At the merge, A's version of this file wins.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import Settings
from ..findings import to_candidate
from ..normalize import NormalizedWorld
from ..schemas import AboutMerge, Candidate, Contact, Extraction, ProfileConfig
from .candidates import ComputeInputs, safety_nets
from .contacts import ContactDirectory, build_contacts
from .context import ContextIndex, apply_context
from .facts import EffectiveFact, collect_claims, effective_facts
from .merge import thread_of


@dataclass
class ComputeResult:
    contacts: list[Contact]
    directory: ContactDirectory
    facts: list[EffectiveFact]
    candidates: list[Candidate]
    about_merges: list[AboutMerge]
    about_map: dict[str, str]
    context: ContextIndex
    stats: dict = field(default_factory=dict)
    links: list = field(default_factory=list)  # the linker's decisions with reasons (written to links.jsonl)

    def facts_for_prompt(self) -> list[dict]:
        return [{"subject": f.subject, "effective": f.effective, "profile_value": f.profile_value, "data_value": f.data_value,
                 "drift": f.drift, "evidence": [e.model_dump(mode="json") for e in f.evidence]} for f in self.facts]


def compute_world(world: NormalizedWorld, extractions: list[Extraction], profile: ProfileConfig, settings: Settings,
                  as_of: datetime, llm=None, ctx=None, decider=None) -> ComputeResult:
    from .linker import Linker

    linker = Linker(llm, ctx, decider=decider, jev_min_p=settings.llm.jev_min_probability)
    directory = build_contacts(world, profile, linker, llm, ctx, settings.thresholds_default.behavior_window_days)
    note_dates = {f"note:{n.path}": n.header_date for n in world.notes}
    facts = effective_facts(profile, collect_claims(extractions, note_dates))
    ci = ComputeInputs(world, profile, settings, as_of, directory, linker=linker)
    cands = [to_candidate(f, "", thread_id=thread_of(f, ci.msg_thread)) for f in safety_nets(ci) if f.needs_avery != "no" or f.kind == "stale_source"]
    idx = ContextIndex(world, extractions, as_of, settings.context.window_days, settings.context.max_items)
    apply_context(cands, idx, world.freshness)
    cands.sort(key=lambda c: (c.type, c.about, c.evidence[0].source_id if c.evidence else ""))
    for i, c in enumerate(cands, 1):
        c.candidate_id = f"c{i}"
    stats = {"contacts": len(directory.contacts), "candidates": len(cands), "by_type": {}, "about_merges": 0,
             "facts_drift": sum(1 for f in facts if f.drift), "links": len(linker.log)}
    for c in cands:
        stats["by_type"][c.type] = stats["by_type"].get(c.type, 0) + 1
    return ComputeResult(directory.contacts, directory, facts, cands, [], {}, idx, stats, links=linker.log)


__all__ = ["ComputeResult", "compute_world", "ContactDirectory", "EffectiveFact"]
