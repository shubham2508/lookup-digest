"""Notes: markdown files whose first line may be `Date: YYYY-MM-DD | Attendees: A, B, C` (data_generation §7)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser

LAST_MODIFIED_RE = re.compile(r"<!--\s*last-modified:\s*([^>]+?)\s*-->", re.IGNORECASE)


def last_modified_header(text: str, tz: ZoneInfo | None = None) -> datetime | None:
    """OPEN_QUESTIONS #6c: the generator writes `<!-- last-modified: <ISO> -->` as the first line; it beats the file mtime."""
    m = LAST_MODIFIED_RE.search(text[:300])
    if not m:
        return None
    try:
        dt = dateparser.parse(m.group(1).strip())
    except (ValueError, OverflowError):
        return None
    if dt.tzinfo is None and tz is not None:
        dt = dt.replace(tzinfo=tz)
    return dt


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


def parse_note_text(text: str, rel_path: str, mtime: datetime | None, tz: ZoneInfo | None = None) -> RawNote:
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    lm = last_modified_header(text, tz or (mtime.tzinfo if mtime else None))
    if lm is not None:
        mtime = lm
    first = 1 if lines and LAST_MODIFIED_RE.match(lines[0].strip()) else 0
    header_date, attendees = parse_note_header(lines[first]) if len(lines) > first else (None, [])
    title = Path(rel_path).stem
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip() or title
            break
    return RawNote(path=rel_path, text=text, title=title, header_date=header_date, attendees=attendees, mtime=mtime)


def parse_note(path: Path, data_dir: Path, tz: ZoneInfo) -> RawNote:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz)
    return parse_note_text(path.read_text(encoding="utf-8"), path.relative_to(data_dir).as_posix(), mtime, tz)
