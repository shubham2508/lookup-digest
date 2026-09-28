"""digest.md parser (architecture §9 grammar)."""
from eval.scorer.digest_md import parse_digest, section_key
from tests.c_helpers import DAY, MINI_RUNS

MD = (MINI_RUNS / "2026-09-24T06-00" / "digest.md").read_text(encoding="utf-8")


def test_header_title_and_sections():
    d = parse_digest(MD)
    assert d.title.startswith("Daily Digest")
    assert d.header.startswith("As of Thu 06:00 PT")
    assert d.section_order == ["one_thing", "urgent", "decisions", "news", "pulse", "calendar_personal"]
    assert [len(d.sections[s]) for s in d.section_order] == [1, 1, 1, 0, 1, 2]
    assert d.prose["news"] == ["Nothing today that touches your open items."]
    assert DAY == 30


def test_items_citations_and_actions():
    d = parse_digest(MD)
    one = d.sections["one_thing"][0]
    assert one.what == "Send the updated cap table to Marcus Webb before 11:00."
    assert [c.raw for c in one.citations] == ["[email: Marcus, Tue 16:42]", "[email: Avery, Tue 21:30]"]
    assert any(a.startswith("☐") for a in one.action_lines) and any(a.startswith("↳ Forward") for a in one.action_lines)
    cal = d.sections["calendar_personal"]
    assert cal[0].citations[0].kind == "cal" and "No draft (Sam)" in cal[0].action_lines[0]
    assert all(i.citations for i in d.items)


def test_question_cards():
    d = parse_digest(MD)
    assert len(d.questions) == 1
    q = d.questions[0]
    assert (q.number, q.question, q.options, q.default, q.section) == (
        1, "Is Oct 6 firm?", ["yes, confirm", "check with Jordan first"], 1, "urgent")


def test_word_count_excludes_header_headings_actions_and_citations():
    d = parse_digest(MD)
    base = d.word_count
    more_actions = MD.replace("↳ Approve in DocuSign (~1 min).", "↳ Approve in DocuSign (~1 min). extra words here now")
    assert parse_digest(more_actions).word_count == base
    more_text = MD.replace("Task due today.", "Task due today, four more words here.")
    assert parse_digest(more_text).word_count == base + 4
    assert parse_digest("As of now\n").word_count == 0


def test_section_titles_map_to_keys():
    assert section_key("If there is one thing you must do right now:") == "one_thing"
    assert section_key("Also pending (3)") == "also_pending"
    assert section_key("Also outside your filter") == "outside_filter"
    assert section_key("Suggested profile updates") == "profile_updates"
