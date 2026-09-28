"""Compute orchestration (specs/PIVOT_SPEC.md §2–§5, MIGRATION_PLAN.md §0). Code only; Track A owns this file,
Track B owns the modules it calls.

v2: `build_spine` (contacts + behavior + linker) → the pipeline runs the thread readers → `assemble` adds the sweeps
and the safety nets, reconciles and groups them (Track B), then maps every Finding onto the Candidate + TriageResult
shapes reduce → compose → materialize → verify → render already consume (digest/findings.py). Until B's functions
land, the spine is the v1 directory built without extractions, and sweeps/nets/reconcile/merge are skipped.

`compute_world` is the v1 extraction-centric stage, kept only for tests/test_a_compute.py until Track B moves those
tests; its imports are lazy so B deleting aboutkeys.py or trimming candidates.py cannot break this module."""
from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import inspect
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


def _inherit_org_tiers(directory, owner_emails) -> None:
    """v1 path only (Track B moves this into contacts.py). DESIGN_LOG §9.6 / P0 cases 5 and 12: a colleague of a
    profile contact at the same outside org inherits that contact's tier during the raise. Never inside Avery's own
    company and never to automated senders. Rules such as never_draft do not propagate."""
    from ..util import domain_of, slugify

    own = {domain_of(e) for e in owner_emails}
    higher = lambda a, b: min(a, b, key=lambda x: int(x[1]))   # noqa: E731  P0 beats P1
    org_tier: dict[str, str] = {}
    for c in directory.contacts:
        if c.relationship.source != "profile" or not c.tier or c.relationship.category == "team":
            continue
        if any(domain_of(e) in own for e in c.emails):
            continue
        for k in ([slugify(c.org)] if c.org else []) + [domain_of(e) for e in c.emails]:
            org_tier[k] = higher(org_tier.get(k, "P9"), c.tier)
    for c in directory.contacts:
        if c.tier or c.relationship.source == "profile" or c.relationship.category in ("team", "automated"):
            continue
        if any(domain_of(e) in own for e in c.emails):
            continue
        keys = ([slugify(c.org)] if c.org else []) + [domain_of(e) for e in c.emails]
        for k in keys:
            if k in org_tier:
                c.tier = org_tier[k]
                break


# ----------------------------------------------------------------------------- v2
def build_spine(world: NormalizedWorld, profile: ProfileConfig, settings: Settings, as_of: datetime, llm=None, ctx=None,
                decider=None) -> Spine:
    """Contacts (B's `build_contacts(world, profile, linker, llm, ctx)` once it lands; the v1 directory without
    extractions until then), behavior stats over the 30-day window, and the linker every later sameness call uses."""
    from .linker import Linker

    linker = Linker(llm, ctx, decider=decider, jev_min_p=settings.llm.jev_min_probability)
    if "extractions" in inspect.signature(contacts_mod.build_contacts).parameters:
        directory = contacts_mod.build_contacts(world, [], profile, linker)
        _inherit_org_tiers(directory, world.owner_emails)
    else:
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
                findings, rescues = reconcile(findings, nets, spine.linker)
                stats["rescues"] = len(rescues)
                if ctx is not None:
                    for r in rescues:
                        ctx.degrade("nets", str(r.get("finding_id") or r.get("title") or r.get("net")), "rescued_by_safety_net",
                                    **{k: v for k, v in r.items() if k not in ("stage", "item", "reason")})
            else:
                findings = findings + nets
            rescued_ids = {f.finding_id for f in findings if f.origin == "safety_net"}

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


# ----------------------------------------------------------------------------- v1 (tests/test_a_compute.py only)
def _extraction_keys(extractions, slug_map: dict[str, str], msg_thread: dict[str, str]):
    """Every about key in the extractions, with the entities and evidence messages that carry it."""
    from .aboutkeys import AboutMerger, canonical_key

    merger = AboutMerger()
    for x in extractions:
        p = x.payload
        if p is None:
            continue
        ents: set[str] = set()
        for so in getattr(p, "sender_observations", []) or []:
            ents.add(so.email.lower())
            if so.name:
                ents.add(slug_map.get(so.name.lower(), so.name.lower()))
        for e in getattr(p, "entities", []) or []:
            ents.add(e.name.lower())
        msgs = {x.source_id}
        keys: list[str] = []
        for a in getattr(p, "about", []) or []:
            keys.append(a)
        if isinstance(getattr(p, "about", None), str):
            keys.append(p.about)
        for c in list(getattr(p, "commitments", []) or []) + list(getattr(p, "action_items", []) or []) + list(getattr(p, "deferrals", []) or []):
            keys.append(c.about)
            merger.add(canonical_key(c.about, slug_map), set(), set(), text=getattr(c, "what", None))
            msgs.add(msg_thread.get(c.evidence.source_id, c.evidence.source_id))
            ents.update(w.lower() for w in getattr(c, "to_whom", []) or [])
        for d in getattr(p, "decisions", []) or []:
            keys.append(d.about)
        summary = getattr(p, "summary", None) or getattr(p, "what", None)
        for k in keys:
            merger.add(canonical_key(k, slug_map), ents, msgs, text=summary)
    return merger


def compute_world(world: NormalizedWorld, extractions: list, profile: ProfileConfig, settings: Settings,
                  as_of: datetime, llm=None, ctx=None, decider=None) -> ComputeResult:
    """v1: contacts → effective facts → about-key merge → candidate rules → context, from extractions."""
    from ..util import domain_of, slugify
    from .candidates import ComputeInputs, generate, resolve_thresholds
    from .context import apply_context
    from .facts import collect_claims, effective_facts
    from .linker import Linker

    linker = Linker(llm, ctx, decider=decider, jev_min_p=settings.llm.jev_min_probability)
    directory = contacts_mod.build_contacts(world, extractions, profile, linker)
    _inherit_org_tiers(directory, world.owner_emails)
    behavior_stats(directory, world, as_of, settings.thresholds_default.behavior_window_days)
    slug_map = directory.slug_map()
    note_dates = {f"note:{n.path}": n.header_date for n in world.notes}
    facts = effective_facts(profile, collect_claims(extractions, note_dates))
    msg_thread = {f"msg:{m.message_id}": t.thread_id for t in world.threads for m in t.messages}
    merger = _extraction_keys(extractions, slug_map, msg_thread)
    person = slugify(profile.person or "")
    generic = {person, person.split("-")[0], slugify(profile.company or ""), *(domain_of(e).split(".")[0] for e in world.owner_emails)}
    generic |= set(world.owner_emails)
    generic.discard("")
    own = set(generic)   # Avery and Avery's company: shared by every internal thread, so never a context link
    for c in directory.contacts:
        if c.relationship.category == "team" or any(e in world.owner_emails for e in c.emails):
            generic |= {c.contact_id, *[e.lower() for e in c.emails], *[n.lower() for n in c.names]}
    merger.generic_entities = generic
    about_map, merges = merger.resolve(linker.group_topics(merger.by_kind()))
    ci = ComputeInputs(world, extractions, profile, settings, as_of, directory, facts, about_map, resolve_thresholds(profile, settings),
                       linker=linker)
    cands = generate(ci)
    cold = {c.contact_id for c in directory.contacts if c.relationship.category == "cold_inbound"}
    if cold:  # architecture §6.4 / §8: individual cold-inbound threads never become candidates
        cands = [c for c in cands if c.type == "recruiter_pattern" or not any(e in cold for e in c.entities)]
    new_keys = [c.about for c in cands if c.about not in merger.keys]
    for c in cands:
        f = c.facts
        merger.add(c.about, set(c.entities), {msg_thread.get(e.source_id, e.source_id) for e in c.evidence},
                   text=f.get("summary") or f.get("subject") or f.get("title") or f.get("what") or f.get("headline"))
    groups = merger.groups + (linker.group_topics(merger.by_kind()) if new_keys else [])
    about_map, merges = merger.resolve(groups)
    for c in cands:
        c.about = about_map.get(c.about, c.about)
    idx = ContextIndex(world, extractions, as_of, settings.context.window_days, settings.context.max_items, ignore=own)
    apply_context(cands, idx, world.freshness)
    cands.sort(key=lambda c: (c.type, c.about, c.evidence[0].source_id if c.evidence else ""))
    for i, c in enumerate(cands, 1):
        c.candidate_id = f"c{i}"
    stats = {"contacts": len(directory.contacts), "candidates": len(cands), "by_type": {}, "about_merges": len(merges),
             "facts_drift": sum(1 for f in facts if f.drift)}
    for c in cands:
        stats["by_type"][c.type] = stats["by_type"].get(c.type, 0) + 1
    stats["links"] = len(linker.log)
    return ComputeResult(directory.contacts, directory, facts, cands, merges, about_map, idx, stats, links=linker.log)


__all__ = ["ComputeResult", "ContactDirectory", "Spine", "assemble", "build_spine", "compute_world"]
