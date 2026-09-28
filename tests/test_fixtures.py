"""The hand-made mini dataset must be well-formed: it is what Tracks A and C develop against before real data lands."""
import email.utils
from email import policy
from email.parser import BytesParser


def test_mini_inbox_parses(mini_dir):
    files = sorted((mini_dir / "inbox").glob("*.eml"))
    assert len(files) == 7
    msgs = [BytesParser(policy=policy.default).parsebytes(f.read_bytes()) for f in files]
    ids = [m["Message-ID"] for m in msgs]
    assert all(ids) and len(set(ids)) == 7
    for m in msgs:
        assert m["Date"] and m["From"] and m["To"] and m["Subject"]
        assert email.utils.parsedate_to_datetime(m["Date"]).utcoffset().total_seconds() == -7 * 3600
        assert m.get_body(preferencelist=("plain",)).get_content().strip()
    replies = [m for m in msgs if m["In-Reply-To"]]
    assert len(replies) == 1 and replies[0]["In-Reply-To"] in ids and replies[0]["References"]
    bulk = [m for m in msgs if m["List-Unsubscribe"] or (m["Precedence"] or "").lower() == "bulk"]
    assert len(bulk) == 2
    assert sum(1 for m in msgs if "avery@tessera.io" in m["From"]) == 1


def test_mini_calendars_parse(mini_dir):
    from icalendar import Calendar

    work = Calendar.from_ical((mini_dir / "calendar" / "work.ics").read_bytes())
    events = list(work.walk("VEVENT"))
    assert len(events) == 4
    assert sum(1 for e in events if e.get("RRULE")) == 2
    organizers = [str(e.get("ORGANIZER")).lower() for e in events]
    assert sum(1 for o in organizers if o.endswith("avery@tessera.io")) == 2
    assert any("lumen" in str(e.get("SUMMARY")).lower() for e in events)
    fam = Calendar.from_ical((mini_dir / "calendar" / "shared_family.ics").read_bytes())
    fe = list(fam.walk("VEVENT"))
    assert len(fe) == 1 and fe[0].get("CREATED") and "sam" in str(fe[0].get("ORGANIZER")).lower()


def test_mini_notes_and_tasks(mini_dir):
    note = (mini_dir / "notes" / "sprint-week.md").read_text(encoding="utf-8")
    assert note.startswith("Date: 2026-09-22 | Attendees:")
    tasks = (mini_dir / "tasks.md").read_text(encoding="utf-8")
    lines = [ln for ln in tasks.splitlines() if ln.startswith("- [")]
    assert len(lines) == 3 and all("(due: 2026-" in ln for ln in lines)
    assert any(ln.startswith("- [x]") for ln in lines)
