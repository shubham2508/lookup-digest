"""Notes: markdown files whose first line may be `Date: YYYY-MM-DD | Attendees: A, B, C` (data_generation §7)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser

_HEADER_RE = re.compile(r"^\s*(?:Date:\s*(?P<date>[^|]*?))?\s*(?:\|\s*)?(?:Attendees:\s*(?P<att>.*))?\s*$", re.IGNORECASE)


@dataclass
class RawNote:
    path: str                       # relative to the data dir, posix: "notes/sprint-week.md"
    text: str                       # whole file, as written
    title: str
    header_date: date | None
    attendees: list[str] = field(default_factory=list)
    mtime: datetime | None = None   # aware


def parse_note_header(first_line: str) -> tuple[date | None, list[str]]:
    if ":" not in first_line or not re.match(r"^\s*(Date|Attendees)\s*:", first_line, re.IGNORECASE):
        return None, []
    m = _HEADER_RE.match(first_line)
    if not m:
        return None, []
    d: date | None = None
    if m.group("date") and m.group("date").strip():
        try:
            d = dateparser.parse(m.group("date").strip()).date()
        except (ValueError, OverflowError):
            d = None
    att = [a.strip() for a in (m.group("att") or "").split(",") if a.strip()]
    return d, att


def parse_note_text(text: str, rel_path: str, mtime: datetime | None) -> RawNote:
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    header_date, attendees = parse_note_header(lines[0]) if lines else (None, [])
    title = Path(rel_path).stem
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip() or title
            break
    return RawNote(path=rel_path, text=text, title=title, header_date=header_date, attendees=attendees, mtime=mtime)


def parse_note(path: Path, data_dir: Path, tz: ZoneInfo) -> RawNote:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz)
    return parse_note_text(path.read_text(encoding="utf-8"), path.relative_to(data_dir).as_posix(), mtime)
