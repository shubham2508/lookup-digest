"""Compose / final-digest metrics (eval.md §2.4) and materializer code checks (§2.5)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from digest.config import Settings, load_settings
from eval.manifest_schema import Manifest

from .artifacts import RunView
from .attribution import attribute_missing, attribute_unwanted
from .common import Miss, StageMetrics, is_never_draft, rate, select_items
from .markdown_view import resolve_citation
from .match import norm_text

EXPECTED_PROFILE = Path(__file__).resolve().parents[1] / "expected" / "profile.yaml"


def _stage(view: RunView, stage: str) -> str:
    return "baseline" if view.markdown_only else stage


def expected_p0(manifest: Manifest, day: int):
    try:
        rd = manifest.run_day(day)
    except KeyError:
        return []
    return [ei for ei in rd.items if ei.include and (ei.priority == "P0" or (ei.priority_band and set(ei.priority_band) == {"P0"}))]


def score_digest(view: RunView, manifest: Manifest, day: int, settings: Settings | None = None) -> StageMetrics:
    settings = settings or load_settings()
    sm = StageMetrics("digest")
    try:
        rd = manifest.run_day(day)
    except KeyError:
        sm.notes.append(f"no run_day {day} in manifest")
        return sm

    # P0 recall — the gate: item, one-liner, or also-pending all count
    p0 = expected_p0(manifest, day)
    p0_hit = 0
    for ei in p0:
        if select_items(view, manifest, {"about": ei.about}, ei.cites_any):
            p0_hit += 1
        else:
            att = attribute_missing(view, manifest, ei.about, ei.cites_any)
            sm.misses.append(Miss(f"P0 missing: {ei.about} ({att.evidence})", "rendered", "absent",
                                  att.links[0] if att.links else view.link("digest"), att.stage))

    # one thing
    one_ok = None
    if rd.one_thing:
        ot = next((r for r in view.rendered if r.is_one_thing), None)
        one_ok = ot is not None and ot in select_items(view, manifest, {"about": rd.one_thing.about}, rd.one_thing.cites_any)
        if not one_ok:
            rendered = select_items(view, manifest, {"about": rd.one_thing.about}, rd.one_thing.cites_any)
            att = (attribute_missing(view, manifest, rd.one_thing.about, rd.one_thing.cites_any) if not rendered
                   else None)
            sm.misses.append(Miss("one thing", rd.one_thing.about, ot.about if ot else None,
                                  att.links[0] if att and att.links else view.link("compose"),
                                  att.stage if att else _stage(view, "compose")))

    # must-not: labeled noise that appeared (cited by any rendered item)
    shown = {s for r in view.rendered for s in r.source_ids}
    noise_shown = [s for s in rd.noise_source_ids if s in shown]
    for sid in noise_shown:
        att = attribute_unwanted(view, manifest, day, [r for r in view.rendered if sid in r.source_ids])
        sm.misses.append(Miss(f"noise surfaced: {sid}", "absent", "rendered", att.links[0], att.stage))
    absent_shown = [a for a in rd.absent if select_items(view, manifest, {"about": a}, [])]
    for key in absent_shown:
        att = attribute_unwanted(view, manifest, day, select_items(view, manifest, {"about": key}, []))
        sm.misses.append(Miss(f"must be absent: {key}", "absent", "rendered", att.links[0], att.stage))

    # section placement for rendered expected items
    sec_ok = sec_n = 0
    for ei in rd.items:
        if not (ei.include and ei.section):
            continue
        hits = [r for r in select_items(view, manifest, {"about": ei.about}, ei.cites_any)
                if r.placement != "also_pending" and r.section is not None]
        if not hits:
            continue
        sec_n += 1
        if any(r.section == ei.section for r in hits):
            sec_ok += 1
        else:
            sm.misses.append(Miss(f"{ei.about}: section", ei.section, hits[0].section, view.link("compose"), _stage(view, "compose")))

    # compose-vs-reduce disagreements, listed for review (not errors)
    flags: list[str] = []
    reduce_ids = {it.get("id") for it in view.reduce.get("items", [])}
    for r in view.rendered:
        if r.is_one_thing and r.priority in ("P2", "P3"):
            flags.append(f"one thing is {r.priority}: {r.about}")
        rec = next((it for it in view.reduce.get("items", []) if it.get("id") == r.id), None)
        if rec and r.placement == "section" and r.section and rec.get("section") and rec["section"] != r.section:
            flags.append(f"section moved {rec['section']}→{r.section}: {r.about}")
        if rec and r.placement == "also_pending" and rec.get("priority") == "P0":
            flags.append(f"P0 demoted to also-pending: {r.about}")
        if reduce_ids and r.id not in reduce_ids and view.candidate(r.id) is None:
            flags.append(f"compose referenced unknown id {r.id}")

    # verify stats, falling back to the rendered markdown
    stats = view.verify.get("stats", {})
    budget = stats.get("budget") or settings.budget.length_words
    words = stats.get("words", view.digest.word_count)
    header_ok = bool(stats.get("header_present", view.digest.header.lower().startswith("as of")))
    md_items = [i for i in view.digest.items if i.section not in ("also_pending", "profile_updates")]
    cited = sum(1 for i in md_items if i.citations)
    unresolved = [v for v in view.verify.get("violations", []) if v.get("fix") == "unresolved"]
    # citation validity from the markdown (eval.md §8; same for pipeline and baseline): email/note/task citations
    # that resolve to a labeled source. Calendar and external-source citations are not in the manifest.
    md_cites = [c for i in view.digest.items for c in i.citations if c.kind in ("email", "thread", "note", "task", "tasks")]
    md_ok = sum(1 for c in md_cites if resolve_citation(c, view.index, manifest))

    sm.metrics = {
        "p0_recall": rate(p0_hit, len(p0)),
        "p0_expected": len(p0),
        "p0_gate": (p0_hit == len(p0)) if p0 else None,
        "one_thing_correct": one_ok,
        "must_not_rate": rate(len(noise_shown), len(rd.noise_source_ids)),
        "absent_violations": len(absent_shown),
        "section_placement_accuracy": rate(sec_ok, sec_n),
        "compose_reduce_flags": flags,
        "words": words,
        "length_budget": budget,
        "length_ok": words <= budget,
        "header_present": header_ok,
        "items_cited_rate": rate(cited, len(md_items)),
        "citations_resolved_rate": rate(stats.get("citations_resolved", 0), stats.get("citations_total", 0)),
        "md_citations_valid_rate": rate(md_ok, len(md_cites)),
        "verify_unresolved": len(unresolved),
    }
    return sm


# ----------------------------------------------------------------------------- materializer
_SENT = re.compile(r"[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$")


def sentence_count(text: str) -> int:
    body = []
    for line in (text or "").strip().splitlines():
        s = line.strip().strip(">").strip()
        if not s or norm_text(s) in ("avery", "- avery", "— avery", "thanks, avery", "thanks,"):
            continue
        body.append(s)
    return len([s for s in _SENT.findall(" ".join(body)) if re.search(r"\w", s)])


def load_expected_profile(path: Path | None = None) -> dict:
    p = path or EXPECTED_PROFILE
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def stale_profile_values(manifest: Manifest, profile: dict | None = None) -> dict[str, tuple[str, set[str]]]:
    """subject → (profile value, data values) where the data contradicts the profile (e.g. ARR $3.2M vs $3.4M)."""
    profile = profile if profile is not None else load_expected_profile()
    facts = {norm_text(f["subject"]): f["value"] for f in profile.get("facts", [])}
    data: dict[str, set[str]] = {}
    for item in manifest.items:
        if item.expected:
            for c in item.expected.claims:
                data.setdefault(norm_text(c.subject), set()).add(c.value)
    return {s: (facts[s], vals) for s, vals in data.items() if s in facts and facts[s] not in vals}


def score_materializer(view: RunView, manifest: Manifest, settings: Settings | None = None,
                       profile: dict | None = None) -> StageMetrics:
    settings = settings or load_settings()
    sm = StageMetrics("materialize")
    drafts = view.drafts()
    stale = stale_profile_values(manifest, profile)
    ok = {"sentences": 0, "banned": 0, "never_draft": 0, "assumptions": 0, "numbers": 0}
    n_assump = n_numbers = 0
    for d in drafts:
        link = view.link("actions", d["_line"])
        text = d.get("draft") or ""
        who = d.get("target") or d.get("recipient_name")
        n = sentence_count(text)
        if n <= settings.drafts.max_sentences:
            ok["sentences"] += 1
        else:
            sm.misses.append(Miss(f"draft to {who}: {n} sentences", f"≤{settings.drafts.max_sentences}", n, link, _stage(view, "materialize")))
        banned = [b for b in settings.drafts.banned_phrases if norm_text(b) in norm_text(text)]
        if not banned:
            ok["banned"] += 1
        else:
            sm.misses.append(Miss(f"draft to {who}: banned phrase", "none", banned, link, _stage(view, "materialize")))
        if not (is_never_draft(manifest, d.get("target")) or is_never_draft(manifest, d.get("recipient_name"))):
            ok["never_draft"] += 1
        else:
            sm.misses.append(Miss(f"draft to never-draft contact {who}", "no draft", "draft", link, _stage(view, "materialize")))
        if d.get("brief_assumptions"):
            n_assump += 1
            if d.get("assumptions"):
                ok["assumptions"] += 1
            else:
                sm.misses.append(Miss(f"draft to {who}: assumptions not shown", d["brief_assumptions"], [], link, _stage(view, "materialize")))
        used_stale = [(s, pv) for s, (pv, _) in stale.items() if norm_text(pv) in norm_text(text)]
        if any(norm_text(v) in norm_text(text) for _, vals in stale.values() for v in vals) or used_stale:
            n_numbers += 1
            if not used_stale:
                ok["numbers"] += 1
            else:
                sm.misses.append(Miss(f"draft to {who}: profile value used over data", {s: stale[s][1] for s, _ in used_stale},
                                      [pv for _, pv in used_stale], link, _stage(view, "materialize")))
    total = len(drafts)
    sm.metrics = {
        "drafts": total,
        "max_sentences_ok": rate(ok["sentences"], total),
        "banned_phrases_absent": rate(ok["banned"], total),
        "no_never_draft_recipient": rate(ok["never_draft"], total),
        "assumptions_shown": rate(ok["assumptions"], n_assump),
        "numbers_match_data": rate(ok["numbers"], n_numbers),
    }
    return sm
