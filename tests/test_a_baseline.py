"""Track A · M8: the naive baseline — corpus assembly, run-dir suffix, artifacts."""
from a_fakes import TZ, fake_llm

from digest.baseline import corpus_text, run_baseline
from digest.config import load_settings
from digest.ingest import load_world
from digest.normalize import normalize_world
from digest.runs import parse_as_of


def test_corpus_text_and_truncation(mini_dir):
    world = normalize_world(load_world(mini_dir, parse_as_of("2026-09-24T06:00"), TZ), load_settings(), "Avery Chen")
    text, dropped = corpus_text(world, world.as_of)
    assert dropped == 0 and "### CALENDAR" in text and "### TASKS" in text and "will send it tonight" in text
    assert text.index("Rippleboard") < text.index("daycare closed friday"), "threads are chronological"
    small, dropped2 = corpus_text(world, world.as_of, max_chars=len(text) - 300)
    assert dropped2 >= 1 and "daycare closed friday" in small, "oldest threads are dropped first"


def test_run_baseline_writes_artifacts(tmp_path):
    llm = fake_llm(tmp_path)
    (tmp_path / "profile.md").write_text("# Avery Chen — Profile\n")
    s = run_baseline("tests/fixtures/mini", "2026-09-24T06:00", runs_dir=tmp_path / "runs", llm=llm, profile_path=tmp_path / "profile.md",
                     profile_out=tmp_path / "profile.yaml")
    d = tmp_path / "runs" / "tests/fixtures/mini" / "2026-09-24T06-00_baseline"
    assert d.is_dir() and (d / "digest.md").read_text().startswith("# Daily Digest") and (d / "verify.json").exists() and (d / "cost.json").exists()
    assert s["baseline"] is True and s["suffix"] == "baseline" and s["words"] > 0
