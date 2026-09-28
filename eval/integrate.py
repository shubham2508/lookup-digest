"""Integration matrix: every product run the eval needs, then the eval, as one command.

    digest eval --matrix --world dev|heldout|tests/fixtures/mini [--dry-run] [--keep-going]
    scripts/integrate.sh dev

For the world's manifest (run days 26–30 at meta.as_of_time, 06:00 PT):
  1. runs       `digest run` for every run day
  2. variants   on the last run day: the honesty variants (stale_inbox, no_notes, corrupt_ics)
  3. customize  on the last run day: every profile/customize/*.md
  4. baseline   on the last run day: `digest baseline`
  5. simulate   `digest simulate --fresh` over the run days (at most 5); OPEN_QUESTIONS #13b
  6. eval       `digest eval --customize-suite --baseline`

Each step is a subprocess of the real CLI. Exit codes: 0 ok; 3 "not implemented yet" (a Track A stage missing)
→ blocked; 2 no data/manifest → blocked; anything else → failed. By default the matrix stops at the first step
that does not succeed and marks the rest skipped (`--keep-going` runs everything that can still run). The log is
written to runs/<world>/integration.json and printed as a table. Exit code: 0 all ok, 3 blocked, 1 failed.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from digest.paths import ROOT
from eval.manifest_schema import Manifest

from .scorer.conditions import BUILTIN_VARIANTS, CUSTOMIZE_DIR, honesty_ids
from .scorer.runner import as_of_for
from .sim_avery.sim import run_digest_cli

Cmd = Callable[[list[str]], tuple[int, str]]
SIM_MAX_DAYS = 5


@dataclass
class Step:
    group: str
    name: str
    args: list[str]
    status: str = "pending"  # pending | ok | blocked | failed | skipped | planned
    exit: int | None = None
    seconds: float | None = None
    tail: str = ""

    @property
    def command(self) -> str:
        return "digest " + " ".join(self.args)


@dataclass
class MatrixResult:
    world: str
    started: str
    steps: list[Step] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        if any(s.status == "failed" for s in self.steps):
            return "failed"
        if any(s.status == "blocked" for s in self.steps):
            return "blocked"
        if all(s.status == "planned" for s in self.steps):
            return "planned"
        return "ok" if all(s.status == "ok" for s in self.steps) else "incomplete"

    @property
    def exit_code(self) -> int:
        return {"ok": 0, "planned": 0, "blocked": 3}.get(self.outcome, 1)

    def table(self) -> str:
        rows = ["| # | group | step | status | exit | s |", "|---|---|---|---|---|---|"]
        for n, s in enumerate(self.steps, 1):
            rows.append(f"| {n} | {s.group} | `{s.command}` | {s.status} | {'' if s.exit is None else s.exit} | "
                        f"{'' if s.seconds is None else s.seconds} |")
        return "\n".join(rows)


def plan(world: str, manifest: Manifest, customize_dir: Path | None = None) -> list[Step]:
    days = manifest.meta.run_days
    at = {d: as_of_for(manifest, d).strftime("%Y-%m-%dT%H:%M") for d in days}
    last = days[-1]
    steps = [Step("runs", f"day {d}", ["run", "--world", world, "--as-of", at[d]]) for d in days]
    for v in honesty_ids(manifest):
        if v not in BUILTIN_VARIANTS:
            steps.append(Step("variants", v, ["run", "--world", world, "--as-of", at[last], "--variant", v]))
    for p in sorted((customize_dir or CUSTOMIZE_DIR).glob("*.md")):
        rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
        steps.append(Step("customize", p.stem, ["run", "--world", world, "--as-of", at[last], "--customize", str(rel)]))
    steps.append(Step("baseline", "baseline", ["baseline", "--world", world, "--as-of", at[last]]))
    steps.append(Step("simulate", f"{min(SIM_MAX_DAYS, len(days))} days",
                      ["simulate", "--world", world, "--days", str(min(SIM_MAX_DAYS, len(days))), "--fresh"]))
    steps.append(Step("eval", "eval", ["eval", "--world", world, "--customize-suite", "--baseline"]))
    return steps


def classify(code: int) -> str:
    return "ok" if code == 0 else ("blocked" if code in (2, 3) else "failed")


def run_matrix(world: str, manifest: Manifest, *, dry_run: bool = False, keep_going: bool = False,
               cmd: Cmd = run_digest_cli, log: Callable[[str], None] = print, runs_root: Path | None = None,
               customize_dir: Path | None = None) -> MatrixResult:
    res = MatrixResult(world=world, started=datetime.now().isoformat(timespec="seconds"),
                       steps=plan(world, manifest, customize_dir))
    stop = False
    for n, s in enumerate(res.steps, 1):
        if dry_run:
            s.status = "planned"
            log(f"[{n:2}/{len(res.steps)}] plan  {s.command}")
            continue
        if stop:
            s.status = "skipped"
            continue
        t0 = time.perf_counter()
        code, out = cmd(s.args)
        s.exit, s.seconds, s.tail = code, round(time.perf_counter() - t0, 1), out[-400:]
        s.status = classify(code)
        log(f"[{n:2}/{len(res.steps)}] {s.status:7} {s.command}" + (f"  → {out.strip().splitlines()[-1][:120]}"
                                                                   if s.status != "ok" and out.strip() else ""))
        if s.status != "ok" and not keep_going:
            stop = True
    if not dry_run:
        root = runs_root or ROOT / "runs" / world
        root.mkdir(parents=True, exist_ok=True)
        (root / "integration.json").write_text(json.dumps(
            {"world": world, "started": res.started, "outcome": res.outcome, "steps": [asdict(s) for s in res.steps]},
            indent=2), encoding="utf-8")
    return res
