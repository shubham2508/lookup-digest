"""Reader diagnostics (PIVOT_SPEC §6, handoff C1): per labeled thread, did its reader say what the answer key implies?

Replaces the v1 extraction metrics. Reported, never gated: the digest-level metrics are the target.

Expected `needs_avery` for thread T on run day d. T must be fully visible at that morning's as_of (every labeled
message sent by then); a partly visible thread is not scored that day, since its labels describe the whole thread.
1. T is cited by an expected item included that day:
   - T is labeled must_not_surface → the item comes from a pattern, sweep or net built on T (recruiter pattern,
     cadence watch, handover profile update, hiring stall), not from T's own reader: not scored.
   - otherwise → yes, with that item's priority band and action types.
2. T is labeled must_not_surface → no (the precision set).
3. The day's expectations hold T back: one of T's about labels is in that day's `absent`, or an expected item with
   include: false cites T → no (timing traps, e.g. S3 before its threshold).
4. Otherwise the label decides: yes when the ball is on Avery, an ask to Avery is open, or Avery's own commitment is
   open and not fulfilled elsewhere (`fulfilled_by_source`, S16); else no.

A reader's verdict on T: `yes` if any of its findings on T says yes; `unsure` if one says unsure with a question card
(counted separately, not as a hit); `no` if all say no; `none` if it read T and emitted nothing; `not read` if no
reader call was made for T (the cost log tags every reader call with its thread; the router or the window left T out).
Newsletter / automated / marketing items labeled must_not_surface: only "no finding (any origin) said yes".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from eval.manifest_schema import ItemLabel, Manifest, RunDayExpectation

from .artifacts import RunView, Signal
from .common import Miss, StageMetrics, rate
from .match import about_match, max_priority

NOISE_KINDS = ("newsletter", "automated", "marketing")


def label_says_yes(item: ItemLabel) -> bool:
    e = item.expected
    if e is None:
        return False
    return (e.ball_awaiting == "avery" or any(a.to_avery and a.status == "open" for a in e.asks)
            or any(c.owner == "avery" and c.status_in_thread == "open" and not c.fulfilled_by_source for c in e.commitments))


def visible(item: ItemLabel, day: int, as_of_time: str) -> str:
    """all | some | none: how much of the thread exists at that morning's as_of."""
    seen = [(m.day, m.time) <= (day, as_of_time) for m in item.messages]
    if not seen:
        return "none"
    return "all" if all(seen) else ("some" if any(seen) else "none")


@dataclass
class ThreadExpectation:
    source_id: str
    storyline: str | None
    expect: str | None                                    # yes | no | None (not scored)
    why: str
    bands: list[str] = field(default_factory=list)        # acceptable priorities (from the backing item)
    actions: list[str] = field(default_factory=list)      # any one of these action types
    backs: list[str] = field(default_factory=list)        # about keys of the expected items it backs


def thread_expectation(item: ItemLabel, rd: RunDayExpectation) -> ThreadExpectation:
    sid = item.source_id
    backing = [ei for ei in rd.items if ei.include and sid in ei.cites_any]
    if backing:
        if item.must_not_surface:
            return ThreadExpectation(sid, item.storyline, None, "must-not thread behind a pattern/sweep/net item",
                                     backs=[ei.about for ei in backing])
        bands = sorted({p for ei in backing for p in (ei.priority_band or ([ei.priority] if ei.priority else []))})
        acts = sorted({a for ei in backing for a in ei.actions})
        return ThreadExpectation(sid, item.storyline, "yes", "backs an expected item", bands, acts, [ei.about for ei in backing])
    if item.must_not_surface:
        return ThreadExpectation(sid, item.storyline, "no", f"must not surface ({item.must_not_reason or '?'})")
    abouts = item.expected.about if item.expected else []
    if any(about_match(a, k) for a in abouts for k in rd.absent) or any(
            not ei.include and sid in ei.cites_any for ei in rd.items):
        return ThreadExpectation(sid, item.storyline, "no", "held back that day (absent / excluded)")
    return ThreadExpectation(sid, item.storyline, "yes" if label_says_yes(item) else "no", "label")


def reader_verdict(sigs: list[Signal]) -> str:
    if any(s.needs_avery == "yes" for s in sigs):
        return "yes"
    if any(s.needs_avery == "unsure" and s.live for s in sigs):
        return "unsure"
    return "no" if sigs else "none"


def score_readers(view: RunView, manifest: Manifest, day: int) -> StageMetrics:
    sm = StageMetrics("read")
    try:
        rd = manifest.run_day(day)
    except KeyError:
        sm.notes.append(f"no run_day {day} in manifest")
        return sm
    readers = [s for s in view.signals if s.origin == "thread_reader"]
    by_thread: dict[str, list[Signal]] = {}
    for s in readers:
        if s.thread:
            by_thread.setdefault(s.thread, []).append(s)
    if not view.findings:
        sm.notes.append("no findings.jsonl rows: reader diagnostics need a v2 run")
    read = {view.index.resolve(r.data.get("tag")) for r in view.cost_rows if r.data.get("role") == "thread_reader"} - {None}

    as_of = manifest.meta.as_of_time
    exp_yes = hit = unsure = 0
    band_n = band_ok = act_n = act_ok = 0
    mn_n = mn_clean = 0
    other_no_n = other_no_yes = 0
    partial = context = 0
    for item in manifest.items:
        if item.kind != "thread":
            continue
        vis = visible(item, day, as_of)
        if vis != "all":
            partial += vis == "some"
            continue
        te = thread_expectation(item, rd)
        if te.expect is None:
            context += 1
            continue
        sigs = by_thread.get(item.source_id, [])
        got = reader_verdict(sigs)
        if got == "none" and read and item.source_id not in read:
            got = "not read"
        yes_sigs = [s for s in sigs if s.needs_avery == "yes"]
        link = view.signal_link(yes_sigs[0] if yes_sigs else sigs[0]) if sigs else view.link("findings")
        tag = f"{item.source_id}{' (' + item.storyline + ')' if item.storyline else ''}"
        if te.expect == "yes":
            exp_yes += 1
            if got == "yes":
                hit += 1
            else:
                unsure += got == "unsure"
                sm.misses.append(Miss(f"{tag}: needs_avery [{te.why}]", "yes", got, link, "read"))
                continue
            got_p = max_priority(s.priority for s in yes_sigs)
            if te.bands:
                band_n += 1
                if got_p in te.bands:
                    band_ok += 1
                else:
                    sm.misses.append(Miss(f"{tag}: priority for {te.backs}", te.bands, got_p, link, "read"))
            if te.actions:
                act_n += 1
                got_a = sorted({a for s in yes_sigs for a in s.actions})
                if set(got_a) & set(te.actions):
                    act_ok += 1
                else:
                    sm.misses.append(Miss(f"{tag}: action for {te.backs}", te.actions, got_a, link, "read"))
        elif item.must_not_surface:
            mn_n += 1
            if got == "yes":
                sm.misses.append(Miss(f"{tag}: must not surface ({item.must_not_reason or '?'})", "no", "yes", link, "read"))
            else:
                mn_clean += 1
        else:
            other_no_n += 1
            if got == "yes":
                other_no_yes += 1
                sm.misses.append(Miss(f"{tag}: needs_avery [{te.why}]", "no", "yes", link, "read"))

    # labeled noise outside threads: no finding of any origin may say yes
    noise_n = noise_clean = 0
    backing = {sid for ei in rd.items if ei.include for sid in ei.cites_any}
    for item in manifest.items:
        if (item.kind not in NOISE_KINDS or not item.must_not_surface or item.source_id in backing
                or visible(item, day, as_of) == "none"):
            continue
        noise_n += 1
        loud = [s for s in view.signals if s.needs_avery == "yes" and item.source_id in s.sources]
        if loud:
            sm.misses.append(Miss(f"{item.source_id}: {item.kind} must not surface", "no finding says yes",
                                  loud[0].label(), view.signal_link(loud[0]), loud[0].stage))
        else:
            noise_clean += 1

    counts = {v: sum(1 for s in readers if s.needs_avery == v) for v in ("yes", "unsure", "no")}
    sm.metrics = {
        "reader_recall": rate(hit, exp_yes),
        "expected_yes": exp_yes,
        "said_unsure_with_card": unsure,
        "priority_in_band": rate(band_ok, band_n),
        "expected_action_present": rate(act_ok, act_n),
        "must_not_precision": rate(mn_clean, mn_n),
        "must_not_threads": mn_n,
        "unexpected_yes_other": f"{other_no_yes}/{other_no_n}",
        "noise_items_clean": rate(noise_clean, noise_n),
        "threads_not_fully_visible": partial,
        "threads_behind_pattern_items": context,
        "threads_read": len(read) if read else "unknown (no reader rows in cost.jsonl)",
        "reader_findings": f"{len(readers)} (yes {counts['yes']} · unsure {counts['unsure']} · no {counts['no']}) "
                           f"on {len(by_thread)} threads",
    }
    return sm
