"""Track A · M3: profile compiler (architecture §5.1) — cached by file hash, written for review, sliced per stage."""
import json

import yaml
from a_fakes import fake_llm

from digest.compile.profile import (
    compile_profile,
    fallback_profile,
    load_compiled,
    profile_hash,
)
from digest.paths import PROFILE_DIR
from digest.prompts import load_prompt
from digest.schemas import ProfileConfig


def test_compile_writes_yaml_and_reuses_it(tmp_path):
    src = tmp_path / "profile.md"
    src.write_text("# Avery Chen — Profile\n\nI'm Avery.\n")
    out = tmp_path / "profile.yaml"
    llm = fake_llm(tmp_path)
    r = compile_profile(llm, src, out)
    assert not r.cached and r.config.person == "Avery Chen" and out.exists()
    data = yaml.safe_load(out.read_text())
    assert data["_meta"]["source_hash"] == r.source_hash and data["_meta"]["prompt_version"].startswith("profile_compiler@v")
    assert len(llm.client.calls) == 1 and "I'm Avery." in llm.client.calls[0]["messages"][0]["content"]
    # hand edits to the reviewed yaml stick until profile.md changes
    data["thresholds"]["hiring_stall_days"] = 9
    out.write_text(yaml.safe_dump(data))
    r2 = compile_profile(llm, src, out)
    assert r2.cached and r2.config.thresholds.hiring_stall_days == 9 and len(llm.client.calls) == 1
    src.write_text("# Avery Chen — Profile\n\nI'm Avery. Changed.\n")
    r3 = compile_profile(llm, src, out)
    assert not r3.cached and r3.source_hash != r.source_hash and r3.config.thresholds.hiring_stall_days == 5
    assert load_compiled(out, "nope") is None


def test_compile_degrades_to_fallback_when_output_invalid_twice(tmp_path):
    src = tmp_path / "profile.md"
    src.write_text("# Jo Doe — Profile\n")
    llm = fake_llm(tmp_path, profile_responses=["not json", "{}"])
    r = compile_profile(llm, src, tmp_path / "profile.yaml")
    assert r.degraded and r.degraded.startswith("LLMOutputInvalid") and r.config.person == "Jo Doe"
    assert not (tmp_path / "profile.yaml").exists()
    fb = fallback_profile("no heading")
    assert fb.hard_rules.cite_everything and fb.contacts == []


def test_profile_hash_changes_with_the_prompt_version():
    assert profile_hash("a", "p@v1", "m") != profile_hash("a", "p@v2", "m")


def test_prompt_p1_shape():
    p = load_prompt("profile_compiler")
    assert p.model_role == "compiler" and p.output_model == "ProfileConfig" and p.variables == ["profile_md"]
    for must in ("Extract, don't invent", "verbatim", "Gender-neutral", "Role rules stay roles"):
        assert must in p.text, must


def test_committed_profile_yaml_matches_the_frozen_profile():
    """profile/profile.yaml is the reviewed compile of profile/profile.md; it must validate and carry the hard rules."""
    path = PROFILE_DIR / "profile.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    meta = data.pop("_meta")
    cfg = ProfileConfig.model_validate(data)
    assert cfg.person == "Avery Chen" and cfg.timezone == "America/Los_Angeles"
    sam = next(c for c in cfg.contacts if c.name == "Sam Park")
    assert sam.category == "family" and sam.tier == "P0" and "never_draft" in sam.rules
    assert "Sam Park" in cfg.hard_rules.never_draft_for and cfg.hard_rules.flag_stale_email_hours == 24
    assert cfg.thresholds.investor_quiet_business_days == 3 and cfg.thresholds.hiring_stall_days == 5
    assert cfg.thresholds.recruiter_pattern.count == 3 and cfg.thresholds.recruiter_pattern.window_days == 7
    assert any(set(b.days) == {"TUE", "THU"} and b.start == "09:00" and b.end == "11:00" for b in cfg.blocks)
    role = next(c for c in cfg.contacts if c.role_at_org)
    assert role.role_at_org.orgs and "Halberd Manufacturing" in role.role_at_org.orgs and "same_day_reply" in role.rules
    assert meta["prompt_version"] == load_prompt("profile_compiler").version_tag, "profile.yaml is older than the prompt: rerun digest run"
    assert json.dumps(data)  # serializable
