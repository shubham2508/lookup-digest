"""Stage attribution (eval.md §1, DESIGN_LOG §10.2): every miss is pinned to the first stage that lost it.

Chain for an expected item: extraction → compute → triage → compose (incl. reduce and verify) → materializer.
Markdown-only runs (the naive baseline) are one call, so their misses are attributed to `baseline`.

- missing expected item / wrong property: walk the chain and stop at the first artifact that no longer carries it.
- unwanted item (should be absent): the stage that introduced it. A candidate of a code-threshold type the manifest
  does not expect that day is compute's error (e.g. S3 quiet at 2 business days); otherwise triage, whose job is
  to filter what compute proposes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from eval.manifest_schema import Manifest

from .artifacts import RunView
from .common import claimed_abouts, extractions_for, select_candidates, select_items
from .match import about_match, type_matches
from .triage import triage_outcome, triage_rows_for

THRESHOLD_TYPES = ("quiet_thread", "commitment_due", "commitment_overdue", "hiring_stall", "recruiter_pattern",
                   "cadence_drop", "calendar_conflict", "obligation_cadence", "task_due", "declined_meeting",
                   "commitment_not_in_tasks")


@dataclass
class Attribution:
    stage: str
    evidence: str
    links: list[str] = field(default_factory=list)


def attribute_missing(view: RunView, manifest: Manifest, about: str | None, cites_any: list[str] | None = None,
                      *, priority: list[str] | str | None = None, section: str | None = None,
                      action: str | None = None, extraction_misses: dict[str, list] | None = None) -> Attribution:
    """Why an expected item (or one of its properties) did not make it into the digest."""
    if view.markdown_only:  # the naive baseline is one call: there are no stages to blame
        return Attribution("baseline", "not in the baseline's digest.md as expected", [view.link("digest")])
    cites = list(cites_any or [])
    claimed = claimed_abouts(manifest, view.day, about)
    ex_rows = extractions_for(view, set(cites), None if cites else about)
    if cites and not ex_rows:
        return Attribution("extraction", f"no extraction for {cites}", [view.link("extractions")])
    if extraction_misses:
        bad = [m for s in cites for m in extraction_misses.get(s, [])]
        if bad and not select_candidates(view, about=about, cites_any=cites, claimed=claimed):
            return Attribution("extraction", "; ".join(m.what for m in bad[:3]), [m.link for m in bad[:3] if m.link])

    cands = select_candidates(view, about=about, cites_any=cites, claimed=claimed) if about or cites else []
    if not cands:
        return Attribution("compute", f"no candidate for {about or cites}", [view.link("candidates")]
                           + [view.link("extractions", r.line) for r in ex_rows[:2]])
    cand_links = [view.link("candidates", c.line) for c in cands[:2]]

    rows = triage_rows_for(view, about or "", cites, claimed)
    out = triage_outcome(rows)
    tri_link = [view.link("triage", out["line"])] if out["line"] else [view.link("triage")]
    if not rows:
        return Attribution("triage", "candidate never triaged (dropped or degraded)", cand_links + [view.link("degradations")])
    if not out["include"]:
        return Attribution("triage", "triage include=false", tri_link)
    pri = [priority] if isinstance(priority, str) else priority
    if pri and out["priority"] not in pri:
        return Attribution("triage", f"triage priority {out['priority']}, expected {pri}", tri_link)
    if action and action not in out["actions"]:
        return Attribution("triage", f"triage proposed {out['actions']}, not {action}", tri_link)
    if section and out["section"] != section:
        return Attribution("triage", f"triage section {out['section']}, expected {section}", tri_link)

    rendered = select_items(view, manifest, {"about": about} if about else {}, cites) if (about or cites) else []
    if not rendered:
        rec = [it for it in view.reduce.get("items", []) if about_match(it.get("about"), about)]
        dropped = [v for v in view.verify.get("violations", []) if v.get("fix") == "dropped"
                   and any(v.get("item_id") == r.get("id") for r in rec)]
        where = "dropped by verify" if dropped else ("kept by reduce, not placed by compose" if rec else "lost at reduce")
        link = view.link("verify") if dropped else view.link("compose")
        return Attribution("compose", where, tri_link + [link])
    if section and not any(r.section == section for r in rendered if r.placement != "also_pending"):
        return Attribution("compose", f"placed in {[r.section or r.placement for r in rendered]}, expected {section}",
                           [view.link("compose")])
    if pri and not any(r.priority in pri for r in rendered):
        return Attribution("compose", f"reduce priority {[r.priority for r in rendered]}, expected {pri}", [view.link("reduce")])
    if action and not any(action in r.action_types for r in rendered):
        return Attribution("compose", f"final actions {[r.action_types for r in rendered]} lack {action}", [view.link("compose")])
    return Attribution("materializer", "item and action present; the rendered action is wrong", [view.link("actions")])


def attribute_unwanted(view: RunView, manifest: Manifest, day: int, items) -> Attribution:
    """Why an item that should be absent was rendered."""
    if view.markdown_only:
        return Attribution("baseline", "rendered in the baseline's digest.md", [view.link("digest")])
    try:
        expected = manifest.run_day(day).candidates
    except KeyError:
        expected = []
    links = [view.link("compose")]
    for it in items:
        for cid in it.candidate_ids:
            c = view.candidate(cid)
            if c is None:
                continue
            ctype = c.data.get("type", "")
            expected_here = any(type_matches(ctype, e.type) and about_match(c.data.get("about"), e.about) for e in expected)
            if any(type_matches(ctype, t) for t in THRESHOLD_TYPES) and not expected_here:
                return Attribution("compute", f"candidate {ctype} {c.data.get('about')} should not exist on day {day}",
                                   [view.link("candidates", c.line)])
            tri = view.triage_for(cid)
            if tri:
                links.append(view.link("triage", tri[0].line))
    return Attribution("triage", "triage included an item that should not surface", links)
