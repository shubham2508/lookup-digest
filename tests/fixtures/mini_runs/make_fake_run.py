"""Writes the hand-made run artifacts the Track C tests score against tests/fixtures/mini/manifest.yaml.

    uv run python tests/fixtures/mini_runs/make_fake_run.py

One run, day 30 (as of 2026-09-24T06:00 PT), shaped by digest/schemas.py: v2 artifacts (PIVOT_SPEC §4), i.e.
findings.jsonl (every Finding + candidate_id, thread_id, rescued_by_safety_net) and the Finding → Candidate /
TriageResult mapping of digest/findings.py. Planted defects, one per stage, so every attribution path is exercised:

- spine        Dana resolved as cold_inbound (label: vendor).
- read         Sam's daycare thread: the reader said needs_avery "no" (label: P0) → P0 recall 2/3, gate fails;
               one citation dropped by the substring check (degradations.jsonl).
- sweep        Lumen's deep-work booking at P3 (label: P2), only calendar_response (label also expects decide);
               the news sweep attached nothing to the Halberd rollout (a news_attachment is expected).
- net          two rescues: the DocuSign approval and the pediatrician collision (no reader or sweep covered them).
- materialize  the Renee draft contains the banned phrase "just wanted to".
Everything else is right: one thing = cap table citing Marcus's thread, no draft to Sam, marketing absent.

The base run also keeps its v1 `extractions.jsonl` (committed, not written here): Track A/B tests read it until the
extractor is gone. The scorer ignores it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "2026-09-24T06-00"

MARCUS_1 = "msg:<20260922-1642.marcus@inflectionpoint.vc>"
AVERY_1 = "msg:<20260922-2130.avery@tessera.io>"
RENEE_1 = "msg:<20260922-1408.renee@halberd.com>"
NL_1 = "msg:<20260923-0700.brief@scbrief.example>"
DOCU_1 = "msg:<20260922-0915.dse@docusign.net>"
RIPPLE_1 = "msg:<20260921-1000.hello@mail.rippleboard.example>"
SAM_1 = "msg:<20260923-2110.sam@parkfamily.example>"
EV_LUMEN = "event:lumen-demo-20260924@lumenanalytics.example"
EV_PED = "event:wren-pediatrician-20260924@parkfamily.example"


def ev(src: str, quote: str) -> dict:
    return {"source_id": src, "quote": quote}


CONTACTS = [
    {"contact_id": "renee-tan", "names": ["Renee Tan"], "emails": ["renee.tan@halberd.com"], "org": "Halberd Manufacturing",
     "relationship": {"category": "customer", "subtype": "reference", "stage": "active", "source": "profile"}, "tier": "P1",
     "profile_rules": ["same_day_reply"]},
    {"contact_id": "marcus-webb", "names": ["Marcus Webb"], "emails": ["marcus@inflectionpoint.vc"],
     "relationship": {"category": "capital", "subtype": "lead_investor", "stage": "term_sheet", "source": "profile"}, "tier": "P0"},
    {"contact_id": "sam-park", "names": ["Sam Park"], "emails": ["sam@parkfamily.example"],
     "relationship": {"category": "family", "subtype": "partner", "stage": None, "source": "profile"}, "tier": "P0",
     "profile_rules": ["never_draft"]},
    {"contact_id": "dana-whitfield", "names": ["Dana Whitfield"], "emails": ["dana@lumenanalytics.example"],
     "relationship": {"category": "cold_inbound", "subtype": None, "stage": None, "source": "inferred"}, "tier": None},
]


def cand(cid, ctype, about, evidence, facts=None, **kw) -> dict:
    return {"candidate_id": cid, "type": ctype, "about": about, "entities": kw.get("entities", []), "facts": facts or {},
            "evidence": evidence, "context_refs": [], "source_dependencies": kw.get("deps", ["email"]),
            "freshness_cap": "none", "times_surfaced": kw.get("times", 0)}


# candidates are the findings that need Avery (digest/findings.py to_candidate): readers' and sweeps' kinds are free
# text, safety nets keep the v1 rule name; a needs_avery "no" finding (the daycare reader) makes no candidate
CANDIDATES = [
    cand("c1", "overdue promise to lead investor", "deal:series-a:captable", [ev(AVERY_1, "will send it tonight")],
         {"days_overdue": 1}, entities=["marcus-webb"]),
    cand("c2", "promise missing from tasks", "deal:series-a:cap-table", [ev(AVERY_1, "will send it tonight")], entities=["marcus-webb"]),
    cand("c3", "reference customer waiting on a date", "rollout:halberd:oct-6", [ev(RENEE_1, "still on")],
         {"hours_since_inbound": 40}, entities=["renee-tan"]),
    cand("c4", "approval_pending", "offer:mei-tanaka", [ev(DOCU_1, "Offer Letter")]),
    cand("c5", "deep-work block booked by a vendor", "meeting:lumen-demo", [ev(EV_LUMEN, "Lumen Analytics demo")],
         {"overlap_minutes": 30}, entities=["dana-whitfield"], deps=["calendar"]),
    cand("c6", "calendar_conflict:family", "family:pediatrician", [ev(EV_PED, "Wren - pediatrician 3:00pm")],
         {"overlap_minutes": 60}, entities=["sam-park"], deps=["calendar"]),
    cand("c7", "task due today", "report:q2-planning", [ev("task:2", "Review Q2 planning comments")], deps=["tasks"]),
]


def act(t, target, brief, assumptions=None, **kw) -> dict:
    return {"type": t, "target": target, "brief": brief, "assumptions": assumptions or [],
            "watch_trigger": kw.get("watch_trigger"), "read_start": kw.get("read_start")}


def tri(cid, include, section, priority, why, cites, actions, ambiguity=None, conf="high") -> dict:
    return {"candidate_id": cid, "include": include, "section": section, "priority": priority, "due_today": include,
            "confidence": conf, "why": why, "citations": cites, "ambiguity": ambiguity, "proposed_actions": actions}


A_TASK = act("task", "Send cap table to Marcus", "send the cap table v3 to Marcus by 11:00")
A_FWD = act("forward_delegate", "ben@wsgr.example", "ask Ben to send Marcus the latest cap table", ["v3 is the latest version"])
A_REPLY = act("reply", "renee.tan@halberd.com", "confirm Oct 6 is on", ["the sprint note says on track"])
A_Q = act("question", None, "is Oct 6 firm, or check with Jordan first?")
TRIAGE = [
    tri("c1", True, "urgent", "P0", "promised Tuesday night, now overdue; term sheet waits on it", [ev(AVERY_1, "will send it tonight")], [A_TASK, A_FWD]),
    tri("c2", True, "urgent", "P1", "promise not on the task list", [ev(AVERY_1, "will send it tonight")], [A_TASK]),
    tri("c3", True, "urgent", "P1", "reference customer asked Tuesday; same-day reply rule", [ev(RENEE_1, "still on")], [A_REPLY, A_Q],
        ambiguity={"type": "factual", "question": "Is Oct 6 firm?", "options": ["yes, confirm", "check with Jordan first"], "default": 1}),
    tri("c4", True, "decisions", "P1", "offer letter waiting in DocuSign since Tuesday", [ev(DOCU_1, "Offer Letter")],
        [act("approve", "DocuSign", "sign Mei's offer letter")]),
    tri("c5", True, "calendar_personal", "P3", "vendor booked over Thursday deep work", [ev(EV_LUMEN, "Lumen Analytics demo")],
        [act("calendar_response", "lumen-demo-20260924@lumenanalytics.example", "propose moving to 11:15")]),
    tri("c6", True, "calendar_personal", "P0", "Sam added the pediatrician at 3pm; overlaps your afternoon", [ev(EV_PED, "Wren - pediatrician 3:00pm")],
        [act("message_person", "sam@parkfamily.example", "ask Sam whether you are expected to take Wren")]),
    tri("c7", True, "pulse", "P2", "Q2 planning comments due today", [ev("task:2", "Review Q2 planning comments")], [A_TASK | {"target": "Review Q2 planning comments"}]),
]

THREAD_MARCUS = "thread:20260922-1642.marcus@inflectionpoint.vc"
THREAD_RENEE = "thread:20260922-1408.renee@halberd.com"
THREAD_SAM = "thread:20260923-2110.sam@parkfamily.example"


def finding(fid, origin, needs, title, kind, why, priority, section, about, cites, actions, cid, thread=None, *,
            rescued=False, urgency="today", ambiguity=None, entities=None, contradictions=None, suspicious=None) -> dict:
    """One findings.jsonl row (digest/findings.py finding_row): the Finding plus candidate_id, thread_id, rescued."""
    return {"finding_id": fid, "origin": origin, "needs_avery": needs, "title": title, "kind": kind, "why": why,
            "priority": priority, "urgency": urgency, "deadline": None, "stakes": "high" if priority == "P0" else "medium",
            "confidence": "high", "section": section, "entities": entities or [], "about": about, "citations": cites,
            "proposed_actions": actions, "ambiguity": ambiguity, "contradictions": contradictions or [],
            "freshness_caveat": None, "suspicious_instructions": suspicious or [],
            "candidate_id": cid, "thread_id": thread, "rescued_by_safety_net": rescued}


FINDINGS = [
    finding("f1", "thread_reader", "yes", "Send the updated cap table to Marcus", "overdue promise to lead investor",
            "You promised it Tuesday night; the term sheet waits on it.", "P0", "urgent", ["deal:series-a:captable"],
            [ev(AVERY_1, "will send it tonight")], [A_TASK, A_FWD], "c1", THREAD_MARCUS, entities=["marcus-webb"]),
    finding("f2", "notes_tasks_sweep", "yes", "Add the cap table promise to your tasks", "promise missing from tasks",
            "The promise to Marcus is not on the task list.", "P1", "urgent", ["deal:series-a:cap-table"],
            [ev(AVERY_1, "will send it tonight")], [A_TASK], "c2", entities=["marcus-webb"]),
    finding("f3", "thread_reader", "yes", "Reply to Renee about the Oct 6 rollout", "reference customer waiting on a date",
            "Renee asked Tuesday whether Oct 6 is still on; same-day reply rule.", "P1", "urgent", ["rollout:halberd:oct-6"],
            [ev(RENEE_1, "still on")], [A_REPLY, A_Q], "c3", THREAD_RENEE, ambiguity=TRIAGE[2]["ambiguity"],
            entities=["renee-tan"]),
    finding("f4", "safety_net", "yes", "Sign Mei Tanaka's offer letter", "approval_pending",
            "DocuSign offer letter waiting since Tuesday 09:15; no reader covers automated mail.", "P1", "decisions",
            ["offer:mei-tanaka"], [ev(DOCU_1, "Offer Letter")], [act("approve", "DocuSign", "sign Mei's offer letter")], "c4",
            rescued=True),
    finding("f5", "calendar_sweep", "yes", "Move the Lumen demo off your deep-work block", "deep-work block booked by a vendor",
            "Lumen's rep booked 10:30 inside Thursday 09:00-11:00.", "P3", "calendar_personal", ["meeting:lumen-demo"],
            [ev(EV_LUMEN, "Lumen Analytics demo")],
            [act("calendar_response", "lumen-demo-20260924@lumenanalytics.example", "propose moving to 11:15")], "c5",
            entities=["dana-whitfield"]),
    finding("f6", "safety_net", "yes", "Check with Sam about Wren's 3pm pediatrician", "calendar_conflict:family",
            "Shared-family event at 15:00 overlaps your afternoon (60 min).", "P0", "calendar_personal", ["family:pediatrician"],
            [ev(EV_PED, "Wren - pediatrician 3:00pm")],
            [act("message_person", "sam@parkfamily.example", "ask Sam whether you are expected to take Wren")], "c6",
            rescued=True, entities=["sam-park"]),
    finding("f7", "notes_tasks_sweep", "yes", "Review the Q2 planning comments", "task due today", "tasks.md marks it due today.",
            "P2", "pulse", ["report:q2-planning"], [ev("task:2", "Review Q2 planning comments")],
            [A_TASK | {"target": "Review Q2 planning comments"}], "c7"),
    finding("f8", "thread_reader", "no", "Note Friday's daycare closure", "family logistics FYI", "Sam's note reads as FYI.",
            "P2", "calendar_personal", ["family:daycare"], [ev(SAM_1, "Can you take the afternoon")], [], None, THREAD_SAM,
            urgency="this_week", entities=["sam-park"]),
]

REDUCE = {
    "items": [
        {"id": "i1", "about": "deal:series-a:cap-table", "candidate_ids": ["c1", "c2"], "priority": "P0", "section": "urgent",
         "due_today": True, "confidence": "high", "citations": [ev(MARCUS_1, "I need the updated cap table"), ev(AVERY_1, "will send it tonight")],
         "proposed_actions": [A_TASK, A_FWD], "ambiguity": None, "entities": ["marcus-webb"]},
        {"id": "i2", "about": "rollout:halberd:oct-6", "candidate_ids": ["c3"], "priority": "P1", "section": "urgent", "due_today": True,
         "confidence": "high", "citations": [ev(RENEE_1, "still on")], "proposed_actions": [A_REPLY, A_Q],
         "ambiguity": TRIAGE[2]["ambiguity"], "entities": ["renee-tan"]},
        {"id": "i3", "about": "offer:mei-tanaka", "candidate_ids": ["c4"], "priority": "P1", "section": "decisions", "due_today": True,
         "confidence": "high", "citations": [ev(DOCU_1, "Offer Letter")], "proposed_actions": TRIAGE[3]["proposed_actions"], "ambiguity": None},
        {"id": "i4", "about": "family:pediatrician", "candidate_ids": ["c6"], "priority": "P0", "section": "calendar_personal",
         "due_today": True, "confidence": "high", "citations": [ev(EV_PED, "Wren - pediatrician 3:00pm"), ev(SAM_1, "pediatrician")],
         "proposed_actions": TRIAGE[5]["proposed_actions"], "ambiguity": None, "entities": ["sam-park"]},
        {"id": "i5", "about": "meeting:lumen-demo", "candidate_ids": ["c5"], "priority": "P3", "section": "calendar_personal",
         "due_today": True, "confidence": "high", "citations": [ev(EV_LUMEN, "Lumen Analytics demo")],
         "proposed_actions": TRIAGE[4]["proposed_actions"], "ambiguity": None, "entities": ["dana-whitfield"]},
        {"id": "i6", "about": "report:q2-planning", "candidate_ids": ["c7"], "priority": "P2", "section": "pulse", "due_today": True,
         "confidence": "medium", "citations": [ev("task:2", "Review Q2 planning comments")], "proposed_actions": TRIAGE[6]["proposed_actions"],
         "ambiguity": None},
    ],
    "overflow": [],
    "about_merges": [{"canonical": "deal:series-a:cap-table", "merged": ["deal:series-a:captable"]}],
}

COMPOSE = {
    "one_thing_id": "i1",
    "sections": [
        {"name": "urgent", "item_ids": ["i2"]},
        {"name": "decisions", "item_ids": ["i3"]},
        {"name": "news", "item_ids": []},
        {"name": "pulse", "item_ids": ["i6"]},
        {"name": "calendar_personal", "item_ids": ["i4", "i5"]},
    ],
    "items": [
        {"id": "i1", "what": "Send the updated cap table to Marcus Webb before 11:00", "why": "You promised Tuesday night; the term sheet waits on it.",
         "final_actions": [A_TASK, A_FWD]},
        {"id": "i2", "what": "Reply to Renee Tan at Halberd", "why": "She asked Tuesday whether Oct 6 is still on; same-day customer.",
         "final_actions": [A_REPLY, A_Q]},
        {"id": "i3", "what": "Sign Mei Tanaka's offer letter", "why": "Waiting in DocuSign since Tuesday 09:15.",
         "final_actions": TRIAGE[3]["proposed_actions"]},
        {"id": "i4", "what": "Check with Sam about Wren's 3pm pediatrician", "why": "Sam added it last night; it overlaps your afternoon.",
         "final_actions": TRIAGE[5]["proposed_actions"]},
        {"id": "i5", "what": "Lumen demo at 10:30 sits on your deep-work block", "why": "Their rep booked over Thursday 09:00-11:00.",
         "final_actions": TRIAGE[4]["proposed_actions"]},
        {"id": "i6", "what": "Review the Q2 planning comments", "why": "Task due today.", "final_actions": TRIAGE[6]["proposed_actions"]},
    ],
    "header_notes": [],
    "cut_ids": [],
}

ACTIONS = [
    {"item_id": "i1", "type": "task", "target": "Send cap table to Marcus", "recipient_name": None, "recipient_category": None,
     "brief": A_TASK["brief"], "brief_assumptions": [], "text": "☐ Send cap table to Marcus — due 11:00 today", "draft": None,
     "assumptions": [], "evidence": [ev(AVERY_1, "will send it tonight")]},
    {"item_id": "i1", "type": "forward_delegate", "target": "ben@wsgr.example", "recipient_name": "Ben Schaffer",
     "recipient_category": "legal_gov", "brief": A_FWD["brief"], "brief_assumptions": A_FWD["assumptions"],
     "text": "↳ Forward to Ben with:", "draft": "ben, can you send Marcus the cap table v3 this morning? thanks.\nAvery",
     "assumptions": ["v3 is the latest version"], "evidence": [ev(MARCUS_1, "I need the updated cap table")]},
    {"item_id": "i2", "type": "reply", "target": "renee.tan@halberd.com", "recipient_name": "Renee Tan", "recipient_category": "customer",
     "brief": A_REPLY["brief"], "brief_assumptions": A_REPLY["assumptions"], "text": "↳ Draft to Renee:",
     "draft": "renee, just wanted to confirm Oct 6 is still on. the cutover checklist is with your team.\nAvery",
     "assumptions": ["the sprint note says on track"], "evidence": [ev(RENEE_1, "still on")]},
    {"item_id": "i2", "type": "question", "target": None, "recipient_name": None, "recipient_category": None, "brief": A_Q["brief"],
     "brief_assumptions": [], "text": "Q1 · Is Oct 6 firm? (1) yes, confirm (2) check with Jordan first", "draft": None, "assumptions": [], "evidence": []},
    {"item_id": "i3", "type": "approve", "target": "DocuSign", "recipient_name": None, "recipient_category": None, "brief": "sign",
     "brief_assumptions": [], "text": "↳ Approve in DocuSign (~1 min).", "draft": None, "assumptions": [], "evidence": [ev(DOCU_1, "Offer Letter")]},
    {"item_id": "i4", "type": "message_person", "target": "sam@parkfamily.example", "recipient_name": "Sam Park", "recipient_category": "family",
     "brief": "ask Sam", "brief_assumptions": [], "text": "↳ Message Sam about the 3pm pediatrician. No draft (Sam).", "draft": None,
     "assumptions": [], "evidence": [ev(EV_PED, "Wren - pediatrician 3:00pm")]},
    {"item_id": "i5", "type": "calendar_response", "target": "lumen-demo-20260924@lumenanalytics.example", "recipient_name": "Dana Whitfield",
     "recipient_category": "cold_inbound", "brief": "propose 11:15", "brief_assumptions": [], "text": "↳ Propose: move to 11:15.",
     "draft": None, "assumptions": [], "evidence": [ev(EV_LUMEN, "Lumen Analytics demo")]},
    {"item_id": "i6", "type": "task", "target": "Review Q2 planning comments", "recipient_name": None, "recipient_category": None,
     "brief": "review", "brief_assumptions": [], "text": "☐ Review Q2 planning comments — due today", "draft": None,
     "assumptions": [], "evidence": []},
]

VERIFY = {"violations": [], "stats": {"budget": 350, "header_present": True, "items": 6, "items_cited": 6,
                                      "citations_total": 9, "citations_resolved": 9}}

DIGEST = """# Daily Digest — Thursday, September 24, 2026

As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar ok · notes ok · tasks ok

## If there is one thing you must do right now

**Send the updated cap table to Marcus Webb before 11:00.** You promised Tuesday night; the term sheet waits on it. *[email: Marcus, Tue 16:42] [email: Avery, Tue 21:30]*
  ☐ Send cap table to Marcus — due 11:00 today
  ↳ Forward to Ben with: "ben, can you send Marcus the cap table v3 this morning? thanks. Avery"
  Assumptions: v3 is the latest version

---

## Urgent To-Do Today

- **Reply to Renee Tan at Halberd.** She asked Tuesday whether Oct 6 is still on; same-day customer. *[email: Renee, Tue 14:08]*
  ↳ Draft to Renee: "renee, just wanted to confirm Oct 6 is still on. the cutover checklist is with your team. Avery"
  Assumptions: the sprint note says on track
  Q1 · Is Oct 6 firm? (1) yes, confirm (2) check with Jordan first. Default if unanswered: 1 → digest answer Q1 1

---

## Decisions & Approvals

- **Sign Mei Tanaka's offer letter.** Waiting in DocuSign since Tuesday 09:15. *[email: DocuSign, Tue 09:15]*
  ↳ Approve in DocuSign (~1 min).

---

## AI Industry News

Nothing today that touches your open items.

---

## Team & Product Pulse

- **Review the Q2 planning comments.** Task due today. *[task: Review Q2 planning comments]*
  ☐ Review Q2 planning comments — due today

---

## Calendar & Personal

- **Check with Sam about Wren's 3pm pediatrician.** Sam added it last night; it overlaps your afternoon. *[cal: shared, added Wed 21:04] [email: Sam, Wed 21:10]*
  ↳ Message Sam about the 3pm pediatrician. No draft (Sam).
- **Lumen demo at 10:30 sits on your deep-work block.** Their rep booked over Thursday 09:00-11:00. *[cal: work, Lumen Analytics demo]*
  ↳ Propose: move to 11:15.

2 other meetings, nothing to act on.
"""

COST = {"calls": 14, "cached": 0, "prompt_tokens": 52000, "completion_tokens": 9100, "cost_usd": 0.0123,
        "cost_unknown_calls": 0, "by_role": {}}
RUN = {"run_id": "tests/fixtures/mini/2026-09-24T06-00", "world": "tests/fixtures/mini", "as_of": "2026-09-24T06:00:00-07:00",
       "variant": None, "customize": None, "timings_s": {}, "wall_s": 1.0, "cost_usd": 0.0123, "llm_calls": 14,
       "llm_cached": 0, "degradations": 1}
DEGRADATIONS = [{"stage": "read", "item": THREAD_RENEE, "reason": "citation_invalid",
                 "why": "quote not a substring of the source", "path": "findings[0].citations[1]"}]


def validate() -> None:
    """The fake artifacts must satisfy the product's own contracts."""
    from digest.schemas import (
        Candidate,
        ComposeResult,
        Contact,
        Finding,
        MaterializedAction,
        ReduceResult,
        TriageResult,
        VerifyResult,
    )

    for r in FINDINGS:
        Finding.model_validate({k: v for k, v in r.items() if k not in ("candidate_id", "thread_id", "rescued_by_safety_net")})
    for r in CONTACTS:
        Contact.model_validate(r)
    for r in CANDIDATES:
        Candidate.model_validate(r)
    for r in TRIAGE:
        TriageResult.model_validate(r)
    ComposeResult.model_validate(COMPOSE)
    ReduceResult.model_validate(REDUCE)
    for r in ACTIONS:
        MaterializedAction.model_validate(r)
    VerifyResult.model_validate(VERIFY)


def write_run(out: Path, b: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)

    def jl(name: str, rows: list[dict]) -> None:
        (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def js(name: str, obj) -> None:
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for name, key in (("findings.jsonl", "findings"), ("candidates.jsonl", "candidates"), ("triage.jsonl", "triage"),
                      ("actions.jsonl", "actions"), ("cost.jsonl", "cost_log"), ("degradations.jsonl", "degradations")):
        if key in b:
            jl(name, b[key])
    for name, key in (("contacts.json", "contacts"), ("reduce.json", "reduce"), ("compose.json", "compose"),
                      ("verify.json", "verify"), ("cost.json", "cost"), ("run.json", "run")):
        if key in b:
            js(name, b[key])
    (out / "digest.md").write_text(b["digest"], encoding="utf-8")


def base_bundle() -> dict:
    return copy.deepcopy({
        "findings": FINDINGS, "contacts": CONTACTS, "candidates": CANDIDATES, "triage": TRIAGE, "reduce": REDUCE,
        "compose": COMPOSE, "actions": ACTIONS, "verify": VERIFY, "digest": DIGEST, "cost": COST, "cost_log": [],
        "run": RUN, "degradations": DEGRADATIONS})


# ----------------------------------------------------------------------------- condition runs (M7, M8)
SECTION_TITLES = {"urgent": "Urgent To-Do Today", "decisions": "Decisions & Approvals", "news": "AI Industry News",
                  "pulse": "Team & Product Pulse", "calendar_personal": "Calendar & Personal"}
CITE = {MARCUS_1: "[email: Marcus, Tue 16:42]", AVERY_1: "[email: Avery, Tue 21:30]", RENEE_1: "[email: Renee, Tue 14:08]",
        DOCU_1: "[email: DocuSign, Tue 09:15]", SAM_1: "[email: Sam, Wed 21:10]", NL_1: "[email: The Supply Chain Brief, Wed 07:00]",
        RIPPLE_1: "[email: Rippleboard, Mon 10:00]", EV_PED: "[cal: shared, added Wed 21:04]", EV_LUMEN: "[cal: work, Lumen Analytics demo]",
        "task:2": "[task: Review Q2 planning comments]"}


def render(b: dict, header: str) -> str:
    """architecture §9 rendering of a bundle (the base digest.md above is hand-written; derived runs use this)."""
    red = {it["id"]: it for it in b["reduce"]["items"]}
    comp = {it["id"]: it for it in b["compose"]["items"]}
    acts: dict[str, list[dict]] = {}
    for a in b["actions"]:
        acts.setdefault(a["item_id"], []).append(a)

    def item(iid: str, bullet: bool) -> list[str]:
        c, r = comp[iid], red[iid]
        cites = " ".join(dict.fromkeys(CITE.get(e["source_id"], "") for e in r["citations"])).strip()
        line = f"{'- ' if bullet else ''}**{c['what']}.** {c['why']} *{cites}*"
        out = [line]
        for a in acts.get(iid, []):
            text = a["text"]
            if a.get("draft"):
                text += ' "' + a["draft"].replace("\n", " ") + '"'
            out.append("  " + text)
            if a.get("assumptions"):
                out.append("  Assumptions: " + "; ".join(a["assumptions"]))
        return out

    md = ["# Daily Digest — Thursday, September 24, 2026", "", header, ""]
    one = b["compose"].get("one_thing_id")
    if one:
        md += ["## If there is one thing you must do right now", "", *item(one, False), "", "---", ""]
    for blk in b["compose"]["sections"]:
        ids = [i for i in blk["item_ids"] if i != one]
        if not ids and blk["name"] != "news":
            continue
        md += [f"## {SECTION_TITLES[blk['name']]}", ""]
        md += [x for i in ids for x in item(i, True)] or ["Nothing today that touches your open items."]
        md += ["", "---", ""]
    if b["compose"].get("cut_ids"):
        md += [f"## Also pending ({len(b['compose']['cut_ids'])})", ""]
        md += [f"- {comp[i]['what']}" for i in b["compose"]["cut_ids"]] + [""]
    return "\n".join(md)


def _drop(b: dict, *iids: str) -> None:
    b["compose"]["sections"] = [dict(blk, item_ids=[i for i in blk["item_ids"] if i not in iids]) for blk in b["compose"]["sections"]]
    b["compose"]["items"] = [c for c in b["compose"]["items"] if c["id"] not in iids]
    b["reduce"]["items"] = [r for r in b["reduce"]["items"] if r["id"] not in iids]
    b["actions"] = [a for a in b["actions"] if a["item_id"] not in iids]


def _add_item(b: dict, iid: str, about: str, cand_type: str, section: str, priority: str, what: str, why: str,
              cites: list[dict], actions: list[dict] | None = None) -> None:
    cid = f"c-{iid}"
    b["candidates"].append(cand(cid, cand_type, about, cites))
    origin = "news_sweep" if cand_type == "news_attachment" else "notes_tasks_sweep"
    b["findings"].append(finding(f"f-{iid}", origin, "yes", what, cand_type, why, priority, section, [about], cites,
                                 [act(a["type"], a.get("target"), "b") for a in actions or []], cid,
                                 contradictions=[why] if cand_type == "contradiction" else None))
    b["triage"].append(tri(cid, True, section, priority, why, cites, [act(a["type"], a.get("target"), "b") for a in actions or []]))
    b["reduce"]["items"].append({"id": iid, "about": about, "candidate_ids": [cid], "candidate_types": [cand_type],
                                 "priority": priority, "section": section, "confidence": "high", "citations": cites,
                                 "proposed_actions": [], "why": why})
    b["compose"]["items"].append({"id": iid, "what": what, "why": why, "final_actions": []})
    for blk in b["compose"]["sections"]:
        if blk["name"] == section:
            blk["item_ids"].append(iid)
    for a in actions or []:
        b["actions"].append({"item_id": iid, "brief": "b", "brief_assumptions": [], "assumptions": [], "evidence": cites, **a})


def _set_draft(b: dict, item_id: str, draft: str) -> None:
    for a in b["actions"]:
        if a["item_id"] == item_id and a.get("draft"):
            a["draft"] = draft


HEADER = "As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar ok · notes ok · tasks ok"


def conditions() -> dict[str, dict]:
    out: dict[str, dict] = {}

    # honesty: stale_inbox — header says so; the overdue promise carries the qualifier, confidence capped
    b = base_bundle()
    for r in b["reduce"]["items"]:
        if r["id"] == "i1":
            r["confidence"] = "medium"
            r["why"] = "promised Tuesday night; may be a sync gap"
    for c in b["compose"]["items"]:
        if c["id"] == "i1":
            c["why"] = "You promised Tuesday night; nothing sent since, but this may be a sync gap."
    h = "As of Thu 06:00 PT · inbox 30h old (last synced Tue 23:59): may be a sync gap · calendar ok · notes ok · tasks ok"
    b["digest"], b["run"] = render(b, h), {**RUN, "variant": "stale_inbox", "suffix": "stale_inbox"}
    out["stale_inbox"] = b

    # honesty: no_notes — header says so; PLANTED FAILURE: the Renee draft still asserts "on track" unhedged
    b = base_bundle()
    _set_draft(b, "i2", "renee, yes, Oct 6 is on track.\nAvery")
    _drop(b, "i6")
    b["digest"] = render(b, "As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar ok · notes unavailable · tasks ok")
    out["no_notes"] = b

    # honesty: corrupt_ics — header says so; no calendar-conflict candidates or items
    b = base_bundle()
    b["candidates"] = [c for c in b["candidates"] if c["candidate_id"] not in ("c5", "c6")]
    b["triage"] = [t for t in b["triage"] if t["candidate_id"] not in ("c5", "c6")]
    b["findings"] = [f for f in b["findings"] if f["candidate_id"] not in ("c5", "c6")]
    _drop(b, "i4", "i5")
    b["digest"] = render(b, "As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar unreadable, calendar checks skipped · notes ok · tasks ok")
    out["corrupt_ics"] = b

    # customize: board_prep — capital first (the cap table), ARR drift surfaced, Sam's conflict still present
    b = base_bundle()
    _add_item(b, "i7", "report:arr", "contradiction", "decisions", "P1", "Reconcile ARR before the board meeting",
              "profile says $3.2M; the finance sync says $3.4M.", [ev(MARCUS_1, "final numbers")])
    b["digest"] = render(b, HEADER + " · customize: board prep (capital first, metrics)")
    out["customize-board_prep"] = b

    # customize: weekend — P0 and family only, under 100 words
    b = base_bundle()
    _drop(b, "i2", "i3", "i5", "i6")
    b["compose"]["sections"] = [blk for blk in b["compose"]["sections"] if blk["name"] != "news"]
    b["digest"] = render(b, HEADER + " · customize: weekend mode (P0 and family only)")
    out["customize-weekend"] = b

    # customize: newsletters — a cited newsletter item is allowed
    b = base_bundle()
    _add_item(b, "i8", "rollout:halberd:mx-summit", "news_attachment", "news", "P2", "Halberd presented at MX Summit",
              "their case study did not name Tessera; worth a word with Renee.", [ev(NL_1, "case studies")])
    b["digest"] = render(b, HEADER + " · customize: newsletters included")
    out["customize-newsletters"] = b

    # customize: no_citations — citations stay, the header notes the rejected instruction
    b = base_bundle()
    b["compose"]["header_notes"] = ["ignored: skip the source citations (citations are required)"]
    b["digest"] = render(b, HEADER + " · ignored: skip the source citations (citations are required)")
    out["customize-no_citations"] = b

    # customize: formal — drafts shift tone; still no draft to Sam
    b = base_bundle()
    _set_draft(b, "i2", "Dear Renee,\nI am writing to confirm that the October 6 rollout remains on schedule.\nBest regards,\nAvery")
    for a in b["actions"]:
        if a["item_id"] == "i1" and a.get("draft"):
            a["draft"] = "Dear Ben,\nCould you please send Marcus the cap table v3 this morning?\nBest regards,\nAvery"
    b["digest"] = render(b, HEADER + " · customize: formal tone for drafts")
    out["customize-formal"] = b

    # customize: garbage — default digest, header says the file was not understood
    b = base_bundle()
    b["compose"]["header_notes"] = ["customize file not understood; default digest"]
    b["digest"] = render(b, HEADER + " · customize file not understood; default digest")
    out["customize-garbage"] = b

    # baseline (eval.md §8): markdown only. PLANTED: surfaces the Rippleboard marketing mail, picks the wrong one
    # thing, drafts a reply to Sam, and misses the pediatrician conflict
    out["baseline"] = {
        "digest": BASELINE_DIGEST, "cost": {**COST, "cost_usd": 0.0451, "calls": 1},
        "run": {**RUN, "baseline": True, "suffix": "baseline", "cost_usd": 0.0451, "llm_calls": 1}}
    return out


BASELINE_DIGEST = """# Daily Digest — Thursday, September 24, 2026

As of Thu 06:00 PT

## If there is one thing you must do right now

**Reply to Renee Tan about the Oct 6 rollout.** She asked Tuesday and is a reference customer. *[email: Renee, Tue 14:08]*
  ↳ Draft to Renee: "Hi Renee! Just wanted to confirm everything is on track for Oct 6. Let me know if you need anything else from us!"

## Urgent To-Do Today

- **Send Marcus the updated cap table.** You said you'd send it Tuesday night. *[email: Marcus, Tue 16:42]*
- **Sort out Friday daycare with Sam.** Bright Steps is closed Friday afternoon. *[email: Sam, Wed 21:10]*
  ↳ Draft to Sam: "I can take the afternoon, no need to ask your parents."

## Decisions & Approvals

- **Sign Mei Tanaka's offer letter in DocuSign.** Pending since Tuesday. *[email: DocuSign, Tue 09:15]*

## AI Industry News

- **Rippleboard launched one-click expense approvals.** Could save the finance team time. *[email: Rippleboard, Mon 10:00]*
"""


def main() -> None:
    validate()
    write_run(OUT, base_bundle())
    (OUT / "suggested_tasks.md").write_text("- [ ] Send cap table to Marcus (due: 2026-09-24)\n", encoding="utf-8")
    for suffix, bundle in conditions().items():
        write_run(OUT.parent / f"{OUT.name}_{suffix}", bundle)


if __name__ == "__main__":
    main()
