"""Sweep and safety-net diagnostics (PIVOT_SPEC §6, handoff C2). Reported, never gated.

1. Planted calendar and notes/tasks traps: the day's expected candidates of the types below. A trap is found when a
   live finding of any origin (reader, sweep, net) is related to it: one of its about keys fuzzy-matches the trap's
   key, it cites a source the answer key cites for that trap's item, or it carries the net's type name and passes
   the #9 fallback. A `contradiction` trap also needs a finding that lists a contradiction (the Finding field).
2. Rescue list: findings a safety net added because no reader or sweep covered them (`rescued_by_safety_net`), by
   kind, with what each rescued (the expected item or trap it matches that day, or nothing: possible noise).
   Readers should rarely need rescuing.
"""
from __future__ import annotations

from collections import Counter

from eval.manifest_schema import ExpectedCandidate, Manifest, RunDayExpectation

from .artifacts import RunView, Signal
from .attribution import producer_stage
from .common import STRUCTURAL_TYPES, Miss, StageMetrics, fallback_signal_match, rate, signal_is_type
from .match import about_match, type_matches

TRAP_TYPES = ("calendar_conflict", "declined_meeting", "task_due", "obligation_cadence", "profile_drift", "contradiction")
CALENDAR_TYPES = ("calendar_conflict", "declined_meeting")


def trap_sources(rd: RunDayExpectation, ec: ExpectedCandidate) -> set[str]:
    """The sources the answer key cites for the item this trap feeds that day."""
    return {s for ei in rd.items if about_match(ei.about, ec.about) for s in ei.cites_any}


def finds_trap(view: RunView, s: Signal, ec: ExpectedCandidate, sources: set[str]) -> bool:
    typed = signal_is_type(s, ec.type)
    related = (any(about_match(a, ec.about) for a in s.abouts) or bool(s.sources & sources)
               or (typed and fallback_signal_match(view, s, ec.about, ec.storyline)))
    return (typed and related) if ec.type in STRUCTURAL_TYPES else related


def rescued_what(view: RunView, s: Signal, rd: RunDayExpectation) -> list[str]:
    items = [f"{ei.about} ({ei.priority or '/'.join(ei.priority_band) or '?'})" for ei in rd.items if ei.include and (
        any(about_match(a, ei.about) for a in s.abouts) or s.sources & set(ei.cites_any))]
    if items:
        return list(dict.fromkeys(items))
    return list(dict.fromkeys(f"expected {ec.type} {ec.about}" for ec in rd.candidates
                              if signal_is_type(s, ec.type) and finds_trap(view, s, ec, trap_sources(rd, ec))))


def score_sweeps(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("sweep")
    try:
        rd = manifest.run_day(day)
    except KeyError:
        sm.notes.append(f"no run_day {day} in manifest")
        return sm
    live = [s for s in view.signals if s.live]

    found = {"calendar": [0, 0], "notes_tasks": [0, 0]}
    by_origin: Counter = Counter()
    for ec in rd.candidates:
        if not any(type_matches(ec.type, t) for t in TRAP_TYPES):
            continue
        group = "calendar" if any(type_matches(ec.type, t) for t in CALENDAR_TYPES) else "notes_tasks"
        found[group][1] += 1
        srcs = trap_sources(rd, ec)
        hits = [s for s in live if finds_trap(view, s, ec, srcs)]
        tag = f"{ec.type} {ec.about}{' (' + ec.storyline + ')' if ec.storyline else ''}"
        if hits:
            found[group][0] += 1
            origins = sorted({s.origin or s.artifact for s in hits})
            by_origin.update(origins)
            sm.notes.append(f"found {tag} by {', '.join(origins)}")
        else:
            near = [s for s in view.signals if not s.live and finds_trap(view, s, ec, srcs)]
            got = f"said no: {near[0].label()}" if near else "no finding"
            link = view.signal_link(near[0]) if near else view.link("findings")
            # nobody saw it: the reader of a cited thread, else the sweep over the calendar / notes / tasks
            stage = near[0].stage if near else (producer_stage(view, ec.about, sorted(srcs)) if srcs else "sweep")
            sm.misses.append(Miss(f"trap {tag}", "found", got, link, stage))

    rescues = [s for s in view.signals if s.rescued]
    rescue_lines = []
    for s in rescues:
        what = rescued_what(view, s, rd)
        rescue_lines.append(f"{s.type} · '{s.title}' ({s.priority}) → "
                            f"{', '.join(what) if what else 'nothing expected that day (possible noise)'} · "
                            f"[{view.signal_link(s)}]({view.signal_link(s)})")
    if rescue_lines:
        sm.lists["Rescue list (safety net added what no reader or sweep covered)"] = rescue_lines

    n_cal, n_nt = found["calendar"], found["notes_tasks"]
    sm.metrics = {
        "trap_recall": rate(n_cal[0] + n_nt[0], n_cal[1] + n_nt[1]),
        "calendar_traps_found": f"{n_cal[0]}/{n_cal[1]}",
        "notes_tasks_traps_found": f"{n_nt[0]}/{n_nt[1]}",
        "traps_found_by_origin": dict(by_origin),
        "rescues": len(rescues),
        "rescues_by_kind": dict(Counter(s.type for s in rescues)),
        "rescues_matching_expected": sum(1 for s in rescues if rescued_what(view, s, rd)),
        "findings_by_origin": dict(Counter(s.origin or s.artifact for s in view.signals)),
    }
    return sm
