"""Profile compiler (architecture §5.1): profile.md → ProfileConfig via prompt P1, cached by file hash, written to
profile/profile.yaml for review. The tool never edits profile.md. Stage slices live here too."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from ..llm import LLM, LLMError, LLMOutputInvalid
from ..paths import PROFILE_DIR
from ..prompts import Prompt, load_prompt
from ..schemas import HardRules, ProfileConfig, Thresholds

META_KEY = "_meta"


@dataclass
class CompiledProfile:
    config: ProfileConfig
    source_hash: str
    cached: bool
    path: Path | None
    degraded: str | None = None     # reason, when the fallback config is in use


def profile_hash(text: str, prompt_version: str, model: str) -> str:
    return hashlib.sha256(f"{prompt_version}\n{model}\n{text}".encode()).hexdigest()[:16]


def load_compiled(path: Path, source_hash: str) -> ProfileConfig | None:
    """The reviewed YAML on disk, if it was compiled from this exact source (hand edits to it are kept)."""
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta = data.pop(META_KEY, {}) or {}
        if meta.get("source_hash") != source_hash:
            return None
        return ProfileConfig.model_validate(data)
    except (yaml.YAMLError, ValidationError, AttributeError):
        return None


def write_compiled(path: Path, cfg: ProfileConfig, source_hash: str, prompt_version: str, model: str, source: Path) -> None:
    data = cfg.model_dump(mode="json")
    data[META_KEY] = {
        "source": str(source), "source_hash": source_hash, "prompt_version": prompt_version, "model": model,
        "compiled_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": "Compiled from profile.md for review. Hand edits are kept until profile.md changes (source_hash).",
    }
    header = ("# profile.yaml — compiled from profile.md by prompts/profile_compiler.md (architecture §5.1).\n"
              "# Review this file; the tool never edits profile.md. Delete it to force a recompile.\n")
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")


def fallback_profile(text: str) -> ProfileConfig:
    """When the compiler fails twice: a minimal config so the run degrades instead of crashing (CLAUDE.md rule 5)."""
    m = re.search(r"^#\s*(.+?)(?:\s+[—–-]\s+Profile)?\s*$", text, re.M)
    person = m.group(1).strip() if m else "the owner"
    return ProfileConfig(
        person=person, company=None, timezone="America/Los_Angeles", contacts=[], facts=[],
        thresholds=Thresholds(investor_quiet_business_days=None, hiring_stall_days=None, recruiter_pattern=None),
        blocks=[], read_windows=[], standing_topics=[], judgment_rules=[], digest_prefs=[], tone=[],
        hard_rules=HardRules(never_draft_for=[], no_newsletter_items=True, recruiter_pattern_only=True,
                             cite_everything=True, flag_stale_email_hours=24),
    )


def compile_profile(llm: LLM, profile_path: Path | None = None, out_path: Path | None = None, *,
                    prompt: Prompt | None = None, write: bool = True, tag: str = "profile") -> CompiledProfile:
    profile_path = profile_path or PROFILE_DIR / "profile.md"
    out_path = out_path if out_path is not None else PROFILE_DIR / "profile.yaml"
    prompt = prompt or load_prompt("profile_compiler")
    text = profile_path.read_text(encoding="utf-8")
    model = llm.role_config(prompt.model_role).model or "?"
    h = profile_hash(text, prompt.version_tag, model)
    cached = load_compiled(out_path, h) if write else None
    if cached is not None:
        return CompiledProfile(cached, h, True, out_path)
    messages = [{"role": "system", "content": prompt.render(profile_md=text)}]
    try:
        r = llm.complete(prompt.model_role, prompt.version_tag, messages, ProfileConfig, tag=tag)
    except (LLMOutputInvalid, LLMError) as e:
        return CompiledProfile(fallback_profile(text), h, False, None, degraded=f"{type(e).__name__}: {str(e)[:200]}")
    cfg = r.output
    if write:
        write_compiled(out_path, cfg, h, prompt.version_tag, r.model, profile_path)
    return CompiledProfile(cfg, h, r.cached, out_path if write else None)


# ----------------------------------------------------------------------------- stage slices (architecture §5.1)
def contact_directory(cfg: ProfileConfig) -> list[dict]:
    """Names, emails, orgs, roles — never tiers (the extractor must not see priorities)."""
    out: list[dict] = []
    for c in cfg.contacts:
        entry: dict = {"name": c.name, "emails": list(c.emails), "category": c.category, "subtype": c.subtype}
        if c.role_at_org:
            entry["role"] = c.role_at_org.role
            entry["orgs"] = list(c.role_at_org.orgs)
        out.append(entry)
    return out






