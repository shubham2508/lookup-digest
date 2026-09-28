"""Track B, M8: the held-out world files are well-formed, internally consistent, and disguised (not a copy of dev)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import get_args

import pytest
import yaml

from digest.schemas import ActionType, CandidateType, Priority, RelationshipHint, Section, validate_about_key
from eval.manifest_schema import AssertionKind

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world" / "heldout"
DEV = ROOT / "world" / "dev"
STORYLINES = sorted((WORLD / "storylines").glob("S*.yaml"))
PROSE = WORLD / "prose"
LABEL_WORDS = re.compile(r"\b(trap|P0|P1|P2|P3|storyline|expected)\b")
GENDERED = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE)
ANCHOR = date(2026, 3, 26)
# names profile/profile.md fixes; every other person in held-out must be new
PROFILE_NAMES = {"Avery Chen", "Sam Park", "Priya Iyer", "Marcus Webb", "Diane Okafor", "Jordan Liu", "Tomás Reyes",
                 "Ben Schaffer"}


def load(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def day_date(day: int) -> date:
    return ANCHOR - timedelta(days=30 - day)


@pytest.fixture(scope="module")
def world() -> dict:
    return load(WORLD / "world.yaml")


@pytest.fixture(scope="module")
def storylines() -> list[dict]:
    return [load(p) for p in STORYLINES]


@pytest.fixture(scope="module")
def people(world) -> set[str]:
    return {p["id"] for p in world["people"]} | {"parents_list", "team_list", "eng_list"}


def test_anchor_is_thursday_and_crosses_dst(world):
    assert str(world["anchor"]) == "2026-03-26"
    assert ANCHOR.weekday() == 3
    assert day_date(1) == date(2026, 2, 25) and day_date(12) == date(2026, 3, 8)  # spring-forward inside the history
    assert world["run_days"] == [26, 27, 28, 29, 30]
    assert world["avery"]["email"] == "avery@tessera.io"


def test_people_unique_and_names_disguised(world):
    ids = [p["id"] for p in world["people"]]
    assert len(ids) == len(set(ids))
    emails = [e for p in world["people"] for e in p["emails"]]
    assert len(emails) == len(set(emails))
    dev_names = {p["name"] for p in load(DEV / "world.yaml")["people"] if p["truth"]["category"] != "automated"}
    shared = {p["name"] for p in world["people"] if p["truth"]["category"] != "automated"} & dev_names
    assert shared <= PROFILE_NAMES, f"held-out reuses dev names outside the profile: {shared - PROFILE_NAMES}"


def test_world_never_genders_avery_or_sam(world):
    for p in world["people"]:
        if p["id"] in ("avery", "sam"):
            text = " ".join(str(v) for v in (p.get("style"), p.get("title"), p.get("signature")))
            assert not GENDERED.search(text), p["id"]


def test_relationship_categories_valid(world):
    cats = set(get_args(RelationshipHint))
    for p in world["people"]:
        assert p["truth"]["category"] in cats, p["id"]


def test_sixteen_storylines_with_review_flag(storylines):
    assert [s["id"] for s in storylines] == [f"S{i}" for i in range(1, 17)]
    assert all(isinstance(s["reviewed"], bool) for s in storylines)


def test_beats_reference_known_people_and_avoid_dst_gap(storylines, people):
    for s in storylines:
        for b in s["beats"]:
            assert 1 <= b["day"] <= 30, (s["id"], b["ref"])
            assert re.fullmatch(r"\d{2}:\d{2}", b["time"]), (s["id"], b["ref"])
            assert not (b["day"] == 12 and b["time"].startswith("02:")), (s["id"], b["ref"], "DST gap")
            if b["source"] == "note":
                continue
            for who in [b["from"]] + b.get("to", []) + b.get("cc", []):
                # one-off senders are {name, email} (world/dev/prose/FORMAT.md)
                assert who in people if isinstance(who, str) else "@" in who["email"], (s["id"], b["ref"], who)


def test_every_email_beat_thread_is_declared(storylines):
    for s in storylines:
        declared = {t["id"] for t in s.get("threads", [])}
        for b in s["beats"]:
            if b["source"] == "email":
                assert b["thread"] in declared, (s["id"], b["ref"], b["thread"])


def _walk_about(obj):
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
                _walk_about(v)
    elif isinstance(obj, list):
        for x in obj:
            _walk_about(x)


def test_about_keys_are_valid_everywhere(storylines):
    for s in storylines:
        _walk_about(s)
    for name in ("background.yaml", "variants.yaml", "notes.yaml"):
        _walk_about(load(WORLD / name))


def test_expectation_vocabularies_and_every_run_day(storylines):
    priorities, sections = set(get_args(Priority)), set(get_args(Section))
    actions, ctypes = set(get_args(ActionType)), set(get_args(CandidateType))
    for s in storylines:
        assert {e["run_day"] for e in s["expectations"]} == {26, 27, 28, 29, 30}, s["id"]
        for e in s["expectations"]:
            assert any(k in e for k in ("items", "absent", "unasserted", "candidates")), (s["id"], e["run_day"])
            for it in e.get("items", []):
                assert it.get("priority", "P0") in priorities, (s["id"], it)
                assert set(it.get("priority_band", [])) <= priorities, (s["id"], it)
                assert it.get("section", "urgent") in sections, (s["id"], it)
                assert set(it.get("actions", []) + it.get("actions_any", [])) <= actions, (s["id"], it)
            for c in e.get("candidates", []):
                assert c["type"] in ctypes, (s["id"], c)


def test_only_s1_owns_the_one_thing(storylines):
    owners = {s["id"] for s in storylines for e in s["expectations"] if e.get("one_thing")}
    assert owners == {"S1"}


def test_assertion_kinds_and_unique_ids(storylines):
    kinds = set(get_args(AssertionKind))
    seen: dict[str, str] = {}
    sources = [(s["id"], s.get("assertions", []) + s.get("simulate", [])
                + [a for v in s.get("variants", []) for a in v.get("assertions", [])]) for s in storylines]
    bg = load(WORLD / "background.yaml")
    bg_assertions = [a for blk in bg["planted_patterns"].values() for a in blk.get("assertions", [])]
    bg_assertions += [a for case in bg["classification_cases"] for a in case.get("assertions", [])]
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


def test_no_label_words_in_must_include(storylines):
    for s in storylines:
        for b in s["beats"]:
            for phrase in b.get("must_include", []):
                assert not LABEL_WORDS.search(phrase), (s["id"], b["ref"], phrase)


def test_s3_business_day_boundary(storylines):
    """Weekday dates strictly after the message date and strictly before the run date (OPEN_QUESTIONS #8)."""
    s3 = next(s for s in storylines if s["id"] == "S3")
    ask = max((b for b in s3["beats"] if b.get("from") == "marcus"), key=lambda b: (b["day"], b["time"]))
    msg = day_date(ask["day"])
    assert msg.weekday() == 4  # Friday

    def quiet(run_day: int) -> int:
        run, d, n = day_date(run_day), msg + timedelta(days=1), 0
        while d < run:
            n += d.weekday() < 5
            d += timedelta(days=1)
        return n

    assert [quiet(d) for d in (26, 27, 28, 29, 30)] == [0, 0, 1, 2, 3]


def test_tasks_exclude_the_planted_promises():
    notes = load(WORLD / "notes.yaml")
    task_keys = {t["labels"]["about"] for t in notes["tasks"]["items"]}
    assert set(notes["tasks"]["absent"]) == {"deal:series-a:operating-model", "report:409a-draft"}
    assert not task_keys & set(notes["tasks"]["absent"])
    assert len(notes["tasks"]["items"]) == 5
    assert len(notes["notes"]) == 10
    assert notes["tasks"]["mtime_day"] == 18


def _prose_messages():
    for path in sorted((PROSE / "threads").glob("*.yaml")):
        doc = load(path)
        for m in doc["messages"]:
            yield path.name, doc.get("subject", ""), m
    for path in sorted((PROSE / "bulk").glob("*.yaml")):
        for it in load(path)["items"]:
            yield path.name, it.get("subject", ""), it


def test_prose_has_no_label_words_and_never_genders_avery_or_sam():
    for fname, subject, m in _prose_messages():
        text = f"{subject}\n{m.get('body', '')}"
        assert not LABEL_WORDS.search(text), (fname, m.get("id"))
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            if re.search(r"\b(Avery|Sam)\b", sentence):
                assert not GENDERED.search(sentence), (fname, m.get("id"), sentence)
    for path in sorted((PROSE / "notes").glob("*.md")):
        assert not LABEL_WORDS.search(path.read_text(encoding="utf-8")), path.name


def test_every_storyline_must_include_is_in_its_prose(storylines):
    bodies: dict[str, str] = {}
    for _, subject, m in _prose_messages():
        if m.get("beat_ref"):
            chain = "\n".join(x.get("body", "") for x in m.get("forward_of") or [])
            bodies[m["beat_ref"]] = bodies.get(m["beat_ref"], "") + f"{subject}\n{m.get('body', '')}\n{chain}"
    for s in storylines:
        for b in s["beats"]:
            if b["source"] != "email" or not b.get("must_include"):
                continue
            assert b["ref"] in bodies, (s["id"], b["ref"], "no prose message carries this beat")
            for phrase in b["must_include"]:
                assert phrase in bodies[b["ref"]], (s["id"], b["ref"], phrase)


def test_note_must_include_phrases_are_planted():
    for n in load(WORLD / "notes.yaml")["notes"]:
        text = (PROSE / "notes" / n["file"]).read_text(encoding="utf-8")
        for phrase in n.get("must_include", []):
            assert phrase in text, (n["file"], phrase)
