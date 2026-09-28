from datetime import date

import pytest
from pydantic import ValidationError

from eval.manifest_schema import Assertion, ItemLabel, Manifest, Meta, RunDayExpectation, load_manifest


def test_mini_manifest_loads(mini_dir):
    m = load_manifest(mini_dir / "manifest.yaml")
    assert m.meta.world == "mini" and m.meta.day_to_date(30) == date(2026, 9, 24)
    assert m.meta.day_to_date(28) == date(2026, 9, 22) and m.meta.day_to_date(1) == date(2026, 8, 26)
    assert m.item("t-halberd-rollout").expected.ball_awaiting == "avery"
    assert m.item("mkt-rippleboard").must_not_surface
    rd = m.run_day(30)
    assert sum(i.one_thing for i in rd.items) == 1 and rd.one_thing.about == "deal:series-a:cap-table"
    assert {a.kind for a in m.assertions} >= {"one_thing", "no_draft_to", "item_absent", "candidate_absent"}
    assert m.sim_avery[0].intended_option == 1


def test_unknown_assertion_kind_rejected():
    with pytest.raises(ValidationError):
        Assertion(id="x", kind="made_up")


def _meta():
    return Meta(world="w", anchor=date(2026, 9, 24))


def test_duplicate_source_ids_rejected():
    items = [ItemLabel(source_id="a", kind="thread"), ItemLabel(source_id="a", kind="note")]
    with pytest.raises(ValidationError, match="duplicate item source_ids"):
        Manifest(meta=_meta(), items=items)


def test_noise_must_reference_an_item():
    with pytest.raises(ValidationError, match="not an item"):
        Manifest(meta=_meta(), items=[], run_days=[RunDayExpectation(run_day=30, noise_source_ids=["ghost"])])


def test_about_keys_in_manifest_are_validated():
    with pytest.raises(ValidationError):
        RunDayExpectation(run_day=30, absent=["Not A Key"])
