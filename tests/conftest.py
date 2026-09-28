from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "tests" / "fixtures" / "mini"


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def mini_dir() -> Path:
    return MINI
