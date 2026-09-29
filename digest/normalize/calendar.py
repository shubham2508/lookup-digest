"""RRULE expansion in [as_of − before, as_of + after] and NormalizedEvent construction (architecture §3)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from ..ingest.ics import RawEvent
from ..schemas import Attendee, NormalizedEvent, Partstat

_UNTIL_RE = re.compile(r"UNTIL=(\d{8})(?:T(\d{6})(Z?))?")


def _rewrite_until(rrule: str, tz: ZoneInfo) -> str:
    def fix(m: re.Match) -> str:
        day, hms, z = m.group(1), m.group(2), m.group(3)
        if not hms:
            return f"UNTIL={day}T235959"
        dt = datetime.strptime(day + hms, "%Y%m%d%H%M%S")
        if z:
            dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).replace(tzinfo=None)
        return "UNTIL=" + dt.strftime("%Y%m%dT%H%M%S")
    return _UNTIL_RE.sub(fix, rrule)


def expand_rrule(rrule: str, dtstart: datetime, win_start: datetime, win_end: datetime, tz: ZoneInfo) -> list[datetime]:
    """Occurrence starts in [win_start, win_end], wall-clock preserved across DST (09:00 stays 09:00)."""
    naive_start = dtstart.astimezone(tz).replace(tzinfo=None)
    rule = rrulestr(_rewrite_until(rrule, tz), dtstart=naive_start, ignoretz=True)
    a = win_start.astimezone(tz).replace(tzinfo=None)
    b = win_end.astimezone(tz).replace(tzinfo=None)
    return [o.replace(tzinfo=tz) for o in rule.between(a, b, inc=True)]


def event_domain(ev: RawEvent) -> str:
    """Hard facts only: the shared family calendar is personal. A work-calendar event becomes personal later, in the
    spine, when a family contact organizes or attends it (compute.mark_family_events); what an event is *about* is the
    calendar sweep's judgment, never a keyword match on its title."""
    return "personal" if ev.calendar == "shared_family" else "work"


def _partstat(ev: RawEvent, owner_emails: set[str]) -> Partstat:
    if ev.organizer and ev.organizer in owner_emails:
        return "ORGANIZER"
    for a in ev.attendees:
        if a.email in owner_emails:
            return a.partstat
    return "NEEDS-ACTION"


def _normalized(ev: RawEvent, start: datetime, end: datetime, recurrence_id: str | None, owner_emails: set[str]) -> NormalizedEvent:
    return NormalizedEvent(
        uid=ev.uid, recurrence_id=recurrence_id, calendar=ev.calendar, title=ev.title, description=ev.description,
        location=ev.location, start=start, end=end, organizer=ev.organizer,
        organizer_is_avery=bool(ev.organizer and ev.organizer in owner_emails),
        attendees=[Attendee(email=a.email, name=a.name, partstat=a.partstat) for a in ev.attendees],
        avery_partstat=_partstat(ev, owner_emails), created=ev.created, last_modified=ev.last_modified,
        domain=event_domain(ev), all_day=bool(getattr(ev, "all_day", False)),
    )


def expand_events(raw: list[RawEvent], as_of: datetime, before_days: int, after_days: int, owner_emails: set[str],
                  tz: ZoneInfo) -> list[NormalizedEvent]:
    win_start = as_of - timedelta(days=before_days)
    win_end = as_of + timedelta(days=after_days)
    masters = [e for e in raw if e.recurrence_id is None and e.status != "CANCELLED"]
    overrides: dict[str, dict[datetime, RawEvent]] = {}
    for e in raw:
        if e.recurrence_id is not None:
            overrides.setdefault(e.uid, {})[e.recurrence_id.astimezone(tz).replace(tzinfo=None)] = e
    out: list[NormalizedEvent] = []
    for ev in masters:
        if not ev.rrule:
            out.append(_normalized(ev, ev.start, ev.end, None, owner_emails))
            continue
        exdates = {x.astimezone(tz).replace(tzinfo=None) for x in ev.exdates}
        used: set[datetime] = set()
        for occ in expand_rrule(ev.rrule, ev.start, win_start, win_end, tz):
            key = occ.replace(tzinfo=None)
            if key in exdates:
                continue
            rid = occ.isoformat()
            ov = overrides.get(ev.uid, {}).get(key)
            if ov is not None:
                used.add(key)
                if ov.status != "CANCELLED":
                    out.append(_normalized(ov, ov.start, ov.end, rid, owner_emails))
                continue
            out.append(_normalized(ev, occ, occ + ev.duration, rid, owner_emails))
        for key, ov in overrides.get(ev.uid, {}).items():   # overrides moved into the window from outside it
            if key not in used and ov.status != "CANCELLED" and win_start <= ov.start <= win_end:
                out.append(_normalized(ov, ov.start, ov.end, ov.recurrence_id.isoformat(), owner_emails))
    out.sort(key=lambda e: (e.start, e.uid))
    return out
