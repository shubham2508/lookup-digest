"""Build eval.manifest_schema.Manifest from the world script + labels + rendered artifacts (M2 step 3)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from eval.manifest_schema import (
    AboutKeyMerges,
    Assertion,
    ContactLabel,
    ExpectedAgreement,
    ExpectedAsk,
    ExpectedAutomated,
    ExpectedCandidate,
    ExpectedClaim,
    ExpectedCommitment,
    ExpectedExtraction,
    ExpectedItem,
    ExpectedNewsItem,
    ExpectedRoleChange,
    ExpectedScheduleMention,
    ExpectedSenderRelationship,
    ExpectedStageSignal,
    ItemLabel,
    LabelAudit,
    Manifest,
    MessageLabel,
    Meta,
    OneThing,
    RunDayExpectation,
    SimAveryAnswer,
    StageAt,
    Variant,
)

from .render_eml import RenderedMessage
from .timeline import Timeline
from .world import World, slugify

EXPECTED_FIELDS = set(ExpectedExtraction.model_fields)
_NOTE_KIND_MAP = {"meeting_notes": "meeting_notes", "draft": "draft", "todo": "todo", "status": "status"}


_NESTED = {
    "asks": ExpectedAsk, "commitments": ExpectedCommitment, "schedule_mentions": ExpectedScheduleMention,
    "stage_signals": ExpectedStageSignal, "role_changes": ExpectedRoleChange, "claims": ExpectedClaim,
    "news_items": ExpectedNewsItem, "agreements": ExpectedAgreement,
}
_NESTED_ONE = {"automated": ExpectedAutomated, "sender_relationship": ExpectedSenderRelationship}


def _strip(cls, d: dict) -> dict:
    return {k: v for k, v in d.items() if k in cls.model_fields}


def _expected(d: dict | None) -> ExpectedExtraction | None:
    """Tolerant: prose/storyline labels may carry extra keys or a scalar where a list is expected (and vice versa)."""
    if not d:
        return None
    clean = {k: v for k, v in d.items() if k in EXPECTED_FIELDS}
    if isinstance(clean.get("about"), str):
        clean["about"] = [clean["about"]]
    for key, cls in _NESTED.items():
        if isinstance(clean.get(key), list):
            clean[key] = [_strip(cls, x) for x in clean[key] if isinstance(x, dict)]
    for key, cls in _NESTED_ONE.items():
        if isinstance(clean.get(key), dict):
            clean[key] = _strip(cls, clean[key])
    auto = clean.get("automated")
    if isinstance(auto, dict) and isinstance(auto.get("about"), list):
        auto["about"] = auto["about"][0] if auto["about"] else None
    if isinstance(clean.get("news_items"), list):
        for ni in clean["news_items"]:
            if isinstance(ni.get("attaches_to"), str):
                ni["attaches_to"] = [ni["attaches_to"]]
    return ExpectedExtraction.model_validate(clean)


def _msg_label(m: RenderedMessage) -> MessageLabel:
    def emails(xs: list[str]) -> list[str]:
        return [re.search(r"<([^>]+)>", x).group(1) if "<" in x else x for x in xs]
    return MessageLabel(message_id=m.message_id, day=m.day, time=m.time, from_email=m.from_email, to=emails(m.to),
                        cc=emails(m.cc), beat_ref=m.beat_ref, must_include=m.must_include, is_from_avery=m.is_from_avery)


def _storyline_labels(w: World) -> dict[str, dict]:
    """thread/newsletter/automated id → {storyline, label dict} from storylines' `labels` lists."""
    out: dict[str, dict] = {}
    for s in w.storylines:
        for lab in s.get("labels", []):
            for key in ("thread", "newsletter", "automated"):
                if key in lab:
                    out[lab[key]] = {"storyline": s["id"], **lab}
    return out


def _storyline_note_labels(w: World) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in w.storylines:
        for lab in s.get("labels", []):
            if "note" in lab:
                out.setdefault(lab["note"], {"storyline": s["id"], **lab})
    return out


def _background_index(w: World) -> dict[str, dict]:
    """id → {must_not, reason, classification_case, storyline, labels} from background.yaml."""
    idx: dict[str, dict] = {}
    bg = w.background
    for it in bg.get("must_not_items", []):
        if "*" in it["id"]:
            continue
        idx[it["id"]] = {"must_not": True, "reason": it.get("reason"), "storyline": None}
    pp = bg.get("planted_patterns", {})
    for it in pp.get("talentbridge", {}).get("items", []):
        idx[it["id"]] = {"must_not": it.get("must_not_surface", True), "reason": it.get("must_not_reason"), "storyline": "BG-talentbridge"}
    for it in pp.get("newsletters", {}).get("decoy", []):
        idx[it["id"]] = {"must_not": True, "reason": it.get("must_not_reason"), "storyline": "BG-newsletter-decoy",
                         "expected": {"type": "newsletter", "news_items": it["items"]}}
    inj = pp.get("injection", {}).get("item")
    if inj:
        idx[inj["id"]] = {"must_not": False, "reason": None, "storyline": "BG-injection", "classification_case": "prompt_injection",
                          "expected": {"about": inj.get("about", []), **inj.get("labels", {})}}
    for it in pp.get("expense_reports", {}).get("items", []):
        idx[it["id"]] = {"must_not": False, "reason": None, "storyline": "BG-expenses",
                         "expected": {"type": "automated", "automated": {"system": it["system"], "action_bearing": True, "action_kind": it["action_kind"], "about": it["about"]}}}
    sp = pp.get("stripe_payout", {}).get("item")
    if sp:
        idx[sp["id"]] = {"must_not": False, "reason": None, "storyline": "BG-stripe",
                         "expected": {"type": "automated", "automated": {"system": sp["system"], "action_bearing": True, "action_kind": sp["action_kind"], "about": sp["about"]}}}
    for case in bg.get("classification_cases", []):
        tag = "BG-" + case["id"].replace("_", "-")
        threads = [case["thread"]] if case.get("thread") else case.get("threads", [])
        for t in threads:
            idx[t["id"]] = {"must_not": bool(t.get("must_not_surface")), "reason": t.get("must_not_reason"),
                            "storyline": tag, "classification_case": case["id"],
                            "expected": {"about": t.get("about", []), **case.get("labels", {})} if case.get("labels") else None}
    return idx


def _thread_item(w: World, thread: dict, msgs: list[RenderedMessage], slabels: dict, bgidx: dict) -> ItemLabel:
    tid = thread["thread_id"]
    lab = slabels.get(tid)
    bg = bgidx.get(tid, {})
    prose_lab = thread.get("labels") or {}
    storyline = (lab or {}).get("storyline") or thread.get("storyline") or bg.get("storyline")
    if lab:
        expected = _expected(lab.get("expected"))
        must_not, reason = bool(lab.get("must_not_surface")), lab.get("must_not_reason")
        case = lab.get("classification_case")
    elif bg.get("expected") or prose_lab.get("expected"):
        exp = dict(bg.get("expected") or {})
        exp.update(prose_lab.get("expected") or {})
        exp.setdefault("type", "human_thread")
        expected = _expected(exp)
        must_not = bool(prose_lab.get("must_not", bg.get("must_not", False)))
        reason = prose_lab.get("reason") or bg.get("reason")
        case = prose_lab.get("classification_case") or bg.get("classification_case")
    else:
        expected = _expected({"type": "human_thread"})
        must_not = bool(prose_lab.get("must_not", bg.get("must_not", True)))
        reason = prose_lab.get("reason") or bg.get("reason") or "unlabeled_background"
        case = prose_lab.get("classification_case") or bg.get("classification_case")
    return ItemLabel(source_id=tid, kind="thread", category=thread.get("category"), storyline=storyline,
                     must_not_surface=must_not, must_not_reason=reason if must_not else None,
                     classification_case=case, expected=expected, messages=[_msg_label(m) for m in msgs])


def _bulk_item(w: World, item: dict, msg: RenderedMessage, slabels: dict, bgidx: dict, story_by_id: dict) -> ItemLabel:
    iid = item["id"]
    lab = item.get("labels") or {}
    kind = lab.get("kind") or ("newsletter" if iid.startswith("nl-") else "automated" if iid.startswith("auto-") else "marketing" if iid.startswith("mkt-") else "thread")
    sl = slabels.get(iid)
    bg = bgidx.get(iid, {})
    storyline = (sl or {}).get("storyline") or story_by_id.get(iid) or bg.get("storyline")
    exp = None
    if sl and sl.get("expected"):
        exp = _expected(sl["expected"])
    elif lab.get("expected"):
        exp = _expected(lab["expected"])
    elif bg.get("expected"):
        exp = _expected(bg["expected"])
    else:
        exp = _expected({"type": {"newsletter": "newsletter", "marketing": "marketing", "automated": "automated", "thread": "human_thread"}[kind]})
    must_not = bool(lab.get("must_not", bg.get("must_not", kind in ("newsletter", "marketing"))))
    if sl is not None:
        must_not = bool(sl.get("must_not_surface", False))
    reason = lab.get("reason") or bg.get("reason") or (kind if kind in ("newsletter", "marketing") else None)
    return ItemLabel(source_id=iid, kind=kind, category=item.get("category"), storyline=storyline, must_not_surface=must_not,
                     must_not_reason=reason if must_not else None, classification_case=lab.get("classification_case") or bg.get("classification_case"),
                     expected=exp, messages=[_msg_label(msg)])


def _note_items(w: World, notes: list[dict], slabels_notes: dict) -> list[ItemLabel]:
    out = []
    for n in notes:
        spec = n["spec"]
        lab = dict(spec.get("labels") or {})
        sl = slabels_notes.get(spec["file"])
        story = lab.get("storyline")
        if isinstance(story, list):
            story = "+".join(story)
        exp: dict[str, Any] = {"type": "note", "note_kind": _NOTE_KIND_MAP.get(lab.get("note_kind") or spec.get("kind"), "meeting_notes")}
        for k in ("about", "agreements", "claims", "stage_signals", "draft_of"):
            if lab.get(k) is not None:
                exp[k] = lab[k]
        if sl and sl.get("expected"):
            for k, v in sl["expected"].items():
                if k in EXPECTED_FIELDS and k not in exp:
                    exp[k] = v
        out.append(ItemLabel(source_id=f"note:notes/{spec['file']}", kind="note", category=None, storyline=story,
                             expected=_expected(exp)))
    return out


def _task_items(w: World, tasks: dict) -> list[ItemLabel]:
    out = []
    for it in tasks["items"]:
        lab = it.get("labels", {})
        out.append(ItemLabel(source_id=f"task:{slugify(it['title'])}", kind="task", category=None, storyline=lab.get("storyline"),
                             expected=_expected({"type": "task", "about": [lab["about"]] if lab.get("about") else []})))
    return out


def _event_items(w: World, cal_events: dict[str, list[dict]]) -> list[ItemLabel]:
    story_by_uid: dict[str, str] = {}
    for s in w.storylines:
        for ev in s.get("events", []):
            story_by_uid[ev["uid"]] = s["id"]
    out = []
    for evs in cal_events.values():
        for ev in evs:
            note = ev.get("note") or ""
            m = re.search(r"\b(S\d{1,2})\b", note)
            out.append(ItemLabel(source_id=f"event:{ev['uid']}", kind="event", category=None,
                                 storyline=story_by_uid.get(ev["uid"]) or (m.group(1) if m else None),
                                 must_not_surface="not a violation" in note or "never a deep-work" in note or "must not" in note,
                                 must_not_reason=("avery_organized_over_own_block" if "own block" in note or "Avery's choice" in note else None),
                                 expected=_expected({"type": "event"})))
    return out


def _contacts(w: World) -> list[ContactLabel]:
    out = []
    for p in w.people.values():
        if p.id == "avery":
            continue
        t = p.truth
        stages = [StageAt(from_day=s["day"], stage=s["stage"]) for s in t.get("stage_timeline", [])]
        replaces = None
        if t.get("replaces") and t["replaces"] in w.people:
            replaces = w.people[t["replaces"]].email
        org_name = w.orgs[p.org]["name"] if p.org and p.org in w.orgs else None
        out.append(ContactLabel(email=p.email, name=p.name, org=org_name, title=p.title, category=t.get("category", "unresolved"),
                                subtype=t.get("subtype"), tier=t.get("tier"), rules=list(t.get("rules", [])), stages=stages,
                                replaces=replaces, in_profile=bool(t.get("in_profile"))))
    return out


_REF_MAP: dict[str, str] = {}


def _ref(sid: str) -> str:
    """Translate symbolic world ids to manifest source ids: note:<file> → note:notes/<file>; task:<n> → task:<slug>."""
    return _REF_MAP.get(sid, sid)


def _refs(xs) -> list[str]:
    return [_ref(x) for x in (xs or [])]


def _item_from_spec(it: dict, storyline: str | None) -> ExpectedItem:
    notes = it.get("notes")
    if it.get("actions_any"):
        notes = (f"actions_any: {it['actions_any']}" + (f"; {notes}" if notes else ""))
    return ExpectedItem(about=it["about"], include=it.get("include", True), priority=it.get("priority"),
                        priority_band=list(it.get("priority_band", [])), section=it.get("section"),
                        actions=list(it.get("actions", [])), cites_any=_refs(it.get("cites_any")),
                        one_thing=bool(it.get("one_thing")), ambiguity=it.get("ambiguity"),
                        storyline=it.get("storyline") or storyline, notes=notes)


def _cand(c: dict, storyline: str | None) -> ExpectedCandidate:
    return ExpectedCandidate(type=c["type"], about=c["about"], storyline=c.get("storyline") or storyline,
                             facts_hint={k: v for k, v in (c.get("facts_hint") or {}).items() if isinstance(v, (str, int, float, bool))})


def _assertion(a: dict, storyline: str | None = None, variant: str | None = None) -> Assertion:
    args = dict(a.get("args") or {})
    if isinstance(args.get("source_id"), str):
        args["source_id"] = _ref(args["source_id"])
    if args.get("cites_any"):
        args["cites_any"] = _refs(args["cites_any"])
    return Assertion(id=a["id"], kind=a["kind"], run_day=a.get("run_day"), variant=a.get("variant") or variant,
                     customize=a.get("customize"), storyline=a.get("storyline") or storyline,
                     args=args, description=a.get("description"))


def _merge_run_days(entries: list[tuple[str | None, dict]], items_visible: dict[int, list[str]],
                    known: set[str] | None = None, problems: list[str] | None = None) -> list[RunDayExpectation]:
    days: dict[int, dict] = {d: {"candidates": [], "items": [], "absent": [], "one_thing": None, "noise": set()} for d in (26, 27, 28, 29, 30)}
    for storyline, e in entries:
        d = days[e["run_day"]]
        for c in e.get("candidates", []):
            d["candidates"].append(_cand(c, storyline))
        for it in e.get("items", []):
            d["items"].append(_item_from_spec(it, storyline))
        d["absent"] += list(e.get("absent", []))
        if e.get("one_thing"):
            d["one_thing"] = OneThing(about=e["one_thing"]["about"], cites_any=_refs(e["one_thing"].get("cites_any")))
        d["noise"] |= set(_refs(e.get("noise", [])))
    out = []
    for day, d in days.items():
        noise = sorted(d["noise"] | set(items_visible.get(day, [])))
        if known is not None:
            for sid in noise:
                if sid not in known and problems is not None:
                    problems.append(f"run_day {day}: noise source {sid!r} is not a rendered item")
            noise = [x for x in noise if x in known]
        out.append(RunDayExpectation(run_day=day, candidates=d["candidates"], items=d["items"], absent=sorted(set(d["absent"])),
                                     one_thing=d["one_thing"], noise_source_ids=noise))
    return out


def build_manifest(w: World, tl: Timeline, rendered: dict[str, list[RenderedMessage]], bulk_rendered: dict[str, RenderedMessage],
                   notes: list[dict], tasks: dict, cal_events: dict[str, list[dict]], counts: dict[str, int],
                   generated_at: datetime, seed: int, problems: list[str] | None = None) -> Manifest:
    _REF_MAP.clear()
    for n in w.notes["notes"]:
        _REF_MAP[f"note:{n['file']}"] = f"note:notes/{n['file']}"
    for t in w.notes["tasks"]["items"]:
        _REF_MAP[t["id"]] = f"task:{slugify(t['title'])}"
    slabels = _storyline_labels(w)
    slabels_notes = _storyline_note_labels(w)
    bgidx = _background_index(w)
    story_by_id: dict[str, str] = {}
    for s in w.storylines:
        for nl in s.get("newsletters", []):
            story_by_id[nl["id"]] = s["id"]
        for au in s.get("automated", []):
            story_by_id[au["id"]] = s["id"]

    items: list[ItemLabel] = []
    for t in w.threads:
        items.append(_thread_item(w, t, rendered[t["thread_id"]], slabels, bgidx))
    for it in w.bulk:
        items.append(_bulk_item(w, it, bulk_rendered[it["id"]], slabels, bgidx, story_by_id))
    items += _note_items(w, notes, slabels_notes)
    items += _task_items(w, tasks)
    items += _event_items(w, cal_events)

    # noise visible per run day: must-not email items whose first message is before that run's 06:00
    first_at: dict[str, datetime] = {}
    for tid, msgs in rendered.items():
        first_at[tid] = min(m.sent_at for m in msgs)
    for iid, m in bulk_rendered.items():
        first_at[iid] = m.sent_at
    visible: dict[int, list[str]] = {}
    for day in (26, 27, 28, 29, 30):
        cutoff = tl.dt(day, "06:00")
        visible[day] = [i.source_id for i in items if i.must_not_surface and i.source_id in first_at and first_at[i.source_id] <= cutoff]

    entries: list[tuple[str | None, dict]] = []
    assertions: list[Assertion] = []
    sims: list[SimAveryAnswer] = []
    merges = AboutKeyMerges()
    variants: list[Variant] = []
    for s in w.storylines:
        sid = s["id"]
        for e in s.get("expectations", []):
            entries.append((sid, e))
            for i, a in enumerate(e.get("assertions_inline", [])):
                assertions.append(Assertion(id=f"{sid}-d{e['run_day']}-inline-{i+1}", kind=a["kind"], run_day=e["run_day"], storyline=sid, args=dict(a["args"])))
        assertions += [_assertion(a, sid) for a in s.get("assertions", [])]
        assertions += [_assertion(a, sid) for a in s.get("simulate", [])]
        for extra in s.get("honesty", {}).values() if isinstance(s.get("honesty"), dict) else []:
            assertions += [_assertion(a, sid) for a in extra]
        sims += [SimAveryAnswer(**x) for x in s.get("sim_avery", [])]
        ak = s.get("about_keys") or {}
        merges.should_merge += [tuple(x) for x in ak.get("should_merge", [])]
        merges.should_not_merge += [tuple(x) for x in ak.get("should_not_merge", [])]
        for v in s.get("variants", []):
            v_entries = [(sid, e) for e in v.get("expectations", [])]
            variants.append(Variant(id=v["id"], kind="storyline", data_dir=f"data/{w.name}__{v['id']}",
                                    run_days=[rd for rd in _merge_run_days(v_entries, {}) if rd.absent or rd.items or rd.candidates],
                                    assertions=[_assertion(a, sid, v["id"]) for a in v.get("assertions", [])]))
    bg = w.background
    pp = bg.get("planted_patterns", {})
    for key, blk in pp.items():
        tag = "BG-" + key.replace("_", "-")
        for e in blk.get("expectations", []):
            entries.append((tag, e))
        assertions += [_assertion(a, tag) for a in blk.get("assertions", [])]
    for case in bg.get("classification_cases", []):
        tag = "BG-" + case["id"].replace("_", "-")
        for e in case.get("expectations", []):
            entries.append((tag, e))
        assertions += [_assertion(a, tag) for a in case.get("assertions", [])]
    bge = bg.get("background_expectations", {})
    for e in bge.get("run_days", []):
        entries.append(("BG", e))
    assertions += [_assertion(a, "BG") for a in bge.get("assertions", [])]
    for hv in w.variants.get("honesty_variants", []):
        v_entries = [(None, e) for e in hv.get("run_days", [])]
        variants.append(Variant(id=hv["id"], kind="honesty", data_dir=None, condition=dict(hv.get("condition") or {}),
                                run_days=[rd for rd in _merge_run_days(v_entries, {}) if rd.absent or rd.items or rd.candidates],
                                assertions=[_assertion(a, None, hv["id"] if hv["id"] != "tasks_stale_builtin" else None) for a in hv.get("assertions", [])]))

    known = {i.source_id for i in items}
    run_days = _merge_run_days(entries, visible, known, problems)
    meta = Meta(world=w.name, anchor=tl.anchor, run_days=[26, 27, 28, 29, 30], seed=seed,
                generated_at=generated_at.isoformat(timespec="seconds"), counts=counts)
    return Manifest(meta=meta, items=items, contacts=_contacts(w), about_keys=merges, run_days=run_days,
                    assertions=assertions, variants=variants, sim_avery=sims, label_audit=LabelAudit())
