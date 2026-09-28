"""Per-run artifacts under runs/<world>/<as_of>[_<variant>]/ (architecture §10) and the run context.

Track A writes these, Track C reads them, so the file names are fixed here.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .llm import CostLog, TraceLog
from .paths import RUNS_DIR

ARTIFACTS: dict[str, str] = {
    "extractions": "extractions.jsonl",   # one Extraction per document
    "contacts": "contacts.json",          # list[Contact]
    "candidates": "candidates.jsonl",     # one Candidate per line
    "triage": "triage.jsonl",             # one TriageResult per line (+ candidate_id)
    "reduce": "reduce.json",              # ordered surviving items, merges, overflow
    "compose": "compose.json",            # ComposeResult
    "actions": "actions.jsonl",           # one materialized action per line
    "verify": "verify.json",              # hard-rule checks, fixes, drops
    "digest": "digest.md",                # the rendered digest
    "suggested_tasks": "suggested_tasks.md",
    "cost": "cost.json",                  # totals from CostLog
    "cost_log": "cost.jsonl",             # every LLM call
    "run": "run.json",                    # as_of, world, variant, customize, timings, degradations
    "degradations": "degradations.jsonl", # skipped items (LLMOutputInvalid, dropped evidence, ...)
    "trace": "trace.jsonl",               # every LLM call with full input/output (debug UI)
}


def parse_as_of(value: str, tz: str = "America/Los_Angeles") -> datetime:
    """'2026-09-24T06:00' (naive, PT) or any ISO string with an offset → aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def run_dir_name(as_of: datetime, variant: str | None = None) -> str:
    return as_of.strftime("%Y-%m-%dT%H-%M") + (f"_{variant}" if variant else "")


def _jsonable(obj: Any) -> Any:
    """Recursively convert Pydantic models (at any depth) so lists of models serialize as JSON objects."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    return obj


@dataclass
class RunContext:
    world: str
    as_of: datetime
    variant: str | None = None
    customize: Path | None = None
    runs_dir: Path | None = None
    baseline: bool = False
    tag: str | None = None
    run_dir: Path = field(init=False)
    cost_log: CostLog = field(init=False)
    trace_log: TraceLog = field(init=False)
    degradations: list[dict] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    @property
    def suffix(self) -> str | None:
        """Run-dir suffix: <variant>, customize-<stem>, baseline, <tag>, joined with '+' when combined (OPEN_QUESTIONS #7c, #14)."""
        parts = []
        if self.variant:
            parts.append(self.variant)
        if self.customize:
            parts.append(f"customize-{Path(self.customize).stem}")
        if self.baseline:
            parts.append("baseline")
        if self.tag:
            parts.append(self.tag)
        return "+".join(parts) or None

    def __post_init__(self) -> None:
        base = self.runs_dir or RUNS_DIR
        self.run_dir = base / self.world / run_dir_name(self.as_of, self.suffix)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cost_log = CostLog(self.run_dir / ARTIFACTS["cost_log"])
        self.trace_log = TraceLog(self.run_dir / ARTIFACTS["trace"])

    @property
    def run_id(self) -> str:
        return f"{self.world}/{run_dir_name(self.as_of, self.suffix)}"

    # ------------------------------------------------------------------ artifacts
    def path(self, artifact: str) -> Path:
        return self.run_dir / ARTIFACTS[artifact]

    def write_jsonl(self, artifact: str, rows: Iterable[Any]) -> Path:
        p = self.path(artifact)
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(_jsonable(r), ensure_ascii=False, default=str) + "\n" for r in rows)
        return p

    def write_json(self, artifact: str, obj: Any) -> Path:
        p = self.path(artifact)
        p.write_text(json.dumps(_jsonable(obj), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return p

    def write_text(self, artifact: str, text: str) -> Path:
        p = self.path(artifact)
        p.write_text(text, encoding="utf-8")
        return p

    def read_jsonl(self, artifact: str) -> list[dict]:
        p = self.path(artifact)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_json(self, artifact: str) -> Any:
        return json.loads(self.path(artifact).read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ honesty bookkeeping
    def degrade(self, stage: str, item: str, reason: str, **extra: Any) -> None:
        """Record a skipped/degraded item; the digest header reports these (CLAUDE.md rule 5)."""
        self.degradations.append({"stage": stage, "item": item, "reason": reason, **extra})

    @contextmanager
    def timed(self, stage: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.timings[stage] = round(self.timings.get(stage, 0.0) + time.perf_counter() - t0, 3)

    def finish(self) -> dict:
        totals = self.cost_log.totals()
        self.write_json("cost", totals)
        self.write_jsonl("degradations", self.degradations)
        summary = {
            "run_id": self.run_id, "world": self.world, "as_of": self.as_of.isoformat(), "variant": self.variant,
            "baseline": self.baseline, "tag": self.tag, "suffix": self.suffix,
            "customize": str(self.customize) if self.customize else None, "timings_s": self.timings,
            "wall_s": round(time.time() - self.started_at, 3), "cost_usd": totals["cost_usd"],
            "llm_calls": totals["calls"], "llm_cached": totals["cached"], "degradations": len(self.degradations),
        }
        self.write_json("run", summary)
        return summary
