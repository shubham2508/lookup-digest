"""Repo-relative paths for the product. Nothing here may reference the generator's or the eval's folders."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("DIGEST_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for p in (here, *here.parents):
        if (p / "pyproject.toml").exists() and (p / "CLAUDE.md").exists():
            return p
    return Path.cwd()


ROOT = repo_root()
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
PROFILE_DIR = ROOT / "profile"
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"
CACHE_DIR = ROOT / ".cache"


def data_dir(world_name: str) -> Path:
    """The generator's OUTPUT for a world: the only data the digest reads.

    A value containing a path separator is used as a directory (relative to the repo root), so the hand-made
    fixture runs with `--world tests/fixtures/mini` while `--world dev` means data/dev.
    """
    if "/" in world_name or Path(world_name).is_absolute():
        p = Path(world_name)
        return p if p.is_absolute() else ROOT / p
    return DATA_DIR / world_name
