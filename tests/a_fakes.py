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

def _action(type_: str, target: str | None, brief: str) -> dict:
    return {"type": type_, "target": target, "brief": brief, "assumptions": [], "watch_trigger": None, "read_start": None}


def _finding(fid: str, cits: list[dict], **over) -> dict:
    base = {"finding_id": fid, "origin": "thread_reader", "needs_avery": "yes", "title": "Handle the thread", "kind": "other",
            "why": "fake why", "priority": "P2", "urgency": "this_week", "deadline": None, "stakes": "medium", "confidence": "high",
            "section": "pulse", "entities": [], "about": ["other:thread"], "citations": cits, "proposed_actions": [], "ambiguity": None,
            "contradictions": [], "freshness_caveat": None, "suspicious_instructions": []}
    base.update(over)
    return base


def fake_reader(user_text: str, *, bad_quote: bool = False) -> dict:
    """A ReaderOutput for the raw thread in the reader's user message. Planted for the code checks: every finding
    carries one invented quote (dropped), Sam gets a reply (→ message_person), Renee gets a P0 (→ P1, not earned),
    Marcus gets a second, needs_avery "no" finding (no candidate). bad_quote: every quote invented (finding dropped)."""
    raw = user_text.split("=== RAW THREAD", 1)[1]
    blocks = re.split(r"\n--- (?=msg:<)", raw)[1:]
    msgs = []
    for b in blocks:
        sid = b.split("\n", 1)[0].strip()
        frm = re.search(r"^from: .*?<([^>]+)>(.*)$", b, re.M)
        subj = re.search(r"^subject: (.*)$", b, re.M).group(1)
        msgs.append((sid, frm.group(1), "[Avery]" in frm.group(2).split("(")[0], subj))
    sender = next((a for _, a, me, _ in msgs if not me), msgs[0][1])
    sid, _, _, subj = msgs[-1]
    good = {"source_id": sid, "quote": "invented quote" if bad_quote else subj}
    cits = [good, {"source_id": sid, "quote": "a sentence nobody wrote"}]
    if "sam@" in sender:
        fs = [_finding("f1", cits, title="Sort out daycare pickup with Sam", kind="childcare change", priority="P0", urgency="today",
                       section="calendar_personal", about=["family:daycare"], stakes="high",
                       proposed_actions=[_action("reply", sender, "who takes pickup on Friday")])]
    elif "marcus@" in sender:
        fs = [_finding("f1", cits, title="Send Marcus the updated cap table", kind="overdue promise to lead investor", priority="P0",
                       urgency="today", section="urgent", about=["deal:series-a:cap-table"], stakes="high",
                       deadline={"raw": "tonight", "resolved": "2026-09-22T23:59:00-07:00"},
                       proposed_actions=[_action("task", "Send Marcus the updated cap table", "overdue since Tuesday night")]),
              _finding("f2", cits, needs_avery="no", title="Marcus's partnership meeting is Thursday", kind="context",
                       priority="P3", urgency="none", about=["deal:series-a"])]
    elif "renee" in sender:
        amb = {"type": "preference", "question": "Confirm Oct 6 or wait for Jordan?", "options": ["confirm", "wait"], "default": 1}
        fs = [_finding("f1", cits, title="Reply to Renee about the rollout date", kind="reference customer asking about a date",
                       priority="P0", urgency="today", section="urgent", entities=["Renee Tan"], about=["rollout:halberd"], ambiguity=amb,
                       proposed_actions=[_action("reply", sender, "confirm Oct 6"), _action("question", None, "confirm or wait?")])]
    else:
        fs = [_finding("f1", cits, proposed_actions=[_action("read", None, "skim it")])]
    return {"thread_summary": f"fake summary of {subj}", "findings": fs}


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
        elif name == "ReaderOutput":
            content = json.dumps(fake_reader(kw["messages"][1]["content"], bad_quote=self.bad_quote))
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
        elif name in ("SignatureFacts", "ContactClassification", "SweepOutput"):   # Track B's v2 spine and sweeps
            from b_fakes import fake_b_output
            content = json.dumps(fake_b_output(name, text))
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
