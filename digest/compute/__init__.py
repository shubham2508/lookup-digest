"""Compute orchestration (specs/PIVOT_SPEC.md §2–§5, MIGRATION_PLAN.md §0). Code only; Track A owns this file,
Track B owns the modules it calls.

v2: `build_spine` (contacts + behavior + linker) → the pipeline runs the thread readers → `assemble` adds the sweeps
and the safety nets, reconciles and groups them (Track B), then maps every Finding onto the Candidate + TriageResult
shapes reduce → compose → materialize → verify → render already consume (digest/findings.py). A Track B function that
is missing is skipped (`_b_fn`), never faked.

Reconcile gets the thread map and the readers' own thread summaries (a waiting-on-Avery net on a thread the reader read
and found closed is covered by that reading, not rescued); only the nets in its rescue log are `rescued_by_safety_net`
(a stale-source fact is carried, never a rescue)."""
from __future__ import annotations

import dataclasses
import importlib
import importlib.util
from dataclasses import dataclass, field
from datetime import datetime

from ..config import Settings
from ..findings import finding_row, to_candidate, to_triage
from ..normalize import NormalizedWorld
from ..schemas import AboutMerge, Candidate, Contact, Finding, ProfileConfig, TriageResult
from . import contacts as contacts_mod
from .contacts import ContactDirectory, behavior_stats
from .context import ContextIndex, dependencies, freshness_cap


@dataclass
class ComputeResult:
    contacts: list[Contact]
    directory: ContactDirectory
    facts: list                     # effective facts (v1 EffectiveFact); v2: the notes+tasks sweep's changed facts (B)
    candidates: list[Candidate]
    about_merges: list[AboutMerge]
    about_map: dict[str, str]
    context: ContextIndex
    stats: dict = field(default_factory=dict)
    links: list = field(default_factory=list)  # the linker's decisions with reasons (written to links.jsonl)
    triage: list[TriageResult] = field(default_factory=list)   # v2: one per candidate, mapped from its Finding
    findings: list[dict] = field(default_factory=list)          # v2: findings.jsonl rows, every origin, "no" ones too

    def facts_for_prompt(self) -> list[dict]:
        return [{"subject": f.subject, "effective": f.effective, "profile_value": f.profile_value, "data_value": f.data_value,
                 "drift": f.drift, "evidence": [e.model_dump(mode="json") for e in f.evidence]} for f in self.facts]


@dataclass
class Spine:
    directory: ContactDirectory
    linker: object
    context: ContextIndex


def _optional(module: str):
    """A Track B module that may not exist yet; one that exists but fails to import raises (never skipped silently)."""
    name = f"{__name__}.{module}"
    if importlib.util.find_spec(name) is None:
        return None
    return importlib.import_module(name)


def _b_fn(name: str, *modules: str):
    """Track B's function `name` from the first of `modules` that has it, else None (not landed yet)."""
    for m in modules:
        mod = _optional(m)
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    return None


# ----------------------------------------------------------------------------- v2
def build_spine(world: NormalizedWorld, profile: ProfileConfig, settings: Settings, as_of: datetime, llm=None, ctx=None,
                decider=None) -> Spine:
    """Contacts (B's `build_contacts(world, profile, linker, llm, ctx)` once it lands; the v1 directory without
    extractions until then), behavior stats over the 30-day window, and the linker every later sameness call uses."""
    from .linker import Linker

    linker = Linker(llm, ctx, decider=decider, jev_min_p=settings.llm.jev_min_probability)
    directory = contacts_mod.build_contacts(world, profile, linker, llm, ctx)
    behavior_stats(directory, world, as_of, settings.thresholds_default.behavior_window_days)
    context = ContextIndex(world, [], as_of, settings.context.window_days, settings.context.max_items)
    return Spine(directory, linker, context)


def _compute_inputs(world, profile, settings, as_of, spine: Spine, findings: list[Finding]):
    """B's safety nets take a ComputeInputs; fill whichever of its fields exist from what v2 has."""
    from . import candidates as cand_mod

    have = {"world": world, "extractions": [], "profile": profile, "settings": settings, "as_of": as_of,
            "directory": spine.directory, "facts": [], "about_map": {}, "linker": spine.linker, "findings": findings}
    if hasattr(cand_mod, "resolve_thresholds"):
        have["thresholds"] = cand_mod.resolve_thresholds(profile, settings)
    kw = {f.name: have[f.name] for f in dataclasses.fields(cand_mod.ComputeInputs) if f.init and f.name in have}
    return cand_mod.ComputeInputs(**kw)


def _thread_of(f: Finding, msg_thread: dict[str, str]) -> str | None:
    for e in f.citations:
        if e.source_id in msg_thread:
            return msg_thread[e.source_id]
    return None


def _renumber(fs: list[Finding], prefix: str, taken: set[str]) -> list[Finding]:
    out = []
    for i, f in enumerate(fs, 1):
        fid = f"{prefix}{i}"
        while fid in taken:
            fid += "x"
        taken.add(fid)
        out.append(f.model_copy(update={"finding_id": fid}))
    return out


class _NullTimer:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def assemble(world: NormalizedWorld, spine: Spine, read, profile: ProfileConfig, settings: Settings, as_of: datetime,
             llm=None, ctx=None) -> ComputeResult:
    """Readers' findings (+ B's sweeps and safety nets when landed) → reconcile → group → Candidate + TriageResult.
    `read` is digest.read.ReadResult. `enforce` (the code floors) runs on the result in the pipeline."""
    msg_thread = {f"msg:{m.message_id}": t.thread_id for t in world.threads for m in t.messages}
    subject = {t.thread_id: t.messages[0].subject for t in world.threads if t.messages}
    taken: set[str] = set()
    readers = _renumber([rf.finding for rf in read.findings], "f", taken)
    thread_of = {f.finding_id: rf.thread_id for f, rf in zip(readers, read.findings, strict=True)}
    refs_of = {f.finding_id: rf.context_refs for f, rf in zip(readers, read.findings, strict=True)}
    findings: list[Finding] = list(readers)
    stats: dict = {"contacts": len(spine.directory.contacts), "reader_findings": len(readers), "sweep_findings": None,
                   "net_findings": None, "rescues": None, "about_merges": 0}

    def timed(stage: str):
        return ctx.timed(stage) if ctx is not None else _NullTimer()

    run_sweeps = _b_fn("run_sweeps", "sweeps")
    if run_sweeps is not None:
        with timed("sweep"):
            swept = _renumber(list(run_sweeps(world, spine.directory, list(findings), profile, settings, llm, ctx, as_of)), "s", taken)
        findings += swept
        stats["sweep_findings"] = len(swept)

    safety_nets = _b_fn("safety_nets", "candidates")
    rescued_ids: set[str] = set()
    if safety_nets is not None:
        with timed("nets"):
            nets = _renumber(list(safety_nets(_compute_inputs(world, profile, settings, as_of, spine, findings))), "n", taken)
            stats["net_findings"] = len(nets)
            reconcile = _b_fn("reconcile", "merge", "linker")
            if reconcile is not None:
                findings, rescues = reconcile(findings, nets, spine.linker, msg_thread=msg_thread,
                                              summaries=getattr(read, "summaries", {}))
                stats["rescues"] = len(rescues)
                if ctx is not None:
                    for r in rescues:
                        ctx.degrade("nets", str(r.get("finding_id") or r.get("title") or r.get("net")), "rescued_by_safety_net",
                                    **{k: v for k, v in r.items() if k not in ("stage", "item", "reason")})
            else:
                findings = findings + nets
            rescued_ids = ({str(r["finding_id"]) for r in rescues} if reconcile is not None
                           else {f.finding_id for f in findings if f.origin == "safety_net"})

    merges: list[AboutMerge] = []
    group_findings = _b_fn("group_findings", "merge", "linker")
    if group_findings is not None:
        with timed("merge"):
            merges = list(group_findings(findings, spine.linker))
    about_map = {m: g.canonical for g in merges for m in g.merged}
    stats["about_merges"] = len(merges)

    cands: list[Candidate] = []
    triage: list[TriageResult] = []
    rows: list[dict] = []
    for f in findings:
        tid = thread_of.get(f.finding_id) or _thread_of(f, msg_thread)
        rescued = f.finding_id in rescued_ids
        if f.needs_avery == "no":
            rows.append(finding_row(f, None, thread_id=tid, rescued=rescued))
            continue
        cid = f"c{len(cands) + 1}"
        c = to_candidate(f, cid, thread_id=tid, context_refs=refs_of.get(f.finding_id, []), rescued=rescued)
        c.about = about_map.get(c.about, about_map.get(f.about[0] if f.about else "", c.about))
        if tid and tid in subject:
            c.facts["subject"] = subject[tid]
        c.source_dependencies = dependencies(c)
        c.freshness_cap = freshness_cap(c.source_dependencies, world.freshness)
        if c.freshness_cap != "none" and "freshness_note" not in c.facts:
            stale = [k for k in c.source_dependencies if world.freshness.get(k) and world.freshness[k].state != "ok"]
            c.facts["freshness_note"] = f"{', '.join(stale)} {'stale' if c.freshness_cap == 'stale' else 'missing/unreadable'}: confidence capped at medium"
        cands.append(c)
        triage.append(to_triage(f, cid))
        rows.append(finding_row(f, cid, thread_id=tid, rescued=rescued))
    stats["candidates"] = len(cands)
    stats["by_origin"] = {}
    for f in findings:
        stats["by_origin"][f.origin] = stats["by_origin"].get(f.origin, 0) + 1
    stats["links"] = len(getattr(spine.linker, "log", []))
    return ComputeResult(spine.directory.contacts, spine.directory, [], cands, merges, about_map, spine.context, stats,
                         links=list(getattr(spine.linker, "log", [])), triage=triage, findings=rows)


__all__ = ["ComputeResult", "ContactDirectory", "Spine", "assemble", "build_spine"]
