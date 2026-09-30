"""Verify (architecture §8): the eleven hard rules, enforced in code after materialize. A violation is fixed in
place or the item/action is dropped; every one is logged in verify.json. Returns the corrected structures."""
from __future__ import annotations

from dataclasses import dataclass

from ..compute import ComputeResult
from ..compute.contacts import is_recruiter
from ..schemas import (
    Candidate,
    ComposeResult,
    CustomizeOverrides,
    MaterializedAction,
    ReduceItem,
    TriageResult,
    VerifyResult,
    VerifyStats,
    VerifyViolation,
)

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass
class Verified:
    result: VerifyResult
    compose: ComposeResult
    actions: list[MaterializedAction]
    also_pending: list[str]         # reduced item ids rendered as one-liners
    outside_filter: list[str]       # P0 items hidden by a customize filter, rendered as one-liners


def _words(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def _is_recruiter(c) -> bool:
    return is_recruiter(c)


def verify(compose: ComposeResult, reduced: dict[str, ReduceItem], actions: list[MaterializedAction], cands: dict[str, Candidate],
           compute: ComputeResult, triage: list[TriageResult], known_sources: set[str], router_types: dict[str, str],
           budget_words: int, header: str, customize: CustomizeOverrides | None = None,
           overflow: list[str] | None = None, msg_thread: dict[str, str] | None = None) -> Verified:
    v: list[VerifyViolation] = []
    items = {ci.id: ci for ci in compose.items}
    placed: list[str] = ([compose.one_thing_id] if compose.one_thing_id else []) + [i for s in compose.sections for i in s.item_ids]
    cut = list(compose.cut_ids) + [i for i in (overflow or []) if i not in compose.cut_ids]
    outside: list[str] = []
    include_news = bool(customize and customize.include_newsletters)

    def drop_item(iid: str, rule: int, detail: str, to_pending: bool = False) -> None:
        nonlocal placed, cut
        if iid == compose.one_thing_id:
            compose.one_thing_id = None
        for s in compose.sections:
            if iid in s.item_ids:
                s.item_ids.remove(iid)
        placed = [i for i in placed if i != iid]
        if to_pending:
            if iid not in cut:
                cut.append(iid)
            v.append(VerifyViolation(rule=rule, item_id=iid, detail=detail, fix="fixed"))
        else:
            cut = [i for i in cut if i != iid]
            v.append(VerifyViolation(rule=rule, item_id=iid, detail=detail, fix="dropped"))

    # rules 3, 4, 5, 11 per placed item
    for iid in list(placed):
        it = reduced.get(iid)
        if it is None:
            drop_item(iid, 6, "item id not in reduce output")
            continue
        srcs = {e.source_id for e in it.citations}
        threads = {t for t in (compute_thread(s, msg_thread or {}) for s in srcs) if t}
        non_thread = any(not s.startswith(("msg:", "thread:")) for s in srcs)
        bulk_only = bool(threads) and not non_thread and all(router_types.get(t) == "bulk" for t in threads)
        if bulk_only and "news_attachment" not in it.candidate_types and not include_news:
            drop_item(iid, 3, "only newsletter/marketing sources")
            continue
        if "recruiter_pattern" not in it.candidate_types and it.entities and all(_is_recruiter(compute.directory.by_slug.get(e)) for e in it.entities if e in compute.directory.by_slug) and any(e in compute.directory.by_slug for e in it.entities):
            drop_item(iid, 4, "individual recruiter item")
            continue
        resolved = [e for e in it.citations if e.source_id in known_sources]
        if not resolved:
            extra = [e for c in it.candidate_ids if c in cands for e in cands[c].evidence if e.source_id in known_sources]
            if extra:
                it.citations = extra[:3]
                v.append(VerifyViolation(rule=5, item_id=iid, detail="citations did not resolve; replaced with candidate evidence", fix="fixed"))
            else:
                drop_item(iid, 5, "no citation resolves to a stored source")
                continue
        elif len(resolved) != len(it.citations):
            it.citations = resolved
            v.append(VerifyViolation(rule=5, item_id=iid, detail="unresolvable citations removed", fix="fixed"))
        if "suspicious_content" in it.candidate_types and it.priority == "P0":
            it.priority = "P2"
            v.append(VerifyViolation(rule=11, item_id=iid, detail="suspicious_content cannot be P0; set P2", fix="fixed"))
            if iid == compose.one_thing_id:
                drop_item(iid, 11, "suspicious_content cannot be the one thing", to_pending=True)

    # rules 1, 2, 10 per action
    kept_actions: list[MaterializedAction] = []
    for a in actions:
        if a.item_id not in placed:
            continue
        contact = compute.directory.lookup(a.target if a.target and "@" in a.target else None, a.target if a.target and "@" not in a.target else None)
        if contact is None and a.recipient_name:
            contact = compute.directory.lookup(None, a.recipient_name)
        item_nd = any(c is not None and "never_draft" in c.profile_rules
                      for c in (compute.directory.by_slug.get(e) for e in (reduced[a.item_id].entities if a.item_id in reduced else []) if e))
        never_draft = (contact is not None and "never_draft" in contact.profile_rules) or (contact is None and item_nd)
        if a.draft and never_draft and a.type == "decide":
            a = a.model_copy(update={"draft": None})
            v.append(VerifyViolation(rule=1, item_id=a.item_id, detail="decide-card draft on a never_draft contact's item removed", fix="fixed"))
            kept_actions.append(a)
            continue
        if a.draft and never_draft and a.type in ("reply", "forward_delegate", "message_person"):
            contact = contact or next(c for c in (compute.directory.by_slug.get(e) for e in reduced[a.item_id].entities if e)
                                      if c is not None and "never_draft" in c.profile_rules)
            name = contact.names[0] if contact.names else a.target
            a = a.model_copy(update={"type": "message_person", "draft": None, "llm": False,
                                     "text": f"↳ Message {name.split(' ')[0]} about {a.brief.rstrip('.')}. No draft ({name.split(' ')[0]})."})
            v.append(VerifyViolation(rule=1, item_id=a.item_id, detail=f"draft to never_draft contact {name} removed", fix="fixed"))
        if a.type in ("reply", "forward_delegate") and _is_recruiter(contact):
            v.append(VerifyViolation(rule=2, item_id=a.item_id, detail="draft to a cold-inbound recruiter", fix="dropped"))
            continue
        if a.type == "calendar_response" and not a.text.startswith("↳ Propose:"):
            a = a.model_copy(update={"text": "↳ Propose: " + a.text.lstrip("↳ ").rstrip(".") + "."})
            v.append(VerifyViolation(rule=10, item_id=a.item_id, detail="calendar_response rephrased as a proposal", fix="fixed"))
        kept_actions.append(a)

    # rule 7: every triage P0 with include appears somewhere
    p0_cands = {r.candidate_id for r in triage if r.include and r.priority == "P0"}
    for it in reduced.values():
        if set(it.candidate_ids) & p0_cands and it.id not in placed and it.id not in cut:
            cut.append(it.id)
            v.append(VerifyViolation(rule=7, item_id=it.id, detail="P0 item was not placed; added as a one-liner", fix="fixed"))
    # customize: P0 hidden by a filter renders under "Also outside your filter" (architecture §5.2)
    if customize and (customize.focus.mode == "only" or customize.sections_exclude):
        for iid in list(cut):
            it = reduced.get(iid)
            if it and it.priority == "P0" and iid not in outside:
                outside.append(iid)
        cut = [i for i in cut if i not in outside]

    # rule 9: length budget over item text (what + why)
    def total_words() -> int:
        return sum(_words(items[i].what) + _words(items[i].why) for i in placed if i in items)

    words = total_words()
    if words > budget_words:
        order = sorted([i for i in placed if i != compose.one_thing_id], key=lambda i: (PRIORITY_ORDER.get(reduced[i].priority, 9), int(i[1:])), reverse=True)
        for iid in order:
            if total_words() <= budget_words:
                break
            if reduced[iid].priority == "P0":
                continue
            drop_item(iid, 9, f"over budget ({words} > {budget_words} words); demoted to also pending", to_pending=True)
        words = total_words()

    cited = sum(1 for i in placed if reduced[i].citations)
    total_cits = sum(len(reduced[i].citations) for i in placed)
    stats = VerifyStats(words=words, budget=budget_words, header_present=bool(header.strip()), items=len(placed), items_cited=cited,
                        citations_total=total_cits, citations_resolved=sum(1 for i in placed for e in reduced[i].citations if e.source_id in known_sources))
    compose.cut_ids = [i for i in dict.fromkeys(cut) if i in reduced]
    return Verified(VerifyResult(violations=v, stats=stats), compose, kept_actions, compose.cut_ids, outside)


def compute_thread(source_id: str, msg_thread: dict[str, str]) -> str | None:
    if source_id.startswith("thread:"):
        return source_id
    if source_id.startswith("msg:"):
        return msg_thread.get(source_id)
    return None


__all__ = ["Verified", "verify"]
