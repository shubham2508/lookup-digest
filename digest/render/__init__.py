"""Render (architecture §9): header line, sections in order, item grammar, action blocks, 'N other meetings',
also-pending one-liners, footer. Pure code; the format Track C's parser reads."""
from __future__ import annotations

from datetime import datetime

from ..normalize import NormalizedWorld
from ..schemas import Candidate, ComposeResult, CustomizeOverrides, Evidence, MaterializedAction, ReduceItem

SECTION_TITLES = {"urgent": "Urgent To-Do Today", "decisions": "Decisions & Approvals", "news": "AI Industry News",
                  "pulse": "Team & Product Pulse", "calendar_personal": "Calendar & Personal"}
DEFAULT_ORDER = ["urgent", "decisions", "news", "pulse", "calendar_personal"]


class CitationIndex:
    def __init__(self, world: NormalizedWorld, owner_name: str = "you"):
        self.owner_name = owner_name
        self.msgs = {f"msg:{m.message_id}": m for t in world.threads for m in t.messages}
        self.bulk = {f"msg:{m.message_id}" for t in world.threads if t.router_type in ("newsletter", "marketing", "automated") for m in t.messages}
        self.events = {}
        for e in world.events:
            self.events.setdefault(f"event:{e.uid}", e)
        self.notes = {f"note:{n.path}": n for n in world.notes}
        self.tasks = {f"task:{t.task_id}": t for t in world.tasks}
        self.owner = world.owner_emails

    @property
    def known(self) -> set[str]:
        return set(self.msgs) | set(self.events) | set(self.notes) | set(self.tasks)

    def render(self, e: Evidence) -> str | None:
        sid = e.source_id
        if sid in self.msgs:
            m = self.msgs[sid]
            if m.from_addr in self.owner:
                who = self.owner_name
            elif sid in self.bulk:
                who = m.from_name or m.from_addr.split("@")[0]
            else:
                who = m.from_name.split(" ")[0] if m.from_name else m.from_addr.split("@")[0]
            return f"[email: {who}, {m.sent_at.strftime('%a %H:%M')}]"
        if sid in self.events:
            ev = self.events[sid]
            cal = "shared" if ev.calendar == "shared_family" else "work"
            if ev.calendar == "shared_family" and ev.created:
                return f"[cal: {cal}, added {ev.created.strftime('%a %H:%M')}]"
            return f"[cal: {cal}, {ev.title}]"
        base = sid.split("#", 1)[0]
        if base in self.notes:
            return f"[note: {self.notes[base].path.rsplit('/', 1)[-1]}]"
        if sid in self.tasks:
            return f"[task: {self.tasks[sid].title}]"
        return None


ALSO_PENDING_MAX = 8  # one page: the overflow list shows its top lines and a count


def _cites(item: ReduceItem, idx: CitationIndex, limit: int = 3) -> str:
    out: list[str] = []
    for e in item.citations:
        s = idx.render(e)
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return " ".join(out)


def _end(text: str) -> str:
    t = text.strip()
    return t if t.endswith((".", "?", "!")) else t + "."


def _item_line(what: str, why: str, cites: str, bullet: bool) -> str:
    head = f"**{_end(what)}** {_end(why)}".strip() if why.strip() else f"**{_end(what)}**"
    line = f"{head} *{cites}*" if cites else head
    return f"- {line}" if bullet else line


def _one_liner(what: str, cites: str) -> str:
    return f"- **{_end(what)}** *{cites}*" if cites else f"- **{_end(what)}**"


def _action_lines(actions: list[MaterializedAction], item_id: str) -> list[str]:
    lines: list[str] = []
    for a in actions:
        if a.item_id != item_id or a.type == "profile_update":
            continue
        lines.append(f"  {a.text}")
        if a.draft:
            body = a.draft.replace("\n", " ").strip()
            lines.append(f'  "{body}"')
        if a.assumptions and a.type in ("reply", "forward_delegate", "decide"):
            lines.append("  Assumptions: " + "; ".join(a.assumptions))
    return lines


def render_digest(*, as_of: datetime, header: str, compose: ComposeResult, reduced: dict[str, ReduceItem], actions: list[MaterializedAction],
                  cands: dict[str, Candidate], world: NormalizedWorld, also_pending: list[str], outside_filter: list[str],
                  titles: dict[str, str], customize: CustomizeOverrides | None = None, header_notes: list[str] | None = None,
                  owner_name: str = "you") -> str:
    idx = CitationIndex(world, owner_name)
    items = {ci.id: ci for ci in compose.items}
    out: list[str] = [f"# Daily Digest — {as_of.strftime('%A, %B %d, %Y').replace(' 0', ' ')}", ""]
    notes = [n for n in (header_notes or []) if n.strip()]
    out.append(header + (" · " + " · ".join(notes) if notes else ""))
    out.append("")
    cited_events: set[str] = set()

    def emit_item(iid: str, bullet: bool) -> None:
        it = reduced[iid]
        ci = items.get(iid)
        what = ci.what if ci else titles.get(iid, it.about)
        why = ci.why if ci else it.why
        out.append(_item_line(what, why, _cites(it, idx), bullet))
        out.extend(_action_lines(actions, iid))
        for e in it.citations:
            if e.source_id in idx.events:
                cited_events.add(idx.events[e.source_id].uid)

    if compose.one_thing_id and compose.one_thing_id in reduced:
        out += ["## If there is one thing you must do right now", ""]
        emit_item(compose.one_thing_id, bullet=False)
        out += ["", "---", ""]
    order = list(customize.sections_order) if customize and customize.sections_order else DEFAULT_ORDER
    exclude = set(customize.sections_exclude) if customize else set()
    blocks = {s.name: s.item_ids for s in compose.sections}
    for name in order:
        if name in exclude or name not in SECTION_TITLES:
            continue
        ids = [i for i in blocks.get(name, []) if i in reduced]
        out += [f"## {SECTION_TITLES[name]}", ""]
        if name == "news" and not ids:
            out.append("Nothing today that touches your open items.")
        for iid in ids:
            emit_item(iid, bullet=True)
        if name == "calendar_personal":
            todays = [e for e in world.events if e.start.date() == as_of.date()]
            if customize and customize.calendar_full_schedule:
                if ids:
                    out.append("")
                for e in sorted(todays, key=lambda e: e.start):
                    mins = int((e.end - e.start).total_seconds() // 60)
                    out.append(f"- **{e.start.strftime('%H:%M')}** — {e.title} ({mins}m)")
            else:
                others = [e for e in todays if e.uid not in cited_events and any(a.email not in world.owner_emails for a in e.attendees)]
                if ids:
                    out.append("")
                out.append(f"{len(others)} other meeting{'s' if len(others) != 1 else ''}, nothing to act on.")
        if not ids and name not in ("news", "calendar_personal"):
            out.append("Nothing today.")
        out += ["", "---", ""]
    pending = [i for i in also_pending if i in reduced]
    if pending:
        out += [f"## Also pending ({len(pending)})", ""]
        for iid in pending[:ALSO_PENDING_MAX]:
            it = reduced[iid]
            ci = items.get(iid)
            what = ci.what if ci else titles.get(iid, it.about)
            if "sync gap" in it.why.lower() and "sync gap" not in what.lower():
                what = f"{_end(what)} May be a sync gap."   # honesty qualifiers survive the one-liner
            out.append(_one_liner(what, _cites(it, idx, 1)))
        if len(pending) > ALSO_PENDING_MAX:
            out.append(f"- …and {len(pending) - ALSO_PENDING_MAX} more lower-priority items (full list in reduce.json).")
        out += ["", "---", ""]
    outside = [i for i in outside_filter if i in reduced]
    if outside:
        out += ["## Also outside your filter", ""]
        for iid in outside:
            it = reduced[iid]
            ci = items.get(iid)
            out.append(_one_liner(ci.what if ci else titles.get(iid, it.about), _cites(it, idx, 1)))
        out += ["", "---", ""]
    footer = [a for a in actions if a.type == "profile_update"]
    if footer:
        out += ["## Suggested profile updates", ""]
        for a in footer:
            it = reduced.get(a.item_id)
            cite = _cites(it, idx, 1) if it else ""
            out.append(f"- {a.text}" + (f" *{cite}*" if cite else ""))
        out.append("")
    while out and out[-1] in ("", "---"):
        out.pop()
    return "\n".join(out).rstrip() + "\n"


__all__ = ["CitationIndex", "DEFAULT_ORDER", "SECTION_TITLES", "render_digest"]
