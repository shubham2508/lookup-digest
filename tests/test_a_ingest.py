"""Track A · M3: ingest (architecture §3). Only items with time <= as_of exist; broken sources degrade, never raise."""
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from digest.ingest import DataMissing, load_world, parse_eml_bytes, parse_note_text, parse_tasks_text
from digest.ingest.eml import html_to_text
from digest.runs import parse_as_of

TZ = ZoneInfo("America/Los_Angeles")
AS_OF = parse_as_of("2026-09-24T06:00")


def test_fixture_loads_everything_as_of_thursday(mini_dir):
    w = load_world(mini_dir, AS_OF, TZ)
    assert {k: s.state for k, s in w.sources.items()} == {"email": "ok", "calendar": "ok", "notes": "ok", "tasks": "ok"}
    assert len(w.messages) == 7 and len(w.events) == 5 and len(w.notes) == 1 and len(w.tasks) == 3
    sam = w.messages[-1]
    assert sam.from_addr == "sam@parkfamily.example" and sam.from_name == "Sam Park"
    assert sam.sent_at.isoformat() == "2026-09-23T21:10:33-07:00" and sam.display_names["avery@tessera.io"] == "Avery Chen"
    bulk = [m for m in w.messages if "List-Unsubscribe" in m.headers]
    assert len(bulk) == 2 and all(m.headers["Precedence"] == "bulk" for m in bulk)
    reply = next(m for m in w.messages if m.in_reply_to)
    assert reply.in_reply_to == "<20260922-1642.marcus@inflectionpoint.vc>" and reply.references == [reply.in_reply_to]


def test_as_of_filter_hides_the_future(mini_dir):
    w = load_world(mini_dir, parse_as_of("2026-09-23T06:00"), TZ)
    assert [m.message_id for m in w.messages][-1] == "<20260922-2130.avery@tessera.io>"
    assert w.sources["email"].skipped_future == 2          # SC Brief (Wed 07:00) and Sam (Wed 21:10)
    uids = {e.uid for e in w.events}
    assert "lumen-demo-20260924@lumenanalytics.example" not in uids     # created Wed 17:31
    assert "wren-pediatrician-20260924@parkfamily.example" not in uids  # created Wed 21:04
    assert w.sources["calendar"].skipped_future == 2
    # the note is dated Tue 22nd: exists on the 23rd, not on the 22nd at 06:00? (header date = day granularity → exists that day)
    assert len(w.notes) == 1
    w2 = load_world(mini_dir, parse_as_of("2026-09-21T06:00"), TZ)
    assert w2.notes == [] and w2.sources["notes"].skipped_future == 1


def test_stale_inbox_variant_ignores_last_30_hours(mini_dir):
    w = load_world(mini_dir, AS_OF, TZ, variant="stale_inbox")
    assert max(m.sent_at for m in w.messages) <= AS_OF - timedelta(hours=30)
    assert len(w.messages) == 5


def test_no_notes_and_corrupt_ics_variants(mini_dir):
    w = load_world(mini_dir, AS_OF, TZ, variant="no_notes")
    assert w.sources["notes"].state == "missing" and w.notes == [] and "no_notes" in w.sources["notes"].detail
    w = load_world(mini_dir, AS_OF, TZ, variant="corrupt_ics")
    cal = w.sources["calendar"]
    assert not any(e.calendar == "work" for e in w.events), "truncated work.ics must not yield work events"
    assert cal.state in ("ok", "unreadable") and any("unreadable" in e for e in cal.errors)
    assert any(e.calendar == "shared_family" for e in w.events)
    with pytest.raises(ValueError):
        load_world(mini_dir, AS_OF, TZ, variant="bogus")


def test_missing_sources_are_reported_not_raised(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "bad.eml").write_bytes(b"From: x@y\nSubject: no date\n\nbody\n")
    w = load_world(tmp_path, AS_OF, TZ)
    assert w.sources["email"].state == "unreadable" and w.sources["email"].errors
    assert w.sources["calendar"].state == "missing" and w.sources["notes"].state == "missing" and w.sources["tasks"].state == "missing"
    with pytest.raises(DataMissing):
        load_world(tmp_path / "nope", AS_OF, TZ)


def test_eml_html_only_body_and_missing_message_id():
    raw = (b"Date: Tue, 22 Sep 2026 10:00:00 -0700\r\nFrom: Dana <dana@lumen.example>\r\nTo: avery@tessera.io\r\n"
           b"Subject: demo\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Hi Avery,</p><p>Standard &amp; API?</p><br>Dana\r\n")
    m = parse_eml_bytes(raw, "x/2026-09-22-1000-dana.eml", TZ)
    assert m.message_id == "<2026-09-22-1000-dana@local.missing-id>"
    assert m.body == "Hi Avery,\nStandard & API?\n\nDana"
    assert html_to_text("<div>a</div><style>x{}</style><div>b</div>") == "a\nb"


def test_note_header_and_tasks_parse():
    n = parse_note_text("Date: 2026-09-22 | Attendees: Jordan Liu, Priya Iyer\n\n# Standup\n\n- item\n", "notes/x.md", None)
    assert n.header_date.isoformat() == "2026-09-22" and n.attendees == ["Jordan Liu", "Priya Iyer"] and n.title == "Standup"
    n2 = parse_note_text("# Draft board update\n\nARR $3.2M\n", "notes/draft.md", None)
    assert n2.header_date is None and n2.attendees == [] and n2.title == "Draft board update"
    tasks = parse_tasks_text("- [ ] Send Q2 board update to Diane (due: 2026-09-18)\n- [x] Approve expenses (due: 2026-09-21)\n- [ ] Call Ben\n- [ ] Call Ben\n", None)
    assert [t.task_id for t in tasks] == ["send-q2-board-update-to-diane", "approve-expenses", "call-ben", "call-ben-2"]
    assert tasks[0].due.isoformat() == "2026-09-18" and tasks[1].status == "done" and tasks[2].due is None


def test_last_modified_header_beats_mtime():
    from digest.ingest.notes import last_modified_header
    n = parse_note_text("<!-- last-modified: 2026-09-12T10:00:00-07:00 -->\nDate: 2026-09-10 | Attendees: A\n\n# T\n", "notes/x.md", None, TZ)
    assert n.mtime.isoformat() == "2026-09-12T10:00:00-07:00" and n.header_date.isoformat() == "2026-09-10"
    tasks = parse_tasks_text("<!-- last-modified: 2026-09-12 -->\n- [ ] Call Ben (due: 2026-09-20)\n", None, TZ)
    assert tasks[0].file_last_modified.isoformat() == "2026-09-12T00:00:00-07:00"
    assert last_modified_header("no header") is None


def test_data_dir_must_exist():
    with pytest.raises(DataMissing):
        load_world(Path("/definitely/not/here"), AS_OF, TZ)
