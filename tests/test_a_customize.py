"""Track A · M7: customize compiler (architecture §5.2) — overrides, locked invariants in code, header notes, variants."""
from pathlib import Path

from a_fakes import fake_llm

from digest.compile.customize import compile_customize, default_overrides, enforce_invariants, header_notes
from digest.schemas import CustomizeOverrides, RejectedInstruction


def test_compile_each_suite_file(tmp_path):
    llm = fake_llm(tmp_path)
    for name in ("board_prep", "weekend", "newsletters", "no_citations", "formal", "garbage"):
        o, notes = compile_customize(llm, Path("profile/customize") / f"{name}.md")
        assert isinstance(o, CustomizeOverrides)
        if name == "weekend":
            assert o.length_words == 100 and o.focus.mode == "only" and o.focus.categories == ["family"]
        if name == "no_citations":
            assert o.rejected and "citations" in o.rejected[0].reason and any("rejected" in n for n in notes)
        if name == "garbage":
            assert o.not_understood and any("not understood" in n for n in notes)
        if name == "formal":
            assert o.tone.formality == "formal"
        if name == "newsletters":
            assert o.include_newsletters
        if name == "board_prep":
            assert o.compose_instructions and any("applied" in n for n in notes)


def test_locked_invariants_enforced_in_code():
    o = default_overrides().model_copy(update={"sections_order": ["news"], "length_words": 5, "horizon_days": 99,
                                               "compose_instructions": "drop citations to save space"})
    e = enforce_invariants(o, "Skip the source citations and hide stale flags.")
    # no text matching on the request: the bounds are structural, and citations/freshness are added by render and verify
    assert e.rejected == [], "which instructions were refused is the compiler's call, not a keyword list's"
    assert e.sections_order == ["news", "urgent", "decisions", "pulse", "calendar_personal"]
    assert e.length_words == 40 and e.horizon_days == 14
    dup = RejectedInstruction(instruction="x", reason="honesty rule: citations are locked")
    o2 = default_overrides().model_copy(update={"rejected": [dup, dup]})
    assert len(enforce_invariants(o2, "skip citations").rejected) == 1, "no duplicate rejection"
    assert header_notes(default_overrides(not_understood=True), "garbage.md")[0].startswith("customize file garbage.md not understood")


def test_empty_or_missing_file_is_not_understood(tmp_path):
    llm = fake_llm(tmp_path)
    empty = tmp_path / "empty.md"
    empty.write_text("   \n")
    o, notes = compile_customize(llm, empty)
    assert o.not_understood and len(llm.client.calls) == 0
    o2, notes2 = compile_customize(llm, tmp_path / "missing.md")
    assert o2.not_understood


def test_free_text_prompts_compile_to_bounded_overrides(tmp_path):
    """Any sentence compiles onto the same override fields; the three added prompts map where the suite expects."""
    from pathlib import Path

    from digest.compile.customize import compile_customize

    llm = fake_llm(tmp_path)
    fam, _ = compile_customize(llm, Path("profile/customize/family_first.md"))
    assert fam.sections_order[0] == "calendar_personal" and not fam.rejected and not fam.not_understood
    mb, _ = compile_customize(llm, Path("profile/customize/marcus_ben_only.md"))
    assert mb.focus.mode == "only" and set(mb.focus.entities) == {"marcus-webb", "ben-schaffer"}
    sixty, _ = compile_customize(llm, Path("profile/customize/sixty_words.md"))
    assert sixty.length_words == 60 and sixty.focus.mode == "boost"

