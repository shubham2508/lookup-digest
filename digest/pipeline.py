"""The fixed DAG (architecture §1). M3 covers profile compile → ingest → normalize → router → extract; later
milestones append compute → triage → reduce → compose → materialize → verify → render. Never crashes on bad
model output or a broken source: it degrades and records why (CLAUDE.md rule 5, DESIGN_LOG §4.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .compile.profile import CompiledProfile, compile_profile
from .compose import compose_digest, title_for
from .compute import ComputeResult, compute_world
from .config import Settings, load_settings
from .extract import ExtractStats, extract_world
from .history import (
    answered_after_digest,
    load_rulings,
    mark_resolved,
    record_items,
    rulings_path,
    times_surfaced,
)
from .ingest import DataMissing, load_world
from .llm import LLM
from .materialize import materialize, suggested_tasks_md
from .normalize import NormalizedWorld, normalize_world
from .normalize.freshness import header_fragment
from .paths import ROOT, data_dir
from .reduce import reduce_items
from .render import CitationIndex, render_digest
from .runs import RunContext, parse_as_of
from .schemas import ComposeResult, CustomizeOverrides, Extraction, ReduceResult, VerifyResult
from .store import Store
from .triage import triage_candidates
from .verify import verify

STAGES = ("compile_profile", "ingest", "normalize", "extract", "compute", "triage", "reduce", "compose", "materialize", "verify", "render")
STAGES_PENDING: tuple[str, ...] = ()


@dataclass
class PipelineResult:
    ctx: RunContext
    profile: CompiledProfile
    world: NormalizedWorld
    extractions: list[Extraction]
    extract_stats: ExtractStats
    summary: dict
    pending_stages: tuple[str, ...] = ()
    compute: ComputeResult | None = None
    reduce: ReduceResult | None = None
    compose: ComposeResult | None = None
    verify: VerifyResult | None = None
    digest_md: str = ""

    @property
    def freshness_line(self) -> str:
        return " · ".join(header_fragment(f, self.world.as_of) for f in self.world.freshness.values())


SYNC_GAP_TYPES = {"quiet_thread", "commitment_overdue", "commitment_due", "reply_owed", "obligation_cadence"}


def qualify_for_freshness(composed: ComposeResult, by_item: dict, cands: dict, freshness: dict, as_of: datetime) -> None:
    """DESIGN_LOG §4.4, enforced in code: a 'quiet' or 'overdue' conclusion drawn from a stale inbox says it may be a
    sync gap; a calendar conflict drawn while the work calendar is unreadable says overlaps were not checked."""
    email, cal = freshness.get("email"), freshness.get("calendar")
    email_stale = email is not None and email.state != "ok"
    cal_bad = cal is not None and cal.state in ("unreadable", "missing")
    synced = email.latest_item_time.strftime("%a %H:%M") if email_stale and email.latest_item_time else "unknown"
    for ci in composed.items:
        it = by_item.get(ci.id)
        if it is None:
            continue
        types = set(it.candidate_types)
        add = []
        if email_stale and types & SYNC_GAP_TYPES and "sync gap" not in ci.why.lower():
            add.append(f"May be a sync gap: inbox last synced {synced}.")
        if cal_bad and any(t.startswith("calendar_conflict") for t in types) and "calendar" not in ci.why.lower():
            add.append("Work calendar unreadable; overlaps not checked.")
        if add:
            ci.why = (ci.why.rstrip() + " " + " ".join(add)).strip()


def _decider(llm: LLM, settings: Settings, ctx: RunContext):
    """Jev for the linker's pick-one questions when config/models.yaml has a `decider` role; None otherwise."""
    role = llm.models.roles.get("decider")
    if role is None or not role.model or not role.model.startswith("typesafe/"):
        return None
    from .compute.jev import JevDecider
    from .llm import load_api_key

    key = load_api_key(llm.models.provider.api_key_env)
    if not key:
        return None
    return JevDecider(api_key=key, model=role.model, cache_dir=ROOT / settings.llm.cache_dir, cost_log=ctx.cost_log,
                      trace_log=ctx.trace_log)


def store_path(settings: Settings, world: str) -> Path:
    return ROOT / settings.store.path_template.format(world=world)


def persist(store: Store, ctx: RunContext, world: NormalizedWorld, extractions: list[Extraction]) -> None:
    store.upsert_many("messages", [
        {"message_id": m.message_id, "thread_id": t.thread_id, "sent_at": m.sent_at.isoformat(), "from_addr": m.from_addr,
         "subject": m.subject, "is_from_avery": m.is_from_avery, **m.model_dump(mode="json")}
        for t in world.threads for m in t.messages])
    store.upsert_many("threads", [
        {"thread_id": t.thread_id, "router_type": t.router_type, "latest_at": t.messages[-1].sent_at.isoformat(),
         "message_ids": [m.message_id for m in t.messages]} for t in world.threads])
    store.upsert_many("events", [
        {"event_id": f"{e.uid}|{e.recurrence_id or ''}", "uid": e.uid, "recurrence_id": e.recurrence_id, "calendar": e.calendar,
         "start": e.start.isoformat(), "end": e.end.isoformat(), "organizer": e.organizer, "avery_partstat": e.avery_partstat,
         **e.model_dump(mode="json")} for e in world.events])
    store.upsert_many("notes", [
        {"path": n.path, "mtime": n.mtime.isoformat() if n.mtime else None,
         "note_date": n.header_date.isoformat() if n.header_date else None, "title": n.title, "attendees": n.attendees}
        for n in world.notes])
    store.upsert_many("tasks", [
        {"task_id": t.task_id, "title": t.title, "due": t.due.isoformat() if t.due else None, "status": t.status,
         **t.model_dump(mode="json")} for t in world.tasks])
    store.upsert_many("extractions", [
        {"input_hash": x.meta.input_hash, "source_id": x.source_id, "type": x.type, "prompt_version": x.meta.prompt_version,
         "model": x.meta.model, "created_at": x.meta.extracted_at.isoformat(), **x.model_dump(mode="json")}
        for x in extractions])
    store.upsert("runs", {"run_id": ctx.run_id, "world": ctx.world, "as_of": ctx.as_of.isoformat(), "variant": ctx.variant, "tag": ctx.tag,
                          "customize": str(ctx.customize) if ctx.customize else None, "cost_usd": None,
                          "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")})
    store.commit()


def run_pipeline(world: str, as_of: str | None = None, *, variant: str | None = None, customize: Path | None = None,
                 runs_dir: Path | None = None, llm: LLM | None = None, settings: Settings | None = None,
                 profile_path: Path | None = None, profile_out: Path | None = None, store: Store | None = None,
                 tag: str | None = None) -> PipelineResult:
    """The whole DAG for one as-of. Every LLM stage degrades on invalid output; nothing here raises on model errors."""
    settings = settings or load_settings()
    tz = ZoneInfo(settings.timezone)
    as_of_dt = parse_as_of(as_of, settings.timezone) if as_of else datetime.now(tz).replace(microsecond=0)
    ddir = data_dir(world)
    if not ddir.is_dir():
        raise DataMissing(f"no data directory for world {world!r} at {ddir}")
    ctx = RunContext(world, as_of_dt, variant, customize, runs_dir=runs_dir, tag=tag)
    llm = llm or LLM(cache_dir=ROOT / settings.llm.cache_dir, cost_log=ctx.cost_log, seed=settings.llm.seed,
                     max_retries_transport=settings.llm.max_retries_transport)
    llm.cost_log = ctx.cost_log
    llm.trace_log = ctx.trace_log

    with ctx.timed("compile_profile"):
        profile = compile_profile(llm, profile_path, profile_out, tag="profile")
        if profile.degraded:
            ctx.degrade("compile_profile", "profile.md", profile.degraded)
    overrides: CustomizeOverrides | None = None
    customize_notes: list[str] = []
    if customize is not None:
        with ctx.timed("compile_customize"):
            from .compile.customize import compile_customize

            overrides, customize_notes = compile_customize(llm, Path(customize), ctx)

    with ctx.timed("ingest"):
        raw = load_world(ddir, as_of_dt, tz, variant)
        for kind, st in raw.sources.items():
            if st.state != "ok":
                ctx.degrade("ingest", kind, f"source_{st.state}", detail=st.detail)
            for err in st.errors:
                ctx.degrade("ingest", kind, "parse_error", detail=err)

    with ctx.timed("normalize"):
        norm = normalize_world(raw, settings, profile.config.person)
        if norm.owner_email is None:
            ctx.degrade("normalize", "owner", "could not detect Avery's address from the data")

    with ctx.timed("extract"):
        extractions, stats = extract_world(llm, norm, profile.config, settings, ctx)
    ctx.write_jsonl("extractions", extractions)

    own_store = store is None
    st = store or Store(store_path(settings, world))
    st.connect()
    try:
        with ctx.timed("persist"):
            persist(st, ctx, norm, extractions)
        stage_notes: list[str] = []
        if profile.degraded:
            stage_notes.append("profile compiled with fallback config")
        for kind, f in norm.freshness.items():
            if f.state != "ok":
                stage_notes.append(f"{kind} {f.state}")

        with ctx.timed("compute"):
            comp = compute_world(norm, extractions, profile.config, settings, as_of_dt, llm=llm, ctx=ctx, decider=_decider(llm, settings, ctx))
            plain = variant is None and customize is None
            surfaced = times_surfaced(st, world, as_of_dt, tag=tag) if plain else {}
            for c in comp.candidates:
                c.times_surfaced = surfaced.get(c.about, 0)
            resolved = mark_resolved(st, world, as_of_dt, comp.candidates, tag=tag) if plain else 0
            answered = answered_after_digest(st, world, as_of_dt, comp.candidates, {t.thread_id: t for t in norm.threads}, tag=tag) if plain else set()
            for cid in answered:
                ctx.degrade("compute", cid, "answered_after_digest", detail="Avery replied after the digest showed it; not re-surfaced")
            comp.candidates = [c for c in comp.candidates if c.candidate_id not in answered]
        ctx.write_json("contacts", comp.contacts)
        ctx.write_jsonl("links", comp.links)
        ctx.write_jsonl("candidates", comp.candidates)
        st.upsert_many("contacts", [{"contact_id": c.contact_id, "category": c.relationship.category, "tier": c.tier, **c.model_dump(mode="json")} for c in comp.contacts])
        st.upsert_many("candidates", [{"run_id": ctx.run_id, "candidate_id": c.candidate_id, "type": c.type, "about": c.about, **c.model_dump(mode="json")} for c in comp.candidates])

        rulings = load_rulings(rulings_path(world, settings), as_of_dt)
        with ctx.timed("triage"):
            triage, tstats = triage_candidates(llm, comp.candidates, comp, profile.config, settings, ctx, rulings, as_of=as_of_dt)
        ctx.write_jsonl("triage", triage)
        st.upsert_many("triage_results", [{"run_id": ctx.run_id, "candidate_id": r.candidate_id, "include": r.include, "priority": r.priority,
                                           "section": r.section, **r.model_dump(mode="json")} for r in triage])
        if tstats.invalid_packs or tstats.missing:
            stage_notes.append(f"triage skipped {tstats.invalid_packs} pack(s), {len(tstats.missing)} item(s) shown from facts")

        with ctx.timed("reduce"):
            reduced = reduce_items(triage, comp.candidates, comp, settings.budget.k_cap, comp.about_merges)
        ctx.write_json("reduce", reduced)
        by_item = {it.id: it for it in reduced.items}
        cands = {c.candidate_id: c for c in comp.candidates}
        freshness_line = " · ".join(header_fragment(f, as_of_dt) for f in norm.freshness.values())
        header = f"As of {as_of_dt.strftime('%a %H:%M')} PT · {freshness_line}"
        if tstats.rulings_applied:
            header += f" · applied {tstats.rulings_applied} learned rule{'s' if tstats.rulings_applied != 1 else ''}"

        with ctx.timed("compose"):
            composed, cstats = compose_digest(llm, reduced, cands, profile.config, settings, ctx, freshness_line=freshness_line,
                                              rulings_applied=tstats.rulings_applied, customize=overrides, stage_notes=stage_notes,
                                              as_of=as_of_dt.isoformat(), compute=comp)
        if cstats.fallback:
            stage_notes.append("compose fell back to triage order")
        qualify_for_freshness(composed, by_item, cands, norm.freshness, as_of_dt)

        with ctx.timed("materialize"):
            actions, mstats = materialize(llm, composed, by_item, cands, comp, profile.config, settings, ctx, overrides)
        with ctx.timed("verify"):
            budget = overrides.length_words if overrides and overrides.length_words else settings.budget.length_words
            known = CitationIndex(norm).known
            msg_thread = {f"msg:{m.message_id}": t.thread_id for t in norm.threads for m in t.messages}
            router_types = {t.thread_id: t.router_type for t in norm.threads}
            ver = verify(composed, by_item, actions, cands, comp, triage, known, router_types, budget, header, overrides,
                         overflow=reduced.overflow, msg_thread=msg_thread)
            for iid in cstats.outside_filter:
                if iid not in ver.outside_filter:
                    ver.outside_filter.append(iid)
                    ver.also_pending = [i for i in ver.also_pending if i != iid]
            for iid in cstats.hidden_by_focus:
                ver.also_pending = [i for i in ver.also_pending if i != iid]
        ctx.write_json("compose", composed)
        ctx.write_jsonl("actions", ver.actions)
        ctx.write_json("verify", ver.result)
        ctx.write_text("suggested_tasks", suggested_tasks_md(ver.actions, as_of_dt.date().isoformat()))
        notes = list(dict.fromkeys(list(composed.header_notes) + customize_notes))
        dropped_n = sum(1 for v in ver.result.violations if v.fix == "dropped")
        if dropped_n:
            notes.append(f"{dropped_n} item(s) removed by hard rules (see verify.json)")
        if ctx.degradations:
            skipped = [d for d in ctx.degradations if d["reason"] not in ("code_fix", "evidence_replaced", "evidence_invalid")]
            if skipped:
                notes.append(f"{len(skipped)} item(s) degraded (see degradations.jsonl)")
        if resolved:
            notes.append(f"{resolved} earlier item(s) resolved")
        with ctx.timed("render"):
            titles = {it.id: title_for(it, cands) for it in reduced.items}
            md = render_digest(as_of=as_of_dt, header=header, compose=ver.compose, reduced=by_item, actions=ver.actions, cands=cands,
                               world=norm, also_pending=ver.also_pending, outside_filter=ver.outside_filter, titles=titles,
                               customize=overrides, header_notes=notes)
        ctx.write_text("digest", md)
        ver.result.stats.header_present = True
        ctx.write_json("verify", ver.result)
        actions_by_item: dict[str, list[str]] = {}
        for a in ver.actions:
            actions_by_item.setdefault(a.item_id, []).append(a.type)
        record_items(st, ctx.run_id, by_item, ver.compose, ver.also_pending, ver.outside_filter, actions_by_item, surfaced)
        st.upsert("runs", {"run_id": ctx.run_id, "world": world, "as_of": as_of_dt.isoformat(), "variant": variant,
                           "customize": str(customize) if customize else None, "baseline": False, "tag": tag,
                           "cost_usd": ctx.cost_log.totals()["cost_usd"], "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")})
        st.commit()
    finally:
        if own_store:
            st.close()

    summary = ctx.finish()
    summary.update({
        "owner_email": norm.owner_email, "threads": len(norm.threads), "messages": len(norm.messages),
        "forwarded_messages": norm.forwarded_count, "events": len(norm.events), "notes": len(norm.notes),
        "tasks": len(norm.tasks), "extractions": len(extractions), "extract": stats.__dict__,
        "compute": comp.stats, "triage": {"candidates": tstats.candidates, "packs": tstats.packs, "cached": tstats.cached,
                                          "invalid_packs": tstats.invalid_packs, "missing": tstats.missing, "fixes": len(tstats.fixes),
                                          "rulings_applied": tstats.rulings_applied},
        "reduce": {"items": len(reduced.items), "overflow": len(reduced.overflow), "dropped": len(reduced.dropped), "merges": len(reduced.about_merges)},
        "compose": {"cached": cstats.cached, "fallback": cstats.fallback, "fixes": cstats.fixes, "one_thing": composed.one_thing_id,
                    "placed": sum(len(s.item_ids) for s in composed.sections) + (1 if composed.one_thing_id else 0), "cut": len(composed.cut_ids)},
        "materialize": {"actions": mstats.actions, "llm_calls": mstats.llm_calls, "cached": mstats.cached, "draft_retries": mstats.draft_retries,
                        "drafts_dropped": mstats.drafts_dropped},
        "verify": ver.result.model_dump(mode="json"), "history": {"resolved_later": resolved, "answered_after_digest": len(answered)},
        "freshness": {k: {"state": f.state, "latest": f.latest_item_time.isoformat() if f.latest_item_time else None,
                          "age_hours": f.age_hours} for k, f in norm.freshness.items()},
        "profile_cached": profile.cached, "pending_stages": [], "header": header,
    })
    ctx.write_json("run", summary)
    return PipelineResult(ctx, profile, norm, extractions, stats, summary, (), comp, reduced, ver.compose, ver.result, md)
