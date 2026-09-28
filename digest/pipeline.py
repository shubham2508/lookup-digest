"""The fixed DAG (architecture §1). M3 covers profile compile → ingest → normalize → router → extract; later
milestones append compute → triage → reduce → compose → materialize → verify → render. Never crashes on bad
model output or a broken source: it degrades and records why (CLAUDE.md rule 5, DESIGN_LOG §4.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .compile.profile import CompiledProfile, compile_profile
from .config import Settings, load_settings
from .extract import ExtractStats, extract_world
from .ingest import DataMissing, load_world
from .llm import LLM
from .normalize import NormalizedWorld, normalize_world
from .normalize.freshness import header_fragment
from .paths import ROOT, data_dir
from .runs import RunContext, parse_as_of
from .schemas import Extraction
from .store import Store

STAGES_M3 = ("compile_profile", "ingest", "normalize", "extract")
STAGES_PENDING = ("compute", "triage", "reduce", "compose", "materialize", "verify", "render")


@dataclass
class PipelineResult:
    ctx: RunContext
    profile: CompiledProfile
    world: NormalizedWorld
    extractions: list[Extraction]
    extract_stats: ExtractStats
    summary: dict
    pending_stages: tuple[str, ...]

    @property
    def freshness_line(self) -> str:
        return " · ".join(header_fragment(f, self.world.as_of) for f in self.world.freshness.values())


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
    store.upsert("runs", {"run_id": ctx.run_id, "world": ctx.world, "as_of": ctx.as_of.isoformat(), "variant": ctx.variant,
                          "customize": str(ctx.customize) if ctx.customize else None, "cost_usd": None,
                          "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")})
    store.commit()


def run_pipeline(world: str, as_of: str | None = None, *, variant: str | None = None, customize: Path | None = None,
                 runs_dir: Path | None = None, llm: LLM | None = None, settings: Settings | None = None,
                 profile_path: Path | None = None, profile_out: Path | None = None, store: Store | None = None) -> PipelineResult:
    settings = settings or load_settings()
    tz = ZoneInfo(settings.timezone)
    as_of_dt = parse_as_of(as_of, settings.timezone) if as_of else datetime.now(tz).replace(microsecond=0)
    ddir = data_dir(world)
    if not ddir.is_dir():
        raise DataMissing(f"no data directory for world {world!r} at {ddir}")
    ctx = RunContext(world, as_of_dt, variant, customize, runs_dir=runs_dir)
    llm = llm or LLM(cache_dir=ROOT / settings.llm.cache_dir, cost_log=ctx.cost_log, seed=settings.llm.seed,
                     max_retries_transport=settings.llm.max_retries_transport)
    llm.cost_log = ctx.cost_log

    with ctx.timed("compile_profile"):
        profile = compile_profile(llm, profile_path, profile_out, tag="profile")
        if profile.degraded:
            ctx.degrade("compile_profile", "profile.md", profile.degraded)

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

    with ctx.timed("persist"):
        own_store = store is None
        st = store or Store(store_path(settings, world))
        try:
            with st:
                persist(st, ctx, norm, extractions)
        finally:
            if own_store:
                st.close()

    summary = ctx.finish()
    summary.update({
        "owner_email": norm.owner_email, "threads": len(norm.threads), "messages": len(norm.messages),
        "forwarded_messages": norm.forwarded_count, "events": len(norm.events), "notes": len(norm.notes),
        "tasks": len(norm.tasks), "extractions": len(extractions), "extract": stats.__dict__,
        "freshness": {k: {"state": f.state, "latest": f.latest_item_time.isoformat() if f.latest_item_time else None,
                          "age_hours": f.age_hours} for k, f in norm.freshness.items()},
        "profile_cached": profile.cached, "pending_stages": list(STAGES_PENDING),
    })
    ctx.write_json("run", summary)
    return PipelineResult(ctx, profile, norm, extractions, stats, summary, STAGES_PENDING)
