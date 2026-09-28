"""Multi-day simulation checks (eval.md §7, M9), scored from the runs, rulings.yaml and the simulate transcript.

`digest simulate` saves its transcript to runs/<world>/simulation.json (day, as_of, answers given). The
manifest's own multi-day assertions (ruling_applied, escalation_framing, resolved_disappears,
content_overrides_ruling) are scored with the base assertions over every run day. On top of those, these generic
checks need no labels, so they hold on any world:

- sim-ruling-recorded:  every card sim_avery answered produced a ruling in rulings.yaml (scope about or contact
                        matches the carded item, option_chosen matches the answer).
- sim-ruling-applied:   the day after an answer, the same scope is not carded again, and N ≥ 1 rulings were
                        applied: run.json `rulings_applied`, else the header's "applied N learned rules" (#13c).
- sim-escalation:       an item rendered on ≥ 3 run days in a row (times_surfaced ≥ 2 by the third) is framed as
                        an escalation from the third day on ("third time", "still", "again", ...).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from digest.config import load_settings
from digest.paths import ROOT
from eval.manifest_schema import Manifest

from .artifacts import RenderedItem, RunView
from .assertions import ESCALATION_RE, AssertionResult
from .attribution import lead_signal
from .match import about_match, norm_text

APPLIED_RE = re.compile(r"applied (\d+) learned rules?", re.I)
TRANSCRIPT = "simulation.json"


def state_path(template: str, runs_root: Path, world: str | None = None) -> Path:
    """Resolve a `settings.store` path template. One under `runs/{world}/` follows `runs_root`, so a `--runs`
    override moves the product state together with the runs it belongs to."""
    prefix = "runs/{world}/"
    if template.startswith(prefix):
        return runs_root / template[len(prefix):]
    return ROOT / template.format(world=world or runs_root.name)


def rulings_path(runs_root: Path, world: str | None = None) -> Path:
    """OPEN_QUESTIONS #13a (ruled): `settings.store.rulings_path_template`, per world (runs/<world>/rulings.yaml)."""
    return state_path(load_settings().store.rulings_path_template, runs_root, world)


def load_rulings(runs_root: Path, world: str | None = None) -> list[dict]:
    p = rulings_path(runs_root, world)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    return data.get("rulings", []) if isinstance(data, dict) else list(data)


def rulings_applied(view: RunView) -> int:
    """OPEN_QUESTIONS #13c (ruled): run.json `rulings_applied` first, else the header's "applied N learned rules"."""
    n = view.run.get("rulings_applied")
    if isinstance(n, int):
        return n
    m = APPLIED_RE.search(view.digest.header)
    return int(m.group(1)) if m else 0


def load_transcript(runs_root: Path) -> list[dict] | None:
    p = runs_root / TRANSCRIPT
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _res(cid: str, kind: str, passed: bool | None, evidence: str, stage: str | None = None,
         links: list[str] | None = None, day: int | None = None) -> AssertionResult:
    return AssertionResult(id=cid, kind=kind, passed=passed, evidence=evidence, attributed_stage=None if passed else stage,
                           artifact_links=links or [], run_day=day, description="eval.md §7 (generic)")


def _scope_hits(ruling: dict, about: str | None, item: RenderedItem | None) -> bool:
    scope = ruling.get("scope") or {}
    if scope.get("about") and about_match(scope["about"], about):
        return True
    if scope.get("contact") and item is not None:
        c = norm_text(scope["contact"])
        people = [norm_text(e) for e in item.entities] + [norm_text(str(a.get("target") or "")) for a in item.actions]
        return any(c and (c in p or p in c) for p in people if p)
    return False


def _carded(view: RunView, about: str | None) -> list[RenderedItem]:
    return [i for i in view.rendered if "question" in i.action_types and about_match(i.about, about)]


def score_simulation(manifest: Manifest, views: dict[int, RunView], transcript: list[dict] | None,
                     rulings: list[dict], rulings_file: Path | None = None) -> list[AssertionResult]:
    out: list[AssertionResult] = []
    if transcript is None:
        return [_res("sim", "simulation", None, "not run: no simulation.json (run `digest simulate`)")]
    answers = [(step["day"], a) for step in transcript for a in step.get("answers", [])]
    rlink = [str(rulings_file)] if rulings_file else []

    # 1. every answer produced a ruling
    if not answers:
        out.append(_res("sim-ruling-recorded", "simulation", None, "no cards were answered during the simulation"))
    for day, a in answers:
        view = views.get(day)
        item = next((i for i in (view.rendered if view else []) if about_match(i.about, a.get("about"))), None)
        hit = [r for r in rulings if _scope_hits(r, a.get("about"), item)
               and (r.get("option_chosen") in (None, a.get("option")))]
        ok = bool(hit) and a.get("exit", 0) == 0
        out.append(_res(f"sim-ruling-recorded:d{day}:{a.get('question')}", "sim_ruling_recorded", ok,
                        f"day {day} {a.get('question')}→{a.get('option')} ({a.get('about')}): "
                        + (f"ruling {hit[0].get('id')}" if hit else f"no ruling for this scope ({len(rulings)} in file)"),
                        "read", rlink, day))  # `digest answer` writes it; readers and sweeps are its consumers

    # 2. the next run applies it: same scope not carded again, header counts the learned rule
    days = sorted(views)
    for day, a in answers:
        later = [d for d in days if d > day]
        if not later:
            continue
        nd = later[0]
        nview = views[nd]
        again = _carded(nview, a.get("about"))
        applied = rulings_applied(nview)
        ok = not again and applied >= 1
        why = [] if ok else ([f"carded again: {[i.id for i in again]}"] if again else []) + (
            [] if applied else ["header does not report applied learned rules"])
        asker = lead_signal([s for i in again for s in nview.item_signals(i)])
        stage = (asker.stage if asker else "read") if again else "compose"
        out.append(_res(f"sim-ruling-applied:d{nd}:{a.get('about')}", "sim_ruling_applied", ok,
                        f"day {nd}: " + ("scope not carded again; header: applied " + str(applied) if ok else "; ".join(why)),
                        stage, [nview.signal_link(asker) if asker else nview.link("triage" if again else "digest")], nd))

    # 3. escalation framing for items that keep coming back
    streak: dict[str, int] = {}
    prev: set[str] = set()
    for d in days:
        view = views[d]
        now = {i.about for i in view.rendered if i.about and i.placement != "also_pending"}
        for key in sorted(now):  # deterministic order for the report
            streak[key] = streak.get(key, 0) + 1 if key in prev else 1
            if streak[key] >= 3:
                it = next(i for i in view.rendered if i.about == key)
                ok = bool(ESCALATION_RE.search(f"{it.what} {it.why}"))
                stage = "merge" if it.times_surfaced < 2 else "compose"  # history joins where findings become candidates
                out.append(_res(f"sim-escalation:d{d}:{key}", "sim_escalation", ok,
                                f"day {d}: {key} surfaced {streak[key]} days running (times_surfaced {it.times_surfaced}): "
                                + (f"framed: {it.why[:80]}" if ok else f"flat framing: {it.what[:60]} / {it.why[:60]}"),
                                stage, [view.link("reduce" if stage == "merge" else "compose")], d))
        prev = now
    return out
