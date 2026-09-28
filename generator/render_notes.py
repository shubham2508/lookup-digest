"""Render notes/*.md and tasks.md from notes.yaml + prose/notes/*.md; sets mtimes and the last-modified header."""
from __future__ import annotations

import os
from pathlib import Path

from .timeline import Timeline
from .world import World


def _iso(when) -> str:
    return when.isoformat(timespec="seconds")


def write_notes(w: World, tl: Timeline, out: Path) -> list[dict]:
    notes_dir = out / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for n in w.notes["notes"]:
        body = w.note_bodies.get(n["file"])
        if body is None:
            raise FileNotFoundError(f"prose/notes/{n['file']} is missing")
        when = tl.dt(n["day"], n.get("time", "12:00"))
        if n.get("mtime_note") and "day 29" in n["mtime_note"]:
            when = tl.dt(29, "08:45")
        attendees = ", ".join(w.people[a].name if a in w.people else a for a in n.get("attendees", []))
        header = f"<!-- last-modified: {_iso(when)} -->\nDate: {tl.date(n['day']).isoformat()}"
        header += f" | Attendees: {attendees}" if attendees else " | Attendees: (none)"
        text = header + "\n\n" + body.strip("\n") + "\n"
        p = notes_dir / n["file"]
        p.write_text(text, encoding="utf-8")
        os.utime(p, (when.timestamp(), when.timestamp()))
        written.append({"file": n["file"], "path": p, "when": when, "text": text, "spec": n})
    return written


def write_tasks(w: World, tl: Timeline, out: Path) -> dict:
    t = w.notes["tasks"]
    when = tl.dt(t["mtime_day"], t.get("mtime_time", "18:00"))
    lines = [f"<!-- last-modified: {_iso(when)} -->"]
    for it in t["items"]:
        box = "x" if it.get("status") == "done" else " "
        lines.append(f"- [{box}] {it['title']} (due: {tl.date(it['due_day']).isoformat()})")
    text = "\n".join(lines) + "\n"
    p = out / t.get("file", "tasks.md")
    p.write_text(text, encoding="utf-8")
    os.utime(p, (when.timestamp(), when.timestamp()))
    return {"path": p, "when": when, "text": text, "items": t["items"]}
