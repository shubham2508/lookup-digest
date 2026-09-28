"""Track A · M3: normalize — threading, quote stripping, signatures, forwards, RRULE expansion, freshness, owner."""
from datetime import datetime
from zoneinfo import ZoneInfo

from digest.config import load_settings
from digest.ingest import load_world
from digest.ingest.eml import RawMessage
from digest.ingest.ics import RawEvent
from digest.normalize import normalize_message, normalize_world
from digest.normalize.calendar import expand_events, expand_rrule
from digest.normalize.freshness import header_fragment
from digest.normalize.text import segment_body, split_signature
from digest.normalize.threading import group_messages
from digest.runs import parse_as_of
from digest.schemas import Attendee

TZ = ZoneInfo("America/Los_Angeles")
AS_OF = parse_as_of("2026-09-24T06:00")
SETTINGS = load_settings()


def _raw(mid, sent, frm, to, subject, body, irt=None, refs=(), headers=None, name=""):
    return RawMessage(path="", message_id=mid, in_reply_to=irt, references=list(refs), sent_at=parse_as_of(sent),
                      from_addr=frm, from_name=name, to=list(to), cc=[], subject=subject, body=body, headers=headers or {})


def _world(mini_dir, as_of=AS_OF):
    return normalize_world(load_world(mini_dir, as_of, TZ), SETTINGS, "Avery Chen")


def test_fixture_threads_and_router(mini_dir):
    w = _world(mini_dir)
    assert w.owner_email == "avery@tessera.io"
    by_id = {t.thread_id: t for t in w.threads}
    cap = by_id["thread:20260922-1642.marcus@inflectionpoint.vc"]
    assert [m.message_id for m in cap.messages] == ["<20260922-1642.marcus@inflectionpoint.vc>", "<20260922-2130.avery@tessera.io>"]
    assert cap.messages[1].is_from_avery and cap.router_type == "human"
    assert {t.thread_id.split(":", 1)[1].split(".")[1].split("@")[0]: t.router_type for t in w.threads} == {
        "hello": "marketing", "dse": "automated", "renee": "human", "marcus": "human", "brief": "newsletter", "sam": "human"}


def test_quoted_history_stripped_and_signature_separate(mini_dir):
    w = _world(mini_dir)
    msgs = {m.message_id: m for m in w.messages}
    avery = msgs["<20260922-2130.avery@tessera.io>"]
    assert ">" not in avery.body_new and "Before we go further" not in avery.body_new
    assert avery.body_new.startswith("marcus, yes.") and avery.body_new.endswith("Avery")
    renee = msgs["<20260922-1408.renee@halberd.com>"]
    assert renee.signature_block == "Renee Tan | Procurement Lead | Halberd Manufacturing"
    assert renee.body_new.endswith("Thanks,\nRenee")
    marcus = msgs["<20260922-1642.marcus@inflectionpoint.vc>"]
    assert marcus.signature_block == "Marcus Webb\nPartner, Inflection Point Ventures" and marcus.body_new.endswith("Marcus")


def test_gmail_attribution_wrapped_and_outlook_original():
    own, segs = segment_body("thanks, got it.\n\nOn Tue, Sep 22, 2026 at 4:42 PM Marcus Webb <marcus@inflectionpoint.vc>\nwrote:\n\n> Avery,\n> Before we go further\n", TZ)
    assert own == "thanks, got it." and len(segs) == 1
    assert segs[0].from_addr == "marcus@inflectionpoint.vc" and segs[0].from_name == "Marcus Webb"
    assert segs[0].sent_at == datetime(2026, 9, 22, 16, 42, tzinfo=TZ) and segs[0].body == "Avery,\nBefore we go further"
    own, segs = segment_body("Confirmed.\n\n-----Original Message-----\nFrom: Dana W <dana@lumen.example>\nSent: Wednesday, September 23, 2026 5:31 PM\nTo: Avery Chen\nSubject: Demo agenda\n\nStandard or API?\n", TZ)
    assert own == "Confirmed." and segs[0].kind == "original" and segs[0].body == "Standard or API?"
    assert segs[0].sent_at == datetime(2026, 9, 23, 17, 31, tzinfo=TZ)
    body, sig = split_signature("ok\n\nSent from my iPhone")
    assert body == "ok" and sig == "Sent from my iPhone"


def test_forwarded_chain_becomes_messages_with_forwarded_by():
    fwd = ("thoughts?\n\n---------- Forwarded message ---------\nFrom: Renee Tan <renee.tan@halberd.com>\n"
           "Date: Tue, Sep 22, 2026 at 2:08 PM\nSubject: Re: Rollout date still on?\nTo: Tomás Reyes <tomas@tessera.io>\n\n"
           "Tomás, see below. Can you confirm?\n\nRenee\n\nOn Mon, Sep 21, 2026 at 9:30 AM Tomás Reyes <tomas@tessera.io> wrote:\n"
           "> Renee, we're on track. I'll confirm with eng.\n>\n> On Fri, Sep 18, 2026 at 3:00 PM Renee Tan <renee.tan@halberd.com> wrote:\n"
           "> > Is the rollout still on?\n")
    raw = _raw("<fwd@tessera.io>", "2026-09-22T22:11", "tomas@tessera.io", ["avery@tessera.io"], "Fwd: Rollout date still on?", fwd, name="Tomás Reyes")
    out = normalize_message(raw, {"avery@tessera.io"}, TZ)
    assert len(out) == 4 and out[0].body_new == "thoughts?" and out[0].forwarded_by is None
    f1, f2, f3 = out[1:]
    assert f1.message_id == "<fwd1.fwd@tessera.io>" and f1.forwarded_by == "tomas@tessera.io"
    assert f1.from_addr == "renee.tan@halberd.com" and f1.sent_at == datetime(2026, 9, 22, 14, 8, tzinfo=TZ)
    assert f1.subject == "Re: Rollout date still on?" and f1.body_new == "Tomás, see below. Can you confirm?\n\nRenee"
    assert f2.from_addr == "tomas@tessera.io" and f2.body_new == "Renee, we're on track. I'll confirm with eng."
    assert f3.from_addr == "renee.tan@halberd.com" and f3.body_new == "Is the rollout still on?" and f3.sent_at.day == 18
    # a plain reply's quoted history is NOT turned into messages
    reply = _raw("<r@x>", "2026-09-23T10:00", "marcus@inflectionpoint.vc", ["avery@tessera.io"], "Re: cap table",
                 "thanks\n\nOn Tue, Sep 22, 2026 at 9:30 PM Avery Chen <avery@tessera.io> wrote:\n> will send it tonight\n")
    assert len(normalize_message(reply, {"avery@tessera.io"}, TZ)) == 1


def test_threading_fallback_subject_and_participants():
    a = _raw("<1@x>", "2026-09-20T10:00", "renee.tan@halberd.com", ["avery@tessera.io"], "Rollout date", "a")
    b = _raw("<2@x>", "2026-09-21T10:00", "avery@tessera.io", ["renee.tan@halberd.com"], "Re: Rollout date", "b")   # no headers
    c = _raw("<3@x>", "2026-09-21T11:00", "dana@lumen.example", ["avery@tessera.io"], "RE: rollout date", "c")     # other participants
    d = _raw("<4@x>", "2026-09-22T09:00", "renee.tan@halberd.com", ["avery@tessera.io"], "Re: Rollout date", "d", irt="<2@x>", refs=["<1@x>", "<2@x>"])
    n1 = _raw("<n1@x>", "2026-09-20T07:00", "brief@scbrief.example", ["avery@tessera.io"], "Weekly", "n", headers={"List-Unsubscribe": "<x>"})
    n2 = _raw("<n2@x>", "2026-09-21T07:00", "brief@scbrief.example", ["avery@tessera.io"], "Weekly", "n", headers={"List-Unsubscribe": "<x>"})
    groups = group_messages([a, b, c, d, n1, n2], {"avery@tessera.io"}, {"<n1@x>", "<n2@x>"})
    assert [m.message_id for m in groups["thread:1@x"]] == ["<1@x>", "<2@x>", "<4@x>"]
    assert [m.message_id for m in groups["thread:3@x"]] == ["<3@x>"]
    assert "thread:n1@x" in groups and "thread:n2@x" in groups, "bulk mail never threads by subject"


def test_rrule_expansion_window_exdate_override_and_dst(mini_dir):
    w = _world(mini_dir)
    deep = [e for e in w.events if e.uid == "deepwork-tue-thu@tessera.io"]
    assert len(deep) == 11 and all(e.start.hour == 9 and e.end.hour == 11 for e in deep)
    assert min(e.start for e in deep) >= AS_OF.replace(day=1) and max(e.start for e in deep).isoformat() == "2026-10-06T09:00:00-07:00"
    today = [e for e in deep if e.start.date() == AS_OF.date()]
    assert len(today) == 1 and today[0].recurrence_id == "2026-09-24T09:00:00-07:00" and today[0].avery_partstat == "ORGANIZER"
    assert sum(1 for e in w.events if e.uid == "jordan-1on1-thu@tessera.io") == 5
    fam = next(e for e in w.events if e.calendar == "shared_family")
    assert fam.domain == "personal" and fam.avery_partstat == "NEEDS-ACTION" and not fam.organizer_is_avery
    assert fam.created.isoformat() == "2026-09-23T21:04:00-07:00"
    # DST: 09:00 stays 09:00 across the Nov 1 fall-back
    occ = expand_rrule("FREQ=WEEKLY;BYDAY=TU", parse_as_of("2026-10-20T09:00"), parse_as_of("2026-10-20T00:00"), parse_as_of("2026-11-10T00:00"), TZ)
    assert [o.isoformat() for o in occ] == ["2026-10-20T09:00:00-07:00", "2026-10-27T09:00:00-07:00", "2026-11-03T09:00:00-08:00"]
    # EXDATE + RECURRENCE-ID override + UNTIL in UTC
    master = RawEvent(uid="u", calendar="work", title="standup", start=parse_as_of("2026-09-01T09:00"), end=parse_as_of("2026-09-01T09:15"), all_day=False,
                      rrule="FREQ=DAILY;UNTIL=20260905T170000Z", exdates=[parse_as_of("2026-09-03T09:00")], organizer="avery@tessera.io",
                      attendees=[Attendee(email="avery@tessera.io", partstat="ACCEPTED")])
    moved = RawEvent(uid="u", calendar="work", title="standup (moved)", start=parse_as_of("2026-09-04T14:00"), end=parse_as_of("2026-09-04T14:15"), all_day=False,
                     recurrence_id=parse_as_of("2026-09-04T09:00"), organizer="avery@tessera.io")
    out = expand_events([master, moved], parse_as_of("2026-09-10T06:00"), 30, 14, {"avery@tessera.io"}, TZ)
    assert [(e.start.strftime("%d %H:%M"), e.title) for e in out] == [("01 09:00", "standup"), ("02 09:00", "standup"), ("04 14:00", "standup (moved)"), ("05 09:00", "standup")]


def test_freshness_and_header_fragments(mini_dir):
    w = _world(mini_dir)
    f = w.freshness
    assert f["email"].state == "ok" and f["email"].latest_item_time.isoformat() == "2026-09-23T21:10:33-07:00"
    assert header_fragment(f["email"], AS_OF) == "inbox synced Wed 21:10" and header_fragment(f["calendar"], AS_OF) == "calendar ok"
    late = _world(mini_dir, parse_as_of("2026-09-26T06:00"))
    assert late.freshness["email"].state == "stale" and header_fragment(late.freshness["email"], late.as_of) == "inbox stale (2 days)"
    assert late.freshness["calendar"].state == "stale"
    hidden = normalize_world(load_world(mini_dir, AS_OF, TZ, variant="no_notes"), SETTINGS, "Avery Chen")
    assert hidden.freshness["notes"].state == "missing" and header_fragment(hidden.freshness["notes"], AS_OF) == "notes missing"


def test_owner_detection_falls_back_to_most_frequent_recipient():
    a = _raw("<1@x>", "2026-09-20T10:00", "x@y.example", ["me@corp.example"], "hi", "a")
    b = _raw("<2@x>", "2026-09-21T10:00", "z@y.example", ["me@corp.example", "other@corp.example"], "hi", "b")
    from digest.normalize.owner import detect_owner
    assert detect_owner([a, b], [], "Nobody Named") == ("me@corp.example", {"me@corp.example"})
