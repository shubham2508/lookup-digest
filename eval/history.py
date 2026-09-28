"""eval/history.md: one row per prompt change with the headline metrics before → after (CLAUDE.md rule 10)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

HISTORY = Path(__file__).resolve().parent / "history.md"
COLUMNS = ("p0_recall", "traps_passed", "must_not_rate", "one_thing_accuracy", "cost_per_run")


def _cell(before: dict, after: dict, key: str) -> str:
    b, a = before.get(key), after.get(key)
    fmt = lambda v: "—" if v is None else (f"{v:.3g}" if isinstance(v, float) else str(v))  # noqa: E731
    return fmt(a) if b is None else f"{fmt(b)} → {fmt(a)}"


def append(on: date | str, prompt: str, version: int | str, before: dict, after: dict, note: str = "",
           path: Path | None = None) -> str:
    """Append one row; `before`/`after` are WorldScore.headline() dicts. Returns the row written."""
    p = path or HISTORY
    row = "| " + " | ".join([str(on), prompt, str(version), *(_cell(before, after, k) for k in COLUMNS),
                             note.replace("|", "/")]) + " |"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    p.write_text(text + row + "\n", encoding="utf-8")
    return row
