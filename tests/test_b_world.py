"""Track B, M1: the dev world files are well-formed and internally consistent (before any data is generated)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
import yaml

from digest.schemas import ActionType, CandidateType, Priority, RelationshipHint, Section, validate_about_key
from eval.manifest_schema import AssertionKind

WORLD = Path(__file__).resolve().parents[1] / "world" / "dev"
STORYLINES = sorted((WORLD / "storylines").glob("S*.yaml"))
LABEL_WORDS = re.compile(r"\b(trap|P0|storyline|expected)\b")
GENDERED = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE)


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def world() -> dict:
    return load(WORLD / "world.yaml")


@pytest.fixture(scope="module")
def storylines() -> list[dict]:
    return [load(p) for p in STORYLINES]


@pytest.fixture(scope="module")
def people(world) -> set[str]:
    ids = {p["id"] for p in world["people"]}
    # list aliases used in beats
    return ids | {"parents_list", "team_list", "factoryfloor", "modelwatch", "scbrief"}


def test_sixteen_storylines_all_unreviewed(storylines):
    assert len(storylines) == 16
    assert [s["id"] for s in storylines] == [f"S{i}" for i in range(1, 17)]
    assert all(s["reviewed"] is False for s in storylines), "M1 gate: nothing is reviewed until Shubham says so"


def test_world_anchor_and_run_days(world):
    assert str(world["anchor"]) == "2026-09-24"
    assert world["run_days"] == [26, 27, 28, 29, 30]
    assert world["avery"]["email"] == "avery@tessera.io"


def test_people_ids_unique_and_emails_unique(world):
    ids = [p["id"] for p in world["people"]]
    assert len(ids) == len(set(ids))
    emails = [e for p in world["people"] for e in p["emails"]]
    assert len(emails) == len(set(emails))


def test_world_never_genders_avery_or_sam(world):
    for p in world["people"]:
        if p["id"] in ("avery", "sam"):
            text = " ".join(str(v) for v in (p.get("style"), p.get("title"), p.get("signature")))
            assert not GENDERED.search(text), p["id"]


def test_beats_reference_known_people_and_have_times(storylines, people):
    for s in storylines:
        for b in s["beats"]:
            assert b["day"] >= 1 and b["day"] <= 30, (s["id"], b["ref"])
            assert re.fullmatch(r"\d{2}:\d{2}", b["time"]), (s["id"], b["ref"])
            if b["source"] == "note":
                continue  # notes have no sender
            assert b["from"] in people, (s["id"], b["ref"], b["from"])
            for who in b.get("to", []) + b.get("cc", []):
                assert who in people, (s["id"], b["ref"], who)


def test_every_email_beat_thread_is_declared(storylines):
    for s in storylines:
        declared = {t["id"] for t in s.get("threads", [])}
        for b in s["beats"]:
            if b["source"] == "email":
                assert b["thread"] in declared, (s["id"], b["ref"], b["thread"])


def test_about_keys_are_valid_everywhere(storylines):
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "about":
                    for key in (v if isinstance(v, list) else [v]):
                        if key is not None:
                            validate_about_key(key)
                elif k in ("absent", "attaches_to"):
                    for key in v or []:
                        validate_about_key(key)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    for s in storylines:
        walk(s)
    walk(load(WORLD / "background.yaml"))
    walk(load(WORLD / "variants.yaml"))


def test_expectation_vocabularies(storylines):
    priorities, sections = set(get_args(Priority)), set(get_args(Section))
    actions, ctypes = set(get_args(ActionType)), set(get_args(CandidateType))
    for s in storylines:
        for e in s["expectations"]:
            assert e["run_day"] in (26, 27, 28, 29, 30), s["id"]
            for it in e.get("items", []):
                if "priority" in it:
                    assert it["priority"] in priorities, (s["id"], it)
                for p in it.get("priority_band", []):
                    assert p in priorities
                if "section" in it:
                    assert it["section"] in sections, (s["id"], it)
                for a in it.get("actions", []) + it.get("actions_any", []):
                    assert a in actions, (s["id"], a)
            for c in e.get("candidates", []):
                assert c["type"] in ctypes, (s["id"], c)


def test_every_run_day_is_addressed_per_storyline(storylines):
    for s in storylines:
        days = {e["run_day"] for e in s["expectations"]}
        assert days == {26, 27, 28, 29, 30}, (s["id"], days)
        for e in s["expectations"]:
            assert any(k in e for k in ("items", "absent", "unasserted", "candidates")), (s["id"], e["run_day"])


def test_assertion_kinds_and_unique_ids(storylines):
    kinds = set(get_args(AssertionKind))
    seen: dict[str, str] = {}
    sources = [(s["id"], s.get("assertions", []) + s.get("simulate", [])
                + [a for v in s.get("variants", []) for a in v.get("assertions", [])]) for s in storylines]
    bg = load(WORLD / "background.yaml")
    bg_assertions = []
    for blk in bg["planted_patterns"].values():
        bg_assertions += blk.get("assertions", [])
    for case in bg["classification_cases"]:
        bg_assertions += case.get("assertions", [])
    bg_assertions += bg["background_expectations"]["assertions"]
    sources.append(("background", bg_assertions))
    for v in load(WORLD / "variants.yaml")["honesty_variants"]:
        sources.append((v["id"], v.get("assertions", [])))
    for owner, assertions in sources:
        for a in assertions:
            assert a["kind"] in kinds, (owner, a["id"], a["kind"])
            assert a["id"] not in seen, (a["id"], seen.get(a["id"]), owner)
            seen[a["id"]] = owner
    assert len(seen) > 120


def test_relationship_categories_valid(world):
    cats = set(get_args(RelationshipHint))
    for p in world["people"]:
        assert p["truth"]["category"] in cats, p["id"]


def test_no_label_words_in_must_include(storylines):
    for s in storylines:
        for b in s["beats"]:
            for phrase in b.get("must_include", []):
                assert not LABEL_WORDS.search(phrase), (s["id"], b["ref"], phrase)


def test_s3_business_day_boundary():
    """Fri 17:52 message; weekday dates strictly after the message date and strictly before the run date."""
    from datetime import date, timedelta

    anchor = date(2026, 9, 24)
    msg = anchor - timedelta(days=30 - 24)
    assert msg.weekday() == 4  # Friday

    def quiet(run_day: int) -> int:
        run = anchor - timedelta(days=30 - run_day)
        d, n = msg + timedelta(days=1), 0
        while d < run:
            n += d.weekday() < 5
            d += timedelta(days=1)
        return n

    assert [quiet(d) for d in (26, 27, 28, 29, 30)] == [0, 0, 1, 2, 3]


def test_tasks_exclude_the_planted_promises():
    notes = load(WORLD / "notes.yaml")
    task_keys = {t["labels"]["about"] for t in notes["tasks"]["items"]}
    for key in notes["tasks"]["absent"]:
        assert key not in task_keys
    assert len(notes["tasks"]["items"]) == 5
    assert len(notes["notes"]) == 10
    assert notes["tasks"]["mtime_day"] == 18
