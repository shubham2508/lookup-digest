"""Matching rules the whole scorer relies on (eval/scorer/match.py)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from eval.scorer.match import (
    SourceIndex,
    about_match,
    contains_phrase,
    date_within,
    expected_dt,
    majority_source,
    max_priority,
    type_matches,
)
from tests.c_helpers import mini_manifest

PT = ZoneInfo("America/Los_Angeles")


def test_about_match_uses_the_compute_merge_rule():
    m = mini_manifest()
    for a, b in m.about_keys.should_merge:
        assert about_match(a, b)
    for a, b in m.about_keys.should_not_merge:
        assert not about_match(a, b)
    assert not about_match("offer:mei-tanaka", "candidate:mei-tanaka")  # kind must agree
    assert about_match("offer:mei-tanaka", "OFFER:mei-tanaka")
    assert not about_match(None, "offer:x")


def test_type_matches_prefix_for_calendar_conflicts():
    assert type_matches("calendar_conflict:family", "calendar_conflict")
    assert type_matches("reply_owed", "reply_owed")
    assert not type_matches("reply_owed_x", "reply_owed")
    assert not type_matches(None, "reply_owed")


def test_source_index_maps_every_evidence_form():
    idx = SourceIndex(mini_manifest())
    assert idx.resolve("msg:<20260922-1642.marcus@inflectionpoint.vc>") == "t-marcus-captable"
    assert idx.resolve("msg:20260922-1642.marcus@inflectionpoint.vc") == "t-marcus-captable"
    assert idx.resolve("<20260922-2130.avery@tessera.io>") == "t-marcus-captable"
    assert idx.resolve("thread:<20260923-2110.sam@parkfamily.example>") == "t-sam-daycare"
    assert idx.resolve("t-halberd-rollout") == "t-halberd-rollout"
    assert idx.resolve("event:lumen-demo@x") is None   # the mini manifest has no event items


def test_event_ids_resolve_with_or_without_a_domain():
    from eval.manifest_schema import ItemLabel

    m = mini_manifest()
    m.items.append(ItemLabel(source_id="event:lumen-demo-20260924", kind="event"))
    idx = SourceIndex(m)
    assert idx.resolve("event:lumen-demo-20260924") == "event:lumen-demo-20260924"
    assert idx.resolve("event:lumen-demo-20260924@lumenanalytics.example") == "event:lumen-demo-20260924"
    assert idx.resolve("event:lumen-demo-20260924#2026-09-24") == "event:lumen-demo-20260924"
    assert idx.resolve("event:other") is None
    assert idx.resolve("msg:<unknown@x>") is None
    assert majority_source(idx, ["msg:<20260922-1408.renee@halberd.com>", "msg:<20260922-1642.marcus@inflectionpoint.vc>",
                                 "msg:<20260922-2130.avery@tessera.io>"]) == "t-marcus-captable"


def test_dates_match_within_granularity():
    m = mini_manifest()
    exp = expected_dt(m, 28, "23:59")
    assert exp == datetime(2026, 9, 22, 23, 59, tzinfo=PT)
    assert date_within("2026-09-22T20:00:00-07:00", exp, "day") is True
    assert date_within("2026-09-23T01:00:00-07:00", exp, "day") is False
    assert date_within("2026-09-26T09:00:00-07:00", exp, "week") is True
    assert date_within(None, exp, "day") is False
    assert date_within("2026-09-22T20:00:00-07:00", exp, "unknown") is None
    assert date_within("2026-09-22T20:00:00-07:00", None, "day") is None


def test_phrases_and_priorities():
    assert contains_phrase("Moved to  MONDAY, not Friday", ["monday", "Mon"])
    assert not contains_phrase("Friday only", "monday")
    assert max_priority(["P2", None, "P0", "P1"]) == "P0"
    assert max_priority([]) is None
