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
    return {"type": "human_thread", **empty, "human_thread": {
        "summary": "a thread", "about": ["other:thread"], "domain": "work", "intent_primary": "ask", "intent_secondary": [],
        "ball": {"awaiting": "avery", "awaiting_who": None, "last_message_by": frm, "last_message_at": sent,
                 "closed_by_courtesy": False, "evidence": ev},
        "sender_observations": [], "asks": [{"from_email": frm, "to_avery": True, "kind": "information", "what": "answer",
                                              "deadline": None, "status": "open", "answered_by_message": None, "evidence": ev}],
        "commitments": [], "deferrals": [], "schedule_mentions": [], "stage_signals": [], "role_changes": [], "claims": [],
        "suspicious_instructions": []}}


class FakeClient:
    def __init__(self, *, bad_quote: bool = False, profile_responses: list[str] | None = None):
        self.calls: list[dict] = []
        self.bad_quote = bad_quote
        self.profile_responses = list(profile_responses) if profile_responses is not None else None
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        name = kw["response_format"]["json_schema"]["name"]
        if name == "ProfileConfig":
            content = self.profile_responses.pop(0) if self.profile_responses else json.dumps(PROFILE_JSON)
        elif name == "ExtractorOutput":
            content = json.dumps(fake_extractor_output(kw["messages"][0]["content"], bad_quote=self.bad_quote))
        else:
            raise AssertionError(f"unexpected schema {name}")
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, cost=0.0001)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)


def fake_llm(tmp_path, **kw) -> LLM:
    return LLM(load_models(), cache_dir=tmp_path / "cache", cost_log=CostLog(tmp_path / "cost.jsonl"), client=FakeClient(**kw))
