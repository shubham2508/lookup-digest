"""Load a world's data directory as of a timestamp (architecture §3).

Only items that exist at `as_of` are loaded: messages with Date <= as_of, events created <= as_of, notes dated
<= as_of. Every source reports a status (ok / missing / unreadable) instead of raising, so a broken calendar
or a hidden notes folder yields an honest partial digest (DESIGN_LOG §4.4). The honesty variants of
data_generation §10 are run conditions applied here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from ..schemas import NormalizedTask, SourceKind
from .eml import RawMessage, parse_eml
from .ics import RawEvent, parse_ics_bytes
from .notes import RawNote, parse_note
from .tasks import parse_tasks

SourceState = Literal["ok", "missing", "unreadable"]
VARIANTS = ("stale_inbox", "no_notes", "corrupt_ics")
STALE_INBOX_HOURS = 30  # data_generation §10: ingest ignores email after as_of − 30h


@dataclass
class SourceStatus:
    kind: SourceKind
    state: SourceState
    detail: str = ""
    items: int = 0
    skipped_future: int = 0             # items that exist on disk but are dated after as_of
    errors: list[str] = field(default_factory=list)


@dataclass
class RawWorld:
    data_dir: Path
    as_of: datetime
    variant: str | None
    messages: list[RawMessage] = field(default_factory=list)
    events: list[RawEvent] = field(default_factory=list)
    notes: list[RawNote] = field(default_factory=list)
    tasks: list[NormalizedTask] = field(default_factory=list)
    tasks_mtime: datetime | None = None
    sources: dict[str, SourceStatus] = field(default_factory=dict)


class DataMissing(Exception):
    """The world's data directory does not exist at all."""


def _load_inbox(world: RawWorld, tz: ZoneInfo, cutoff: datetime) -> None:
    inbox = world.data_dir / "inbox"
    st = SourceStatus(kind="email", state="ok")
    world.sources["email"] = st
    if not inbox.is_dir():
        st.state, st.detail = "missing", f"no inbox directory at {inbox}"
        return
    files = sorted(inbox.glob("*.eml"))
    for f in files:
        try:
            m = parse_eml(f, tz)
        except Exception as e:  # noqa: BLE001 - one bad file must not kill the run
            st.errors.append(f"{f.name}: {e}")
            continue
        if m.sent_at > cutoff:
            st.skipped_future += 1
            continue
        world.messages.append(m)
    world.messages.sort(key=lambda m: (m.sent_at, m.message_id))
    st.items = len(world.messages)
    if not files:
        st.state, st.detail = "missing", "inbox directory is empty"
    elif not world.messages and st.errors:
        st.state, st.detail = "unreadable", f"{len(st.errors)} of {len(files)} .eml files failed to parse"
    elif st.errors:
        st.detail = f"{len(st.errors)} of {len(files)} .eml files failed to parse"


def _load_calendar(world: RawWorld, tz: ZoneInfo) -> None:
    cal_dir = world.data_dir / "calendar"
    st = SourceStatus(kind="calendar", state="ok")
    world.sources["calendar"] = st
    found = 0
    for name, calendar in (("work.ics", "work"), ("shared_family.ics", "shared_family")):
        p = cal_dir / name
        if not p.exists():
            st.errors.append(f"{name}: missing")
            continue
        found += 1
        try:
            data = p.read_bytes()
            if world.variant == "corrupt_ics" and calendar == "work":
                data = data[: len(data) // 2]   # truncated mid-file (data_generation §10)
            events = parse_ics_bytes(data, calendar, tz)
        except Exception as e:  # noqa: BLE001 - unreadable calendar → reported, not raised
            st.errors.append(f"{name}: unreadable ({type(e).__name__}: {str(e)[:120]})")
            continue
        for ev in events:
            born = ev.created or ev.dtstamp
            if born is not None and born > world.as_of:
                st.skipped_future += 1
                continue
            world.events.append(ev)
    st.items = len(world.events)
    if found == 0:
        st.state, st.detail = "missing", f"no .ics files in {cal_dir}"
    elif any("unreadable" in e for e in st.errors):
        st.state = "unreadable" if not world.events else "ok"
        st.detail = "; ".join(st.errors)
    elif st.errors:
        st.detail = "; ".join(st.errors)


def _load_notes(world: RawWorld, tz: ZoneInfo) -> None:
    notes_dir = world.data_dir / "notes"
    st = SourceStatus(kind="notes", state="ok")
    world.sources["notes"] = st
    if world.variant == "no_notes":
        st.state, st.detail = "missing", "notes directory hidden (variant no_notes)"
        return
    if not notes_dir.is_dir():
        st.state, st.detail = "missing", f"no notes directory at {notes_dir}"
        return
    files = sorted(notes_dir.glob("*.md"))
    for f in files:
        try:
            n = parse_note(f, world.data_dir, tz)
        except Exception as e:  # noqa: BLE001
            st.errors.append(f"{f.name}: {e}")
            continue
        when = datetime.combine(n.header_date, datetime.min.time(), tzinfo=tz) if n.header_date else n.mtime
        if when is not None and when > world.as_of and n.header_date is not None:
            st.skipped_future += 1
            continue
        world.notes.append(n)
    st.items = len(world.notes)
    if not files:
        st.state, st.detail = "missing", "notes directory is empty"
    elif st.errors:
        st.detail = f"{len(st.errors)} of {len(files)} notes failed to parse"


def _load_tasks(world: RawWorld, tz: ZoneInfo) -> None:
    p = world.data_dir / "tasks.md"
    st = SourceStatus(kind="tasks", state="ok")
    world.sources["tasks"] = st
    if not p.exists():
        st.state, st.detail = "missing", f"no tasks.md at {p}"
        return
    try:
        world.tasks = parse_tasks(p, tz)
        world.tasks_mtime = datetime.fromtimestamp(p.stat().st_mtime, tz)
    except Exception as e:  # noqa: BLE001
        st.state, st.detail = "unreadable", str(e)
        return
    st.items = len(world.tasks)


def load_world(data_dir: Path, as_of: datetime, tz: ZoneInfo, variant: str | None = None) -> RawWorld:
    if variant is not None and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    if not data_dir.is_dir():
        raise DataMissing(f"no data directory at {data_dir}")
    world = RawWorld(data_dir=data_dir, as_of=as_of, variant=variant)
    cutoff = as_of - timedelta(hours=STALE_INBOX_HOURS) if variant == "stale_inbox" else as_of
    _load_inbox(world, tz, cutoff)
    _load_calendar(world, tz)
    _load_notes(world, tz)
    _load_tasks(world, tz)
    return world
