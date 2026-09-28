"""Naive baseline (eval.md §8; M8): one long-context call over the whole ingested corpus + the full profile +
the default format. Same as-of rules as the pipeline (ingest filters), no extraction, no compute, no verify.
Writes runs/<world>/<as_of>_baseline/ with digest.md, cost.json, run.json, a stats-only verify.json."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .compile.profile import compile_profile
from .config import Settings, load_settings
from .ingest import DataMissing, load_world
from .llm import LLM, LLMError, LLMOutputInvalid
from .normalize import NormalizedWorld, normalize_world
from .normalize.freshness import header_fragment
from .paths import PROFILE_DIR, ROOT, data_dir
from .prompts import load_prompt
from .runs import RunContext, parse_as_of
from .schemas import BaselineDigest, VerifyResult, VerifyStats

MAX_CORPUS_CHARS = 700_000   # ≈ 175k tokens; older mail is dropped first beyond this


def corpus_text(world: NormalizedWorld, as_of: datetime, max_chars: int = MAX_CORPUS_CHARS) -> tuple[str, int]:
    parts: list[tuple[datetime, str]] = []
    for t in world.threads:
        lines = [f"### THREAD {t.thread_id} ({t.router_type})"]
        for m in t.messages:
            who = f"{m.from_name} <{m.from_addr}>" if m.from_name else m.from_addr
            lines.append(f"From: {who}\nTo: {', '.join(m.to)}\nDate: {m.sent_at.strftime('%a %Y-%m-%d %H:%M')}\nSubject: {m.subject}"
                         + (f"\n(forwarded by {m.forwarded_by})" if m.forwarded_by else "") + f"\n\n{m.body_new}"
                         + (f"\n{m.signature_block}" if m.signature_block else "") + "\n")
        parts.append((t.messages[-1].sent_at, "\n".join(lines)))
    cal = ["### CALENDAR"]
    for e in world.events:
        att = ", ".join(f"{a.email} ({a.partstat})" for a in e.attendees)
        cal.append(f"- {e.start.strftime('%a %Y-%m-%d %H:%M')}–{e.end.strftime('%H:%M')} [{e.calendar}] {e.title} · organizer {e.organizer}"
                   f" · you: {e.avery_partstat} · attendees: {att}" + (f" · created {e.created.strftime('%a %H:%M')}" if e.created else "")
                   + (f" · {e.description}" if e.description else ""))
    notes = ["### NOTES"]
    for n in world.notes:
        notes.append(f"--- {n.path}\n{n.text}")
    tasks = ["### TASKS (tasks.md)"] + [f"- [{'x' if t.status == 'done' else ' '}] {t.title}" + (f" (due: {t.due})" if t.due else "") for t in world.tasks]
    fixed = "\n".join(cal) + "\n\n" + "\n".join(notes) + "\n\n" + "\n".join(tasks) + "\n\n"
    parts.sort(key=lambda p: p[0], reverse=True)
    out, used, dropped = [], len(fixed), 0
    for _, text in parts:
        if used + len(text) > max_chars:
            dropped += 1
            continue
        out.append(text)
        used += len(text)
    out.reverse()
    return fixed + "\n".join(out), dropped


def run_baseline(world: str, as_of: str | None = None, *, runs_dir: Path | None = None, llm: LLM | None = None,
                 settings: Settings | None = None, profile_path: Path | None = None, profile_out: Path | None = None) -> dict:
    settings = settings or load_settings()
    tz = ZoneInfo(settings.timezone)
    as_of_dt = parse_as_of(as_of, settings.timezone) if as_of else datetime.now(tz).replace(microsecond=0)
    ddir = data_dir(world)
    if not ddir.is_dir():
        raise DataMissing(f"no data directory for world {world!r} at {ddir}")
    ctx = RunContext(world, as_of_dt, runs_dir=runs_dir, baseline=True)
    llm = llm or LLM(cache_dir=ROOT / settings.llm.cache_dir, cost_log=ctx.cost_log, seed=settings.llm.seed)
    llm.cost_log = ctx.cost_log
    llm.trace_log = ctx.trace_log
    profile_path = profile_path or PROFILE_DIR / "profile.md"
    profile_md = profile_path.read_text(encoding="utf-8")
    person = compile_profile(llm, profile_path, profile_out, write=True).config.person
    with ctx.timed("ingest"):
        raw = load_world(ddir, as_of_dt, tz)
        norm = normalize_world(raw, settings, person)
    with ctx.timed("baseline_call"):
        corpus, dropped = corpus_text(norm, as_of_dt)
        if dropped:
            ctx.degrade("baseline", "corpus", "truncated", detail=f"{dropped} oldest threads dropped to fit the context")
        prompt = load_prompt("baseline")
        text = prompt.render(avery_name=person, as_of=as_of_dt.isoformat(), profile_md=profile_md, corpus=corpus)
        try:
            r = llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": text}], BaselineDigest,
                             tag="baseline", max_tokens=16000)
            md = r.output.markdown.strip() + "\n"
        except (LLMOutputInvalid, LLMError) as e:
            ctx.degrade("baseline", "digest", type(e).__name__, detail=str(e)[:300])
            fresh = " · ".join(header_fragment(f, as_of_dt) for f in norm.freshness.values())
            md = (f"# Daily Digest — {as_of_dt.strftime('%A, %B %d, %Y')}\n\nAs of {as_of_dt.strftime('%a %H:%M')} PT · {fresh}"
                  f" · baseline unavailable ({type(e).__name__})\n")
    ctx.write_text("digest", md)
    body = re.sub(r"^\s*(#|As of|\s*[☐↳]|\s*Q\d|\s*Assumptions:|\s*\").*$", "", md, flags=re.M)
    words = len(re.sub(r"\*\[[^\]]*\]\*", "", body).split())
    ctx.write_json("verify", VerifyResult(stats=VerifyStats(words=words, budget=settings.budget.length_words,
                                                            header_present=md.lstrip().startswith("# ") and "As of" in md)))
    summary = ctx.finish()
    summary.update({"baseline": True, "threads": len(norm.threads), "corpus_chars": len(corpus), "threads_dropped": dropped,
                    "words": words, "digest": str(ctx.path("digest"))})
    ctx.write_json("run", summary)
    return summary
