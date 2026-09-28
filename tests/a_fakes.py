"""Fake OpenRouter client for Track A tests: answers by output schema name, never touches the network."""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

from digest.config import load_models
from digest.llm import LLM, CostLog

PROFILE_JSON = {
    "person": "Avery Chen", "company": "Tessera", "timezone": "America/Los_Angeles",
    "contacts": [
        {"name": "Sam Park", "emails": [], "role_at_org": None, "category": "family", "subtype": "partner", "tier": "P0",
         "tier_condition": None, "rules": ["never_draft"], "notes": "anything from Sam is P0. Personal."},
        {"name": "Marcus Webb", "emails": [], "role_at_org": None, "category": "capital", "subtype": "lead_investor",
         "tier": "P0", "tier_condition": "during the raise", "rules": [], "notes": "P0 during the raise."},
        {"name": None, "emails": [], "role_at_org": {"role": "procurement lead", "orgs": ["Halberd Manufacturing", "Northstar Foods", "Veritas Components"]},
         "category": "customer", "subtype": "reference", "tier": "P1", "tier_condition": None, "rules": ["same_day_reply"], "notes": "reference customers"},
    ],
    "facts": [{"subject": "ARR", "value": "~$3.2M"}],
    "thresholds": {"investor_quiet_business_days": 3, "hiring_stall_days": 5, "recruiter_pattern": {"count": 3, "window_days": 7}},
    "blocks": [{"days": ["TUE", "THU"], "start": "09:00", "end": "11:00"}],
    "read_windows": ["06:15-06:45", "12:30-13:00", "evening"],
    "standing_topics": ["supply-chain visibility", "manufacturing", "inference costs", "Series A"],
    "judgment_rules": ["Quiet investor threads."], "digest_prefs": ["Newsletters. Even the good ones."],
    "tone": ["Short. Lowercase greetings or none at all."],
    "hard_rules": {"never_draft_for": ["Sam Park"], "no_newsletter_items": True, "recruiter_pattern_only": True,
                   "cite_everything": True, "flag_stale_email_hours": 24},
}

_SRC_RE = re.compile(r"^--- message \d+ · source_id: (msg:<[^>]+>)", re.M)
_SUBJ_RE = re.compile(r"^subject: (.*)$", re.M)
_DOC_RE = re.compile(r"^(THREAD|NOTE|TASK) (\S+)", re.M)
_ROUTER_RE = re.compile(r"^router guess: (\w+)", re.M)


def fake_extractor_output(prompt_text: str, *, bad_quote: bool = False) -> dict:
    """A minimal valid ExtractorOutput for the document in the prompt; quotes come from the document itself."""
    doc = prompt_text.split("=== DOCUMENT ===", 1)[1]
    kind, sid = _DOC_RE.search(doc).groups()
    empty = {"human_thread": None, "newsletter": None, "automated": None, "note": None, "task": None}
    if kind == "NOTE":
        return {"type": "note", **empty, "note": {
            "note_kind": "meeting_notes", "meeting_date": "2026-09-22", "attendees": ["Jordan Liu"], "summary": "standup",
            "about": ["rollout:halberd"], "decisions": [], "action_items": [], "agreements": [], "open_comments": [],
            "claims": [{"subject": "rollout_date", "value": "Oct 6", "as_of": None,
                        "evidence": {"source_id": f"{sid}#L4", "quote": "wrong quote" if bad_quote else "on track for Oct 6"}}],
            "stage_signals": [], "draft_of": None}}
    if kind == "TASK":
        return {"type": "task", **empty, "task": {"about": "report:board-update", "entities": []}}
    router = _ROUTER_RE.search(doc).group(1)
    msg_ids = _SRC_RE.findall(doc)
    subjects = _SUBJ_RE.findall(doc)
    last_id, last_subject = msg_ids[-1], subjects[-1]
    ev = {"source_id": last_id, "quote": "not in the source" if bad_quote else last_subject}
    if router == "newsletter":
        return {"type": "newsletter", **empty, "newsletter": {"publication": "Fake Brief", "issue_date": "2026-09-23", "items": [
            {"headline": "h", "summary": "s", "topics": ["inference costs"], "entities": [], "effective_date": None, "evidence": ev}]}}
    if router == "automated":
        return {"type": "automated", **empty, "automated": {"system": "DocuSign", "action_bearing": True, "action_kind": "signature",
                                                             "what": "sign", "deadline": None, "about": "offer:mei-tanaka", "link_present": True, "evidence": ev}}
    if router == "marketing":
        return {"type": "marketing", **empty}
    sent = re.findall(r"^sent: (\S+)", doc, re.M)[-1]
    frm = re.findall(r"^from: .*?<?([\w.+-]+@[\w.-]+)>?", doc, re.M)[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", last_subject.lower()).strip("-")[:30].rstrip("-") or "thread"
    return {"type": "human_thread", **empty, "human_thread": {
        "summary": "a thread", "about": [f"other:{slug}"], "domain": "work", "intent_primary": "ask", "intent_secondary": [],
        "ball": {"awaiting": "avery", "awaiting_who": None, "last_message_by": frm, "last_message_at": sent,
                 "closed_by_courtesy": False, "evidence": ev},
        "sender_observations": [], "asks": [{"from_email": frm, "to_avery": True, "kind": "information", "what": "answer",
                                              "deadline": None, "status": "open", "answered_by_message": None, "evidence": ev}],
        "commitments": [], "deferrals": [], "schedule_mentions": [], "stage_signals": [], "role_changes": [], "claims": [],
        "suspicious_instructions": []}}


TRIAGE_PLAN = {   # type → (include, section, priority, due_today, action type)
    "commitment_overdue": (True, "urgent", "P0", True, "task"), "commitment_due": (True, "urgent", "P1", True, "task"),
    "commitment_not_in_tasks": (True, "urgent", "P1", False, "task"), "reply_owed": (True, "urgent", "P1", True, "reply"),
    "quiet_thread": (True, "urgent", "P1", True, "reply"), "approval_pending": (True, "decisions", "P1", True, "approve"),
    "calendar_conflict:deep_work": (True, "calendar_personal", "P2", True, "calendar_response"),
    "calendar_conflict:family": (True, "calendar_personal", "P0", True, "message_person"),
    "calendar_conflict:double_book": (True, "calendar_personal", "P1", True, "decide"),
    "news_attachment": (True, "news", "P2", False, "read"), "task_due": (True, "urgent", "P1", True, "task"),
    "stale_source": (False, "pulse", "P3", False, None), "suspicious_content": (True, "pulse", "P0", False, "read"),
    "recruiter_pattern": (True, "pulse", "P2", False, "watch"), "hiring_stall": (True, "pulse", "P2", False, "forward_delegate"),
    "cadence_drop": (True, "pulse", "P2", False, "watch"), "contradiction": (True, "decisions", "P1", False, "decide"),
    "profile_drift": (True, "pulse", "P3", False, "profile_update"), "obligation_cadence": (True, "urgent", "P1", True, "task"),
    "declined_meeting": (True, "calendar_personal", "P2", False, "read"),
}


def fake_triage(prompt_text: str) -> dict:
    body = prompt_text.split("=== CANDIDATES ===", 1)[1].split("=== END CANDIDATES ===", 1)[0]
    pack = json.loads(body)
    results = []
    for c in pack["candidates"]:
        inc, sec, pri, due, act = TRIAGE_PLAN.get(c["type"], (True, "pulse", "P2", False, "read"))
        contacts = c.get("contacts") or []
        family = any(x.get("category") == "family" for x in contacts)
        target = None
        if act in ("reply", "message_person", "forward_delegate"):
            target = (contacts[0].get("names") or ["x"])[0] if contacts else None
            if family and act == "reply":
                act = "reply"   # the code must convert this to message_person (never_draft)
        elif act == "task":
            target = f"Do {c['about']}"
        elif act == "approve":
            target = c["facts"].get("system") or "the app"
        elif act == "calendar_response":
            target = c["facts"].get("uid")
        actions = [] if act is None else [{"type": act, "target": target, "brief": f"handle {c['about']}", "assumptions": [],
                                           "watch_trigger": None, "read_start": None}]
        amb = None
        if c["type"] == "hiring_stall":
            amb = {"type": "preference", "question": "Push the loop or hold?", "options": ["push", "hold"], "default": 1}
            actions.append({"type": "question", "target": None, "brief": "push or hold?", "assumptions": [], "watch_trigger": None, "read_start": None})
        cits = [dict(e) for e in c["evidence"][:1]] + [{"source_id": "msg:<invented>", "quote": "made up"}]
        results.append({"candidate_id": c["candidate_id"], "include": inc, "section": sec, "priority": pri, "due_today": due,
                        "confidence": "high", "why": f"fake why for {c['type']}", "citations": cits, "ambiguity": amb, "proposed_actions": actions})
    return {"results": results}


def fake_compose(prompt_text: str) -> dict:
    body = prompt_text.split("=== ITEMS ===", 1)[1].split("=== END ITEMS ===", 1)[0]
    items = json.loads(body)
    one = next((i["id"] for i in items if i["priority"] == "P0"), items[0]["id"] if items else None)
    sections = {s: [] for s in ("urgent", "decisions", "news", "pulse", "calendar_personal")}
    out_items = []
    for it in items:
        sections[it["section"]].append(it["id"])          # the one thing is repeated on purpose: code must remove it
        out_items.append({"id": it["id"], "what": f"Do {it['about']}", "why": it["why"], "final_actions": it["proposed_actions"] * 2})
    if out_items:
        out_items.append(dict(out_items[0]))               # duplicate entry on purpose
        out_items.append({"id": "i999", "what": "invented", "why": "invented", "final_actions": []})
    return {"one_thing_id": one, "sections": [{"name": k, "item_ids": v} for k, v in sections.items()], "items": out_items,
            "header_notes": ["fake compose"], "cut_ids": []}


def fake_draft(prompt_text: str, first_call: bool) -> dict:
    if first_call:
        return {"text": "hi, just wanted to confirm Oct 6 is on. it is. really. truly. Avery", "assumptions": ["on track per sprint note"]}
    return {"text": "renee, yes, Oct 6 is on. the cutover checklist is with your team.\nAvery", "assumptions": ["on track per sprint note"]}


def fake_customize(prompt_text: str) -> dict:
    text = prompt_text.split("=== CUSTOMIZE ===", 1)[1].split("=== END CUSTOMIZE ===", 1)[0].strip().lower()
    o = {"sections_order": ["urgent", "decisions", "news", "pulse", "calendar_personal"], "sections_exclude": [], "length_words": None,
         "focus": {"entities": [], "categories": [], "mode": "boost"}, "include_newsletters": False, "calendar_full_schedule": False,
         "tone": {"formality": "default"}, "horizon_days": 0, "compose_instructions": None, "materializer_instructions": None,
         "rejected": [], "not_understood": False}
    if "weekend" in text:
        o.update({"length_words": 100, "focus": {"entities": [], "categories": ["family"], "mode": "only"}, "compose_instructions": "P0 and family only"})
    elif "citation" in text:
        o["rejected"] = [{"instruction": "Skip the source citations.", "reason": "honesty rule: citations are locked"}]
    elif "formal" in text:
        o["tone"] = {"formality": "formal"}
    elif "newsletter" in text:
        o["include_newsletters"] = True
    elif "board" in text:
        o["compose_instructions"] = "Board meeting tomorrow; investors first; include metrics"
    else:
        o["not_understood"] = True
    return o


FAKE_BASELINE_MD = """# Daily Digest — Thursday, September 24, 2026

As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar ok · notes ok · tasks ok

## If there is one thing you must do right now

**Send the cap table to Marcus.** Promised Tuesday night. *[email: Marcus, Tue 16:42]*

---

## Urgent To-Do Today

- **Reply to Renee.** Rollout question. *[email: Renee, Tue 14:08]*
"""


def _json_after(text: str, marker: str):
    i = text.rindex(marker) + len(marker)
    return json.loads(text[i:].strip())


def fake_topic_groups(text: str) -> dict:
    """Test stand-in for the linker LLM: keys whose descriptions name the same deliverable (the fixture's cap table,
    Mei's offer) group; everything else stays apart. The real decision is the LLM's."""
    topics = _json_after(text, "TOPICS\n")
    groups = []
    for _kind, rows in topics.items():
        by_slug: dict[str, list[str]] = {}
        for r in rows:
            slug = r["key"].split(":", 1)[1].replace("captable", "cap-table")
            by_slug.setdefault(slug, []).append(r["key"])
        groups += [{"members": m, "reason": "same slug"} for m in by_slug.values() if len(m) > 1]
    return {"groups": groups}


def fake_links(text: str) -> dict:
    """Test stand-in: an option matches when it shares two or more meaningful words with the item."""
    qs = _json_after(text, "QUESTIONS\n")
    stop = {"the", "and", "for", "with", "from", "that", "this", "will", "send", "avery", "email", "to", "of", "a", "on", "in"}

    def words(s: str) -> set[str]:
        return {w.strip(".,:;()'\"").lower() for w in s.split() if len(w) > 2} - stop

    out = []
    for q in qs:
        iw = words(q["item"])
        strong = {w for w in iw if len(w) >= 5}
        out.append({"question_id": q["id"], "matches": [o["id"] for o in q["options"]
                                                        if len(iw & words(o["text"].replace(":", " ").replace("-", " "))) >= 2
                                                        or strong & words(o["text"].replace(":", " ").replace("-", " "))],
                    "reason": "shared words (test fake)"})
    return {"answers": out}


class FakeClient:
    def __init__(self, *, bad_quote: bool = False, profile_responses: list[str] | None = None, banned_first: bool = False):
        self.calls: list[dict] = []
        self.bad_quote = bad_quote
        self.banned_first = banned_first
        self.draft_calls = 0
        self.profile_responses = list(profile_responses) if profile_responses is not None else None
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        name = kw["response_format"]["json_schema"]["name"]
        text = kw["messages"][0]["content"]
        if name == "ProfileConfig":
            content = self.profile_responses.pop(0) if self.profile_responses else json.dumps(PROFILE_JSON)
        elif name == "ExtractorOutput":
            content = json.dumps(fake_extractor_output(text, bad_quote=self.bad_quote))
        elif name == "TriageBatch":
            content = json.dumps(fake_triage(text))
        elif name == "ComposeResult":
            content = json.dumps(fake_compose(text))
        elif name == "DraftOutput":
            self.draft_calls += 1
            retry = any(m["role"] == "user" for m in kw["messages"])
            content = json.dumps(fake_draft(text, first_call=self.draft_calls == 1 and not retry and self.banned_first))
        elif name == "DecideOutput":
            content = json.dumps({"options": [{"label": "API-focused", "consequence": "covers ingestion"}, {"label": "standard", "consequence": "generic"}],
                                  "recommendation": 1, "rationale": "your eval hinges on ingestion", "draft": None, "assumptions": []})
        elif name == "CustomizeOverrides":
            content = json.dumps(fake_customize(text))
        elif name == "BaselineDigest":
            content = json.dumps({"markdown": FAKE_BASELINE_MD})
        elif name == "TopicGroups":
            content = json.dumps(fake_topic_groups(text))
        elif name == "LinkBatch":
            content = json.dumps(fake_links(text))
        else:
            raise AssertionError(f"unexpected schema {name}")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, cost=0.0001)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


def fake_llm(tmp_path, **kw) -> LLM:
    return LLM(load_models(), cache_dir=tmp_path / "cache", cost_log=CostLog(tmp_path / "cost.jsonl"), client=FakeClient(**kw))


# ----------------------------------------------------------------------------- builders for compute tests (M4)
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from digest.ingest.loader import SourceStatus  # noqa: E402
from digest.normalize import NormalizedWorld  # noqa: E402
from digest.normalize.freshness import SourceFreshness  # noqa: E402
from digest.runs import parse_as_of  # noqa: E402
from digest.schemas import (  # noqa: E402
    Ask,
    Ball,
    Commitment,
    Evidence,
    Extraction,
    ExtractionMeta,
    HumanThread,
    NormalizedEvent,
    NormalizedMessage,
    NormalizedThread,
    ResolvedTime,
    SenderObservation,
)

TZ = ZoneInfo("America/Los_Angeles")
AVERY = "avery@tessera.io"


def msg(mid: str, sent: str, frm: str, to: list[str] | None = None, subject: str = "hi", body: str = "body text here",
        name: str = "", sig: str | None = None) -> NormalizedMessage:
    return NormalizedMessage(message_id=f"<{mid}>", sent_at=parse_as_of(sent), from_addr=frm, from_name=name,
                             to=to or [AVERY], subject=subject, body_new=body, signature_block=sig, is_from_avery=frm == AVERY)


def thread(*messages: NormalizedMessage, router: str = "human") -> NormalizedThread:
    ms = sorted(messages, key=lambda m: m.sent_at)
    return NormalizedThread(thread_id=f"thread:{ms[0].message_id.strip('<>')}", messages=ms, router_type=router)


def ev(msg_or_id, quote: str = "body text here") -> Evidence:
    sid = msg_or_id if isinstance(msg_or_id, str) else f"msg:{msg_or_id.message_id}"
    return Evidence(source_id=sid, quote=quote)


def rt(raw: str, iso: str | None, gran: str = "day") -> ResolvedTime:
    return ResolvedTime(raw=raw, resolved=parse_as_of(iso) if iso else None, granularity=gran, confidence="high")


def human(t: NormalizedThread, *, about: list[str], awaiting: str = "avery", intent: str = "ask", domain: str = "work",
          courtesy: bool = False, asks=(), commitments=(), senders=(), schedule=(), suspicious=(), stage=(), claims=(), roles=(),
          summary: str = "s") -> Extraction:
    last = t.messages[-1]
    p = HumanThread(summary=summary, about=about, domain=domain, intent_primary=intent, intent_secondary=[],
                    ball=Ball(awaiting=awaiting, awaiting_who=None, last_message_by=last.from_addr, last_message_at=last.sent_at,
                              closed_by_courtesy=courtesy, evidence=ev(last)),
                    sender_observations=list(senders), asks=list(asks), commitments=list(commitments), deferrals=[],
                    schedule_mentions=list(schedule), stage_signals=list(stage), role_changes=list(roles), claims=list(claims),
                    suspicious_instructions=list(suspicious))
    meta = ExtractionMeta(prompt_version="extractor@v1", model="fake", input_hash="x", extracted_at=parse_as_of("2026-09-24T06:00"))
    return Extraction(meta=meta, source_id=t.thread_id, type="human_thread", payload=p)


def sender(email: str, name: str, hint: str, subtype: str | None = None, title: str | None = None, org: str | None = None,
           m: NormalizedMessage | None = None) -> SenderObservation:
    return SenderObservation(email=email, name=name, title=title, org=org, relationship_hint=hint, subtype_hint=subtype,
                             introduced_by=None, evidence=[ev(m)] if m else [])


def ask(frm: str, what: str, m: NormalizedMessage, kind: str = "information", deadline: ResolvedTime | None = None,
        status: str = "open", to_avery: bool = True) -> Ask:
    return Ask(from_email=frm, to_avery=to_avery, kind=kind, what=what, deadline=deadline, status=status,
               answered_by_message=None, evidence=ev(m))


def commitment(what: str, about: str, m: NormalizedMessage, due: ResolvedTime | None = None, owner: str = "avery",
               to=(), status: str = "open", fulfills: str | None = None) -> Commitment:
    return Commitment(owner=owner, owner_email=AVERY if owner == "avery" else m.from_addr, to_whom=list(to), what=what, due=due,
                      status_in_thread=status, fulfilled_by=None, fulfills_hint=fulfills, about=about, evidence=ev(m))


def event(uid: str, title: str, start: str, end: str, organizer: str = AVERY, attendees: list[tuple[str, str]] | None = None,
          calendar: str = "work", partstat: str | None = None, created: str | None = None, domain: str | None = None) -> NormalizedEvent:
    from digest.schemas import Attendee
    att = [Attendee(email=e, partstat=p) for e, p in (attendees or [])]
    if partstat is None:
        partstat = "ORGANIZER" if organizer == AVERY else next((p for e, p in (attendees or []) if e == AVERY), "NEEDS-ACTION")
    return NormalizedEvent(uid=uid, calendar=calendar, title=title, start=parse_as_of(start), end=parse_as_of(end), organizer=organizer,
                           organizer_is_avery=organizer == AVERY, attendees=att, avery_partstat=partstat,
                           created=parse_as_of(created) if created else None,
                           domain=domain or ("personal" if calendar == "shared_family" else "work"))


def world(threads=(), events=(), tasks=(), notes=(), as_of: str = "2026-09-24T06:00", stale: dict | None = None) -> NormalizedWorld:
    at = parse_as_of(as_of)
    fresh = {}
    for k in ("email", "calendar", "notes", "tasks"):
        state = (stale or {}).get(k, "ok")
        fresh[k] = SourceFreshness(k, state, None, None)
    return NormalizedWorld(as_of=at, owner_email=AVERY, owner_emails={AVERY}, threads=list(threads), events=list(events),
                           notes=list(notes), tasks=list(tasks), tasks_mtime=None, freshness=fresh,
                           sources={k: SourceStatus(k, "ok") for k in fresh})


def at(iso: str) -> datetime:
    return parse_as_of(iso)
