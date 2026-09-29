"""Normalize: raw files → threads (quoted history stripped, forwards split), expanded events, notes, tasks,
freshness per source (architecture §3). Code only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import Settings
from ..ingest.eml import RawMessage
from ..ingest.loader import RawWorld, SourceStatus
from ..ingest.notes import RawNote
from ..schemas import NormalizedEvent, NormalizedMessage, NormalizedTask, NormalizedThread
from .calendar import expand_events
from .freshness import SourceFreshness, freshness_report
from .owner import detect_owner
from .router import is_bulk, route_messages
from .text import is_forward_subject, segment_body, split_signature
from .threading import group_messages, strip_brackets


@dataclass
class NormalizedWorld:
    as_of: datetime
    owner_email: str | None
    owner_emails: set[str]
    threads: list[NormalizedThread]
    events: list[NormalizedEvent]
    notes: list[RawNote]
    tasks: list[NormalizedTask]
    tasks_mtime: datetime | None
    freshness: dict[str, SourceFreshness]
    sources: dict[str, SourceStatus]
    directory: list[dict] = field(default_factory=list)   # observed {email, name} pairs from headers
    forwarded_count: int = 0
    owner_name: str = "owner"                              # the profile person's first name, for text shown to models

    @property
    def messages(self) -> list[NormalizedMessage]:
        return [m for t in self.threads for m in t.messages]

    def thread_of(self, message_id: str) -> NormalizedThread | None:
        for t in self.threads:
            if any(m.message_id == message_id for m in t.messages):
                return t
        return None


def normalize_message(raw: RawMessage, owner_emails: set[str], tz: ZoneInfo) -> list[NormalizedMessage]:
    """One raw message → itself (history stripped, signature split) plus any forwarded messages it carries."""
    own, segments = segment_body(raw.body, tz)
    body, sig = split_signature(own)
    head = NormalizedMessage(
        message_id=raw.message_id, in_reply_to=raw.in_reply_to, references=list(raw.references), sent_at=raw.sent_at,
        from_addr=raw.from_addr, from_name=raw.from_name, to=list(raw.to), cc=list(raw.cc), subject=raw.subject,
        body_new=body, signature_block=sig, headers=dict(raw.headers), is_from_avery=raw.from_addr in owner_emails,
    )
    out = [head]
    forward = is_forward_subject(raw.subject) or any(s.kind == "forward" for s in segments)
    if not forward:
        return out
    keep = False
    n = 0
    for seg in segments:
        if seg.kind == "forward" or (is_forward_subject(raw.subject) and seg.depth == 0 and seg.kind in ("original", "header")):
            keep = True
        if not keep or not seg.body.strip():
            continue
        n += 1
        fbody, fsig = split_signature(seg.body)
        sent = seg.sent_at or raw.sent_at - timedelta(seconds=n)
        out.append(NormalizedMessage(
            message_id=f"<fwd{n}.{strip_brackets(raw.message_id)}>", in_reply_to=None, references=[], sent_at=sent,
            from_addr=seg.from_addr, from_name=seg.from_name, to=seg.to, cc=seg.cc,
            subject=seg.subject or raw.subject, body_new=fbody, signature_block=fsig, headers={},
            is_from_avery=bool(seg.from_addr) and seg.from_addr in owner_emails, forwarded_by=raw.from_addr,
        ))
    return out


def normalize_world(raw: RawWorld, settings: Settings, person: str) -> NormalizedWorld:
    tz = ZoneInfo(settings.timezone)
    owner, owner_emails = detect_owner(raw.messages, raw.events, person)
    bulk_ids = {m.message_id for m in raw.messages if is_bulk(NormalizedMessage(
        message_id=m.message_id, sent_at=m.sent_at, from_addr=m.from_addr, headers=m.headers))}
    groups = group_messages(raw.messages, owner_emails, bulk_ids)
    threads: list[NormalizedThread] = []
    fwd_total = 0
    for tid, msgs in groups.items():
        norm: list[NormalizedMessage] = []
        for m in msgs:
            expanded = normalize_message(m, owner_emails, tz)
            fwd_total += len(expanded) - 1
            norm.extend(expanded)
        norm.sort(key=lambda x: (x.sent_at, x.forwarded_by is None, x.message_id))
        threads.append(NormalizedThread(thread_id=tid, messages=norm, router_type=route_messages(norm)))
    events = expand_events(raw.events, raw.as_of, settings.calendar.expand_before_days, settings.calendar.expand_after_days,
                           owner_emails, tz)
    seen: dict[str, str] = {}
    for m in raw.messages:
        for addr, name in m.display_names.items():
            if name and addr not in seen:
                seen[addr] = name
    directory = [{"email": a, "name": n} for a, n in sorted(seen.items())]
    return NormalizedWorld(
        as_of=raw.as_of, owner_email=owner, owner_emails=owner_emails, threads=threads, events=events,
        notes=list(raw.notes), tasks=list(raw.tasks), tasks_mtime=raw.tasks_mtime,
        freshness=freshness_report(raw, raw.as_of, settings.freshness, tz), sources=dict(raw.sources),
        directory=directory, forwarded_count=fwd_total, owner_name=(person or "owner").split()[0],
    )


__all__ = ["NormalizedWorld", "normalize_message", "normalize_world", "SourceFreshness"]
