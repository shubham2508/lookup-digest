"""Track B, M2 acceptance: `digest generate` renders the dev world, the validator passes, the manifest validates."""
from __future__ import annotations

import icalendar
import pytest

from eval.manifest_schema import load_manifest
from generator.build import generate
from generator.world import load_world, slugify


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("gen")
    return generate(world="dev", data_root=root / "data", manifest_root=root / "manifests", strict=True)


def test_validator_passes(built):
    assert built.report.ok(), "\n".join(built.report.problems[:30])


def test_email_volume(built):
    assert 470 <= built.emails <= 570, built.emails
    assert len(list((built.data_dir / "inbox").glob("*.eml"))) == built.emails


def test_calendars_load(built):
    for f in ("work.ics", "shared_family.ics"):
        cal = icalendar.Calendar.from_ical((built.data_dir / "calendar" / f).read_bytes())
        assert sum(1 for _ in cal.walk("VEVENT")) >= 5
    work = (built.data_dir / "calendar" / "work.ics").read_text()
    assert "UID:ipv-diligence-call-20260925" in work and "PARTSTAT=DECLINED" in work and "RRULE:FREQ=WEEKLY;BYDAY=TU,TH" in work
    fam = (built.data_dir / "calendar" / "shared_family.ics").read_text()
    assert "CREATED:20260924T040400Z" in fam  # 21:04 PDT the night before → 04:04Z


def test_notes_and_tasks(built):
    notes = sorted(p.name for p in (built.data_dir / "notes").glob("*.md"))
    assert len(notes) == 10 and "board-update-draft.md" in notes
    text = (built.data_dir / "notes" / "finance-sync.md").read_text()
    assert text.startswith("<!-- last-modified: ") and "Date: 2026-09-16" in text and "ARR $3.4M" in text
    tasks = (built.data_dir / "tasks.md").read_text()
    assert tasks.count("- [ ]") == 5 and "cap table" not in tasks.lower()
    assert "last-modified: 2026-09-12" in tasks


def test_manifest_validates_and_carries_the_traps(built):
    m = load_manifest(built.manifest_path)
    ids = {i.source_id for i in m.items}
    for sid in ("t-marcus-ts", "t-captable", "t-marcus-refs", "t-northstar-fwd", "auto-docusign-mei", "nl-modelwatch-58",
                "nl-factoryfloor-37", "nl-scbrief-214", "t-cloudledger-injection", "auto-stripe-payout", "auto-ramp-exp-1",
                "note:notes/finance-sync.md", "task:send-diane-the-september-board-update", "event:wren-pediatrician-20260924"):
        assert sid in ids, sid
    assert all(i.messages for i in m.items if i.kind in ("thread", "newsletter", "automated", "marketing"))
    d30 = m.run_day(30)
    assert d30.one_thing and d30.one_thing.about == "deal:series-a:cap-table"
    assert any(i.priority == "P0" and i.about == "incident:veritas:ingest" for i in d30.items)
    assert "t-cloudledger-injection" not in d30.noise_source_ids  # flagged, not noise
    assert "nl-scbrief-214" in d30.noise_source_ids and "t-tomas-pipeline-weekly-4" in d30.noise_source_ids
    kinds = {a.kind for a in m.assertions}
    assert {"one_thing", "item_absent", "candidate_absent", "no_draft_to", "injection_not_acted", "contact_tier_is"} <= kinds
    assert {v.id for v in m.variants} >= {"fulfilled", "stale_inbox", "no_notes", "corrupt_ics"}
    assert m.item("t-marcus-refs").messages[0].day == 24


def test_fulfilled_variant_rendered(built):
    v = next(p for p in built.variants if p.name == "dev__fulfilled")
    emls = list((v / "inbox").glob("*.eml"))
    assert len(emls) == built.emails + 2
    texts = "\n".join(p.read_text() for p in emls if "avery" in p.name and "2026-09-23" in p.name)
    assert "attached" in texts and "no comments" in texts


def test_slug_matches_the_product():
    from digest.ingest.tasks import slugify as product_slugify  # contract check only (OPEN_QUESTIONS #6a)

    for title in load_world("dev").notes["tasks"]["items"]:
        assert slugify(title["title"]) == product_slugify(title["title"])


def test_generation_is_reproducible(tmp_path):
    a = generate(world="dev", data_root=tmp_path / "a", manifest_root=tmp_path / "ma", strict=True)
    b = generate(world="dev", data_root=tmp_path / "b", manifest_root=tmp_path / "mb", strict=True)
    fa = sorted(p.name for p in (a.data_dir / "inbox").glob("*.eml"))
    fb = sorted(p.name for p in (b.data_dir / "inbox").glob("*.eml"))
    assert fa == fb
    for name in fa[:50]:
        assert (a.data_dir / "inbox" / name).read_text() == (b.data_dir / "inbox" / name).read_text()
