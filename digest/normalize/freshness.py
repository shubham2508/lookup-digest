"""Freshness per source: latest_item_time and staleness (architecture §3, §6.4; DESIGN_LOG §4.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from ..config import FreshnessCfg
from ..ingest.loader import RawWorld
from ..schemas import SourceKind

FreshState = Literal["ok", "stale", "missing", "unreadable"]


@dataclass
class SourceFreshness:
    kind: SourceKind
    state: FreshState
    latest_item_time: datetime | None
    age_hours: float | None
    detail: str = ""
    items: int = 0

    @property
    def capped(self) -> bool:
        return self.state != "ok"


def _age(as_of: datetime, t: datetime | None) -> float | None:
    return None if t is None else round((as_of - t).total_seconds() / 3600, 2)


def freshness_report(raw: RawWorld, as_of: datetime, cfg: FreshnessCfg, tz: ZoneInfo) -> dict[str, SourceFreshness]:
    out: dict[str, SourceFreshness] = {}
    st = raw.sources["email"]
    latest = max((m.sent_at for m in raw.messages), default=None)
    age = _age(as_of, latest)
    state: FreshState = st.state if st.state != "ok" else ("stale" if age is not None and age > cfg.email_stale_hours else "ok")
    if st.state == "ok" and latest is None:
        state = "missing"
    out["email"] = SourceFreshness("email", state, latest, age, st.detail, len(raw.messages))

    st = raw.sources["calendar"]
    stamps = [e.last_modified or e.created or e.dtstamp for e in raw.events]
    # OPEN_QUESTIONS #14: a quiet calendar is not a stale one; the .ics sync time (file mtime) counts too
    latest = max((s for s in [*stamps, raw.calendar_mtime] if s is not None), default=None)
    age = _age(as_of, latest)
    state = st.state if st.state != "ok" else ("stale" if age is not None and age > cfg.calendar_stale_hours else "ok")
    if st.state == "ok" and latest is None:
        state = "missing"
    out["calendar"] = SourceFreshness("calendar", state, latest, age, st.detail, len(raw.events))

    st = raw.sources["notes"]
    times = [datetime.combine(n.header_date, datetime.min.time(), tzinfo=tz) if n.header_date else n.mtime for n in raw.notes]
    latest = max((t for t in times if t is not None), default=None)
    state = st.state if st.state != "ok" else ("missing" if latest is None else "ok")
    out["notes"] = SourceFreshness("notes", state, latest, _age(as_of, latest), st.detail, len(raw.notes))

    st = raw.sources["tasks"]
    latest = raw.tasks_mtime
    age = _age(as_of, latest)
    state = st.state if st.state != "ok" else ("stale" if age is not None and age > cfg.tasks_stale_days * 24 else "ok")
    out["tasks"] = SourceFreshness("tasks", state, latest, age, st.detail, len(raw.tasks))
    return out


def header_fragment(f: SourceFreshness, as_of: datetime) -> str:
    """'inbox synced 05:58' / 'calendar ok' / 'tasks stale (12 days)' / 'notes missing'."""
    label = {"email": "inbox", "calendar": "calendar", "notes": "notes", "tasks": "tasks"}[f.kind]
    if f.state == "ok":
        if f.kind == "email" and f.latest_item_time is not None:
            t = f.latest_item_time
            same_day = t.date() == as_of.date()
            return f"inbox synced {t.strftime('%H:%M') if same_day else t.strftime('%a %H:%M')}"
        return f"{label} ok"
    if f.state == "stale" and f.age_hours is not None:
        days = f.age_hours / 24
        span = f"{int(days)} days" if days >= 2 else f"{int(f.age_hours)}h"
        return f"{label} stale ({span})"
    return f"{label} {f.state}"
