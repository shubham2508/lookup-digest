"""Fake LLM answers for Track B's v2 schemas (SignatureFacts, ContactClassification, SweepOutput), deterministic and
offline. a_fakes.FakeClient routes these schema names here, so every test that builds contacts through the fake client
gets plausible answers instead of a degraded spine. The real decisions are the LLM's; these only read the prompt text."""
from __future__ import annotations

import json
import re

_FROM = re.compile(r"^From: (?:(.+?) )?<?([\w.+-]+@[\w.-]+)>?$", re.M)


def finding(fid: str, title: str, cite: tuple[str, str], *, kind: str = "fake", priority: str = "P2", section: str = "pulse",
            needs: str = "yes", entities: list[str] | None = None, about: list[str] | None = None, actions: list[dict] | None = None,
            suspicious: list[dict] | None = None) -> dict:
    return {"finding_id": fid, "origin": "calendar_sweep", "needs_avery": needs, "title": title, "kind": kind,
            "why": f"fake why: {title}", "priority": priority, "urgency": "today", "deadline": None, "stakes": "medium",
            "confidence": "high", "section": section, "entities": entities or [], "about": about or [],
            "citations": [{"source_id": cite[0], "quote": cite[1]}], "proposed_actions": actions or [], "ambiguity": None,
            "contradictions": [], "freshness_caveat": None, "suspicious_instructions": suspicious or []}


def fake_signature(text: str) -> dict:
    """Name from the From header; title and org from a 'Name | Title | Org', 'Title | Org' or 'Title, Org' line."""
    m = _FROM.search(text)
    name, email = (m.group(1) or None, m.group(2)) if m else (None, "unknown")
    title = org = quote = None
    for line in (ln.strip() for ln in text.split("[signature")[-1].splitlines()[1:]):
        if not line or line == "--":
            continue
        parts = [p.strip() for p in line.split("|")] if "|" in line else [p.strip() for p in line.split(",", 1)] if "," in line else []
        if len(parts) == 3:
            _n, title, org = parts
        elif len(parts) == 2 and (not name or parts[0] != name):
            title, org = parts
        if title:
            quote = line
            break
    return {"name": name, "title": title, "org": org,
            "evidence": {"source_id": f"sig:{email}", "quote": quote} if quote else None}


def fake_classification(text: str) -> dict:
    card = json.loads(text.split("CONTACT RECORD (code-computed)\n", 1)[1].split("\n\nPROFILE RULES", 1)[0])
    sig = card.get("signature") or {}
    title, email = (sig.get("title") or "").lower(), card["email"]
    hint = card.get("same_domain_as_profile_contacts") or []
    cat, sub, stage = "unresolved", None, None
    if hint:
        cat, sub = hint[0].split(": ", 1)[1].split("/")[0], "colleague"
    elif "procurement" in title:
        cat, sub, stage = "customer", "procurement_lead", "active"
    elif email.endswith(".vc"):
        cat, sub = "capital", "investor"
    elif any(w in email for w in ("recruit", "talent", "scout")):
        cat, sub = "cold_inbound", "recruiter"
    return {"category": cat, "subtype": sub, "stage": stage, "confidence": "medium", "reason": f"fake: {cat}", "evidence": []}


def fake_sweep(text: str) -> dict:
    """calendar: one finding per code-listed deep-work overlap; notes_tasks: one per overdue task; news: none."""
    out = []
    if "name: calendar_sweep" in text or "You read" in text and "calendars" in text:
        overlaps = re.search(r"OVERLAPS computed by code: (\[.*?\])\n", text)
        for row in json.loads(overlaps.group(1)) if overlaps else []:
            if "deep-work block" in row:
                uid = re.match(r"event:(\S+)", row).group(1)
                title = re.search(rf"^event:{re.escape(uid)}\ntitle: (.+)$", text, re.M).group(1)
                out.append(finding(f"f{len(out) + 1}", f"Protect deep work: {title}", (f"event:{uid}", title), kind="deep work booked by others",
                                   section="calendar_personal", about=["meeting:x"],
                                   actions=[{"type": "calendar_response", "target": uid, "brief": "propose: decline", "assumptions": [],
                                             "watch_trigger": None, "read_start": None}]))
    elif "notes and the task list" in text:
        for m in re.finditer(r"^(task:\S+) · \[ \] (.+?) · due .*days overdue\)$", text, re.M):
            out.append(finding(f"f{len(out) + 1}", f"Do: {m.group(2)}", (m.group(1), m.group(2)), kind="overdue task", section="urgent", priority="P1"))
    return {"findings": out}


def fake_b_output(schema: str, text: str) -> dict:
    return {"SignatureFacts": fake_signature, "ContactClassification": fake_classification, "SweepOutput": fake_sweep}[schema](text)
