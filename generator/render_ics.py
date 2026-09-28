"""Render calendar.yaml into work.ics and shared_family.ics (RRULE, PARTSTAT, ORGANIZER, CREATED, LAST-MODIFIED)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .timeline import Timeline
from .world import World

PARTSTAT_ROLE = {"ORGANIZER": "CHAIR"}


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, s = [], line
    while len(s.encode("utf-8")) > 72:
        out.append(s[:72])
        s = " " + s[72:]
    out.append(s)
    return "\r\n".join(out)


def _attendee(w: World, a: dict, organizer_email: str) -> str:
    ref = a["id"]
    addr = w.addr(ref)
    partstat = a.get("partstat", "NEEDS-ACTION")
    if partstat == "ORGANIZER":
        partstat = "ACCEPTED"
    role = "CHAIR" if addr["email"] == organizer_email else "REQ-PARTICIPANT"
    rsvp = ";RSVP=TRUE" if partstat == "NEEDS-ACTION" else ""
    return f"ATTENDEE;CN={addr['name']};PARTSTAT={partstat};ROLE={role}{rsvp}:mailto:{addr['email']}"


def _event(w: World, tl: Timeline, ev: dict, calendar: str, default_organizer: str) -> list[str]:
    organizer = w.addr(ev.get("organizer") or default_organizer)
    uid = ev["uid"]          # no domain suffix: the manifest cites event:<uid> exactly as calendar.yaml names it
    created_day = ev.get("created_day", ev.get("from_day", ev.get("day", 1)))
    created = tl.dt(created_day, ev.get("created_time", "16:00"))
    lm_day = ev.get("last_modified_day", created_day)
    last_mod = tl.dt(lm_day, ev.get("last_modified_time", ev.get("created_time", "16:00")))
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{tl.ics_utc(created)}"]
    if ev.get("all_day"):
        start = tl.date(ev["day"])
        end = tl.date(ev.get("end_day", ev["day"])) + timedelta(days=1)
        lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}")
    else:
        day = ev.get("day", ev.get("from_day"))
        start = tl.dt(day, ev["start"])
        end = tl.dt(day, ev["end"])
        lines.append(f"DTSTART;TZID=America/Los_Angeles:{tl.ics_local(start)}")
        lines.append(f"DTEND;TZID=America/Los_Angeles:{tl.ics_local(end)}")
    if ev.get("rrule"):
        rrule = ev["rrule"]
        if "UNTIL=day-" in rrule:
            d = int(rrule.split("UNTIL=day-")[1].split(";")[0])
            until = tl.dt(d, "23:59")
            rrule = rrule.replace(f"UNTIL=day-{d}", f"UNTIL={tl.ics_utc(until)}")
        lines.append(f"RRULE:{rrule}")
    lines.append(f"SUMMARY:{_esc(ev['title'])}")
    if ev.get("description"):
        lines.append(f"DESCRIPTION:{_esc(ev['description'])}")
    if ev.get("location"):
        lines.append(f"LOCATION:{_esc(ev['location'])}")
    lines.append(f"ORGANIZER;CN={organizer['name']}:mailto:{organizer['email']}")
    attendees = list(ev.get("attendees") or [])
    ids = {a["id"] for a in attendees}
    org_ref = ev.get("organizer") or default_organizer
    if org_ref not in ids:
        attendees.insert(0, {"id": org_ref, "partstat": "ACCEPTED"})
    if calendar == "work" and "avery" not in ids and org_ref != "avery":
        attendees.append({"id": "avery", "partstat": "ACCEPTED"})
    for a in attendees:
        lines.append(_attendee(w, a, organizer["email"]))
    lines.append(f"CREATED:{tl.ics_utc(created)}")
    lines.append(f"LAST-MODIFIED:{tl.ics_utc(last_mod)}")
    lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    return lines


def _vtimezone() -> list[str]:
    return [
        "BEGIN:VTIMEZONE", "TZID:America/Los_Angeles",
        "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0800", "TZOFFSETTO:-0700", "TZNAME:PDT", "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
        "BEGIN:STANDARD", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0800", "TZNAME:PST", "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
        "END:VTIMEZONE",
    ]


def render_calendar(w: World, tl: Timeline, which: str) -> tuple[str, list[dict]]:
    cal = w.calendar[which]
    name = cal["calendar_name"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lookup-digest//generator//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}", "X-WR-TIMEZONE:America/Los_Angeles"] + _vtimezone()
    events: list[dict] = []
    if which == "work":
        default_org = "avery"
        evs = list(cal.get("recurring", [])) + list(cal.get("one_off", []))
    else:
        default_org = cal.get("organizer_default", "sam")
        evs = list(cal.get("events", []))
    for ev in evs:
        lines += _event(w, tl, ev, which, default_org)
        events.append(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n", events


def write_calendars(w: World, tl: Timeline, out: Path, corrupt_work: bool = False) -> dict[str, list[dict]]:
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[dict]] = {}
    for which, fname in (("work", "work.ics"), ("shared_family", "shared_family.ics")):
        text, evs = render_calendar(w, tl, which)
        if corrupt_work and which == "work":
            # truncate mid-file after the 8th VEVENT (data_generation §10)
            idx = [i for i in range(len(text)) if text.startswith("END:VEVENT", i)]
            cut = idx[7] + 4 if len(idx) > 8 else len(text) // 2
            text = text[:cut]
        (out / fname).write_text(text, encoding="utf-8")
        result[which] = evs
    return result
