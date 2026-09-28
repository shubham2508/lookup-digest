"""tasks.md: `- [ ] <title> (due: YYYY-MM-DD)` / `- [x] ...` (data_generation §7)."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..schemas import NormalizedTask
from .notes import last_modified_header

_TASK_RE = re.compile(r"^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<title>.*?)\s*(?:\(due:\s*(?P<due>\d{4}-\d{2}-\d{2})\s*\))?\s*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "task"


def parse_tasks_text(text: str, mtime: datetime | None, tz: ZoneInfo | None = None) -> list[NormalizedTask]:
    lm = last_modified_header(text, tz or (mtime.tzinfo if mtime else None))
    if lm is not None:
        mtime = lm
    tasks: list[NormalizedTask] = []
    seen: dict[str, int] = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        m = _TASK_RE.match(line)
        if not m or not m.group("title"):
            continue
        base = slugify(m.group("title"))
        n = seen.get(base, 0)
        seen[base] = n + 1
        task_id = base if n == 0 else f"{base}-{n + 1}"
        due = date.fromisoformat(m.group("due")) if m.group("due") else None
        tasks.append(NormalizedTask(task_id=task_id, title=m.group("title"), due=due,
                                    status="done" if m.group("done").lower() == "x" else "open", file_last_modified=mtime))
    return tasks


def parse_tasks(path: Path, tz: ZoneInfo) -> list[NormalizedTask]:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz)
    return parse_tasks_text(path.read_text(encoding="utf-8"), mtime, tz)
