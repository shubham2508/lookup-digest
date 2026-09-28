"""Stage attribution (eval.md §1, DESIGN_LOG §10.2, PIVOT_SPEC §6): every miss is pinned to the first stage that lost it.

v2 chain for an expected item: read → sweep → net → merge → compose → materialize → verify.

- Nobody noticed it: the stage that should have. A thread's reader (`read`); a note, task, event or newsletter's
  sweep (`sweep`); an automated message's safety net (`net`; readers read human threads only).
- Noticed but not surfaced, or surfaced wrong (needs_avery, priority, action, section): the stage of the finding's
  origin (reader → read, sweeps → sweep, safety net → net). When the finding was right and the code floors
  (triage.enforce: P0 earned, suspicious never P0, never_draft) changed it, `net` (the code between findings and merge).
- Surfaced but not on the page: `verify` if verify dropped it, `merge` if reduce folded it into another item or lost
  it, `compose` if reduce kept it and compose did not place it (or placed it wrong).
- On the page with the wrong action: `compose` (final actions) or `materialize` (the rendered action).
Markdown-only runs (the naive baseline) are one call, so their misses are attributed to `baseline`.

Unwanted item (should be absent): a safety net that fired on a day the answer key does not expect it → `net`;
otherwise the stage of the finding that said it needs Avery.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from eval.manifest_schema import Manifest

from .artifacts import RunView, Signal
from .common import claimed_abouts, select_items, signal_is_type, signals_for_expected
from .match import PRIORITY_ORDER, about_match, type_matches
from .triage import triage_outcome

# v1 code-threshold types: a finding-less candidate of one of these that the day does not expect is a net's error
THRESHOLD_TYPES = ("quiet_thread", "reply_owed", "commitment_due", "commitment_overdue", "hiring_stall",
                   "recruiter_pattern", "cadence_drop", "calendar_conflict", "obligation_cadence", "task_due",
                   "declined_meeting", "commitment_not_in_tasks")
_ORIGIN_ORDER = {"thread_reader": 0, "calendar_sweep": 1, "notes_tasks_sweep": 1, "news_sweep": 1, "safety_net": 2}


@dataclass
class Attribution:
    stage: str
    evidence: str
    links: list[str] = field(default_factory=list)


def lead_signal(signals: list[Signal]) -> Signal | None:
    """The finding to blame first: a reader before a sweep before a net, then the highest priority."""
    return min(signals, key=lambda s: (_ORIGIN_ORDER.get(s.origin or "", 0), PRIORITY_ORDER.get(s.priority or "", 9)),
               default=None)


def producer_stage(view: RunView, about: str | None, cites: list[str]) -> str:
    """The stage that should have noticed an expected item that no finding covers."""
    prefix_kind = {"note": "note", "task": "task", "event": "event", "thread": "thread", "msg": "thread"}
    kinds = {view.index.kind_of(s) or prefix_kind.get(s.split(":", 1)[0]) for s in cites}
    if "thread" in kinds:
        return "read"
    if kinds & {"note", "task", "event", "newsletter"}:
        return "sweep"
    if "automated" in kinds:
        return "net"
    return "read"


def attribute_missing(view: RunView, manifest: Manifest, about: str | None, cites_any: list[str] | None = None,
                      *, priority: list[str] | str | None = None, section: str | None = None,
                      action: str | None = None) -> Attribution:
    """Why an expected item (or one of its properties) did not make it into the digest."""
    if view.markdown_only:  # the naive baseline is one call: there are no stages to blame
        return Attribution("baseline", "not in the baseline's digest.md as expected", [view.link("digest")])
    cites = list(cites_any or [])
    claimed = claimed_abouts(manifest, view.day, about)
    found = signals_for_expected(view, about, cites, claimed, live=False)
    if not found:
        art = "findings" if view.findings else "candidates"
        return Attribution(producer_stage(view, about, cites), f"no finding for {about or cites}", [view.link(art)])
    live = [s for s in found if s.live]
    if not live:
        lead = lead_signal(found)
        return Attribution(lead.stage, f"{lead.label()}: not surfaced", [view.signal_link(s) for s in found[:2]])
    lead = lead_signal(live)
    flinks = [view.signal_link(s) for s in live[:2]]
    rows = [t for s in live if s.candidate_id for t in view.triage_for(s.candidate_id)]
    if not rows:
        return Attribution(lead.stage, f"{lead.label()} has no candidate / triage row (dropped or degraded)",
                           flinks + [view.link("degradations")])
    out = triage_outcome(rows)
    tri_link = [view.link("triage", out["line"])]
    if not out["include"]:
        return Attribution("net", "the finding said it needs Avery; include=false after the code floors (enforce)",
                           tri_link + flinks)
    pri = [priority] if isinstance(priority, str) else priority
    if pri and out["priority"] not in pri:
        finding_ok = any(s.priority in pri for s in live)
        return Attribution("net" if finding_ok else lead.stage,
                           f"priority {out['priority']}, expected {pri}" + (" (the code floors changed it)" if finding_ok else ""),
                           tri_link + flinks)
    if action and action not in out["actions"]:
        finding_ok = any(action in s.actions for s in live)
        return Attribution("net" if finding_ok else lead.stage, f"proposed {out['actions']}, not {action}", tri_link + flinks)
    if section and out["section"] != section:
        return Attribution(lead.stage, f"section {out['section']}, expected {section}", tri_link + flinks)

    rendered = select_items(view, manifest, {"about": about} if about else {}, cites) if (about or cites) else []
    if not rendered:
        cids = {s.candidate_id for s in live if s.candidate_id}
        recs = [it for it in view.reduce.get("items", []) if set(it.get("candidate_ids") or [it.get("id")]) & cids]
        if any(v.get("fix") == "dropped" and v.get("item_id") in {r.get("id") for r in recs}
               for v in view.verify.get("violations", [])):
            return Attribution("verify", "dropped by verify", [view.link("verify")])
        shown = [x for x in (view.rendered_by_id(r.get("id")) for r in recs) if x]
        if shown:
            return Attribution("merge", f"merged into {shown[0].id} ({shown[0].about})", [view.link("reduce")] + flinks)
        if recs:
            return Attribution("compose", "kept by reduce, not placed by compose", tri_link + [view.link("compose")])
        return Attribution("merge", "lost at reduce (grouped away or over the cap)", tri_link + [view.link("reduce")])
    if section and not any(r.section == section for r in rendered if r.placement != "also_pending"):
        return Attribution("compose", f"placed in {[r.section or r.placement for r in rendered]}, expected {section}",
                           [view.link("compose")])
    if pri and not any(r.priority in pri for r in rendered):
        return Attribution("merge", f"reduce priority {[r.priority for r in rendered]}, expected {pri}", [view.link("reduce")])
    if action and not any(action in r.action_types for r in rendered):
        return Attribution("compose", f"final actions {[r.action_types for r in rendered]} lack {action}", [view.link("compose")])
    return Attribution("materialize", "item and action present; the rendered action is wrong", [view.link("actions")])


def attribute_unwanted(view: RunView, manifest: Manifest, day: int, items) -> Attribution:
    """Why an item that should be absent was rendered."""
    if view.markdown_only:
        return Attribution("baseline", "rendered in the baseline's digest.md", [view.link("digest")])
    try:
        expected = manifest.run_day(day).candidates
    except KeyError:
        expected = []
    behind = [s for it in items for s in view.item_signals(it)]
    for s in behind:
        is_net = s.origin == "safety_net" or (s.artifact == "candidates" and not s.origin
                                               and any(type_matches(s.type, t) for t in THRESHOLD_TYPES))
        if not is_net:
            continue
        expected_here = any(signal_is_type(s, e.type) and any(about_match(a, e.about) for a in s.abouts) for e in expected)
        if not expected_here:
            return Attribution("net", f"{s.type} {s.abouts[:1]} should not fire on day {day}", [view.signal_link(s)])
    lead = lead_signal([s for s in behind if s.live])
    if lead is None:
        return Attribution("compose", "rendered an item no finding supports", [view.link("compose")])
    return Attribution(lead.stage, f"{lead.label()} said it needs Avery", [view.signal_link(lead)])
