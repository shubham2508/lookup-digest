"""M7: honesty variants (eval.md §5), customize suite (§6), storyline variants, scored as conditions."""
import pytest

from eval.manifest_schema import Assertion, RunDayExpectation, Variant
from eval.scorer.conditions import (
    condition_assertions,
    customize_ids,
    formality,
    honesty_ids,
    score_conditions,
    variant_manifest,
)
from eval.scorer.runner import load_views, score_world
from tests.c_helpers import DAY, MINI_RUNS, make_run, mini_manifest

RENEE = "msg:<20260922-1408.renee@halberd.com>"


@pytest.fixture(scope="module")
def manifest():
    return mini_manifest()


@pytest.fixture(scope="module")
def world(manifest):
    """The committed fixture: default run + 3 honesty variants + 6 customize runs + baseline, all day 30."""
    return score_world("tests/fixtures/mini", MINI_RUNS, manifest=manifest, customize_suite=True)


def by_id(ws):
    return {c.id: c for c in ws.conditions}


def test_every_condition_is_found_by_its_run_dir_suffix(world):
    ids = [(c.kind, c.id, c.days) for c in world.conditions]
    assert ids == [("honesty", "stale_inbox", [DAY]), ("honesty", "no_notes", [DAY]), ("honesty", "corrupt_ics", [DAY]),
                   *[("customize", s, [DAY]) for s in ("board_prep", "formal", "garbage", "newsletters", "no_citations", "weekend")]]
    assert "tasks_stale" not in by_id(world)  # built in to the world, but the mini manifest does not declare it


def test_honesty_variants(world):
    c = by_id(world)
    assert c["stale_inbox"].status == "pass" and all(a.passed for a in c["stale_inbox"].assertions)
    assert c["corrupt_ics"].status == "pass"
    assert c["corrupt_ics"].headline["p0_recall"] == pytest.approx(0.333, abs=1e-3)  # reported, not gated for honesty
    nn = c["no_notes"]
    assert nn.status == "fail"
    [bad] = [a for a in nn.assertions if a.passed is False]
    assert bad.id == "hv-nonotes-no-unhedged-status" and bad.attributed_stage == "materialize"
    assert bad.artifact_links[0].endswith("_no_notes/actions.jsonl#L3")


def test_customize_suite_passes_and_keeps_p0(world):
    c = by_id(world)
    for stem in ("board_prep", "formal", "garbage", "newsletters", "no_citations", "weekend"):
        assert c[stem].status == "pass", (stem, [(a.id, a.evidence) for a in c[stem].assertions if not a.passed])
        assert c[stem].checks["p0_kept"] == {"kept": "2/2", "lost": "none", "passed": True}
    ts = c["formal"].checks["tone_shift"]
    assert ts["pairs"] == 2 and ts["formality_customize"] > ts["formality_default"] and ts["passed"] is True


def test_customize_hiding_a_p0_fails(tmp_path, manifest):
    make_run(tmp_path, manifest, DAY, [
        {"id": "a", "about": "deal:series-a:cap-table", "priority": "P0", "placement": "one_thing"},
        {"id": "b", "about": "family:pediatrician", "priority": "P0", "section": "calendar_personal"}])
    make_run(tmp_path, manifest, DAY, [{"id": "a", "about": "deal:series-a:cap-table", "priority": "P0"}],
             suffix="customize-board_prep")
    cs = score_conditions(manifest, tmp_path, load_views(manifest, tmp_path), customize_suite=False)
    assert [c.kind for c in cs] == ["honesty"] * 3  # customize only with the suite or when the manifest names a stem
    assert all(c.status == "not run" for c in cs)
    [c] = [x for x in score_conditions(manifest, tmp_path, load_views(manifest, tmp_path), customize_suite=True)
           if x.id == "board_prep"]
    assert c.checks["p0_kept"]["passed"] is False and c.checks["p0_kept"]["lost"] == ["d30:family:pediatrician"]
    assert c.status == "fail"


def test_condition_assertions_merge_manifest_and_suites(manifest):
    m = manifest.model_copy(deep=True)
    m.assertions.append(Assertion(id="mine", kind="header_contains", variant="stale_inbox", args={"phrases": ["x"]}))
    m.variants.append(Variant(id="stale_inbox", kind="honesty", assertions=[
        Assertion(id="v-own", kind="word_count_max", args={"max": 400})]))
    ids = [a.id for a in condition_assertions(m, "honesty", "stale_inbox")]
    assert ids[:2] == ["mine", "v-own"] and "hv-stale-header" in ids
    assert honesty_ids(m)[:1] == ["stale_inbox"] and "corrupt_ics" in honesty_ids(m)
    assert customize_ids(m, True) == ["board_prep", "formal", "garbage", "newsletters", "no_citations", "weekend"]


def test_builtin_tasks_stale_is_scored_on_default_runs_when_declared(tmp_path, manifest):
    m = manifest.model_copy(deep=True)
    m.variants.append(Variant(id="tasks_stale", kind="honesty", condition={"tasks_age_days": 12}))
    make_run(tmp_path, m, DAY, [{"id": "t", "about": "report:q2-planning", "ctype": "contradiction"}],
             header="As of Thu 06:00 PT · inbox ok · tasks stale (12 days)")
    [c] = [x for x in score_conditions(m, tmp_path, load_views(m, tmp_path)) if x.id == "tasks_stale"]
    assert c.suffix is None and c.status == "pass" and "default runs" in c.notes[0]


def test_storyline_variant_uses_its_own_expectations(tmp_path, manifest):
    m = manifest.model_copy(deep=True)
    m.variants.append(Variant(id="fulfilled", kind="storyline", data_dir="data/mini__fulfilled",
                              run_days=[RunDayExpectation(run_day=30, absent=["deal:series-a:cap-table"])],
                              assertions=[Assertion(id="S1-fulfilled-absent", kind="item_absent", run_day=30,
                                                    args={"about": "deal:series-a:cap-table"})]))
    vm = variant_manifest(m, "fulfilled")
    assert vm.run_day(30).absent == ["deal:series-a:cap-table"] and m.run_day(30).absent == []
    root = tmp_path / "mini"
    make_run(root, m, DAY, [])
    make_run(tmp_path / "mini__fulfilled", m, DAY, [{"id": "k", "about": "deal:series-a:cap-table"}])
    [c] = [x for x in score_conditions(m, root, load_views(m, root)) if x.kind == "storyline"]
    assert c.status == "fail" and c.assertions[0].passed is False


def test_variant_scored_on_its_own(tmp_path, manifest):
    m = manifest.model_copy(deep=True)
    m.assertions.append(Assertion(id="v-hdr", kind="header_contains", variant="stale_inbox", run_day=30,
                                  args={"phrases": ["sync gap"]}))
    make_run(tmp_path, m, DAY, [], suffix="stale_inbox", header="As of Thu 06:00 PT · inbox 30h old: possible sync gap")
    only = score_world("x", tmp_path, suffix="stale_inbox", manifest=m)
    assert [a.id for a in only.assertions][0] == "v-hdr" and only.assertions[0].passed is True
    assert all(a.variant == "stale_inbox" for a in only.assertions)


def test_formality_heuristic():
    assert formality("renee, it'll be on.\nAvery") == 0.0
    assert formality("renee, it's on.\nAvery") == pytest.approx(0.333, abs=1e-3)  # 's is ambiguous (possessive)
    assert formality("Dear Renee,\nI am confirming the date.\nBest regards,\nAvery") == 1.0

