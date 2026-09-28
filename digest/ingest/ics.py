"""Parse an .ics file with `icalendar` into RawEvents (RRULE kept as text; expansion is in digest/normalize/calendar.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar

from ..schemas import Attendee


@dataclass
class RawEvent:
    uid: str
    calendar: str                       # "work" | "shared_family"
    title: str
    start: datetime                     # aware, digest tz
    end: datetime
    all_day: bool
    description: str | None = None
    location: str | None = None
    rrule: str | None = None            # "FREQ=WEEKLY;BYDAY=TU,TH"
    exdates: list[datetime] = field(default_factory=list)
    recurrence_id: datetime | None = None   # this VEVENT overrides that occurrence of the master with the same uid
    organizer: str = ""                 # email, lowercased
    organizer_name: str = ""
    attendees: list[Attendee] = field(default_factory=list)
    created: datetime | None = None
    last_modified: datetime | None = None
    dtstamp: datetime | None = None
    status: str = "CONFIRMED"

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


def to_tz(value: datetime | date, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)
    return datetime.combine(value, time(0), tzinfo=tz)


def _mailto(value: object) -> str:
    s = str(value or "").strip()
    if s.lower().startswith("mailto:"):
        s = s[7:]
    return s.lower()


def _as_list(value: object) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _dt_prop(ev, name: str, tz: ZoneInfo) -> datetime | None:
    prop = ev.get(name)
    if prop is None:
        return None
    return to_tz(prop.dt, tz)


def parse_ics_bytes(data: bytes, calendar: str, tz: ZoneInfo) -> list[RawEvent]:
    cal = Calendar.from_ical(data)
    events: list[RawEvent] = []
    for ev in cal.walk("VEVENT"):
        dtstart = ev.get("DTSTART")
        if dtstart is None:
            continue
        all_day = not isinstance(dtstart.dt, datetime)
        start = to_tz(dtstart.dt, tz)
        dtend = ev.get("DTEND")
        if dtend is not None:
            end = to_tz(dtend.dt, tz)
        elif ev.get("DURATION") is not None:
            end = start + ev.get("DURATION").dt
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        rrule = ev.get("RRULE")
        rrule_text = rrule.to_ical().decode() if rrule is not None else None
        exdates: list[datetime] = []
        for ex in _as_list(ev.get("EXDATE")):
            for d in getattr(ex, "dts", []):
                exdates.append(to_tz(d.dt, tz))
        organizer = ev.get("ORGANIZER")
        attendees: list[Attendee] = []
        for a in _as_list(ev.get("ATTENDEE")):
            params = getattr(a, "params", {}) or {}
            partstat = str(params.get("PARTSTAT", "NEEDS-ACTION")).upper()
            if partstat not in ("ACCEPTED", "DECLINED", "TENTATIVE", "NEEDS-ACTION"):
                partstat = "NEEDS-ACTION"
            attendees.append(Attendee(email=_mailto(a), name=str(params.get("CN", "") or ""), partstat=partstat))
        rid = ev.get("RECURRENCE-ID")
        events.append(RawEvent(
            uid=str(ev.get("UID") or "").strip(), calendar=calendar, title=str(ev.get("SUMMARY") or "").strip(),
            start=start, end=end, all_day=all_day,
            description=(str(ev.get("DESCRIPTION")).strip() or None) if ev.get("DESCRIPTION") is not None else None,
            location=(str(ev.get("LOCATION")).strip() or None) if ev.get("LOCATION") is not None else None,
            rrule=rrule_text, exdates=exdates, recurrence_id=to_tz(rid.dt, tz) if rid is not None else None,
            organizer=_mailto(organizer), organizer_name=str((getattr(organizer, "params", {}) or {}).get("CN", "") or ""),
            attendees=attendees, created=_dt_prop(ev, "CREATED", tz), last_modified=_dt_prop(ev, "LAST-MODIFIED", tz),
            dtstamp=_dt_prop(ev, "DTSTAMP", tz), status=str(ev.get("STATUS") or "CONFIRMED").upper(),
        ))
    return events
