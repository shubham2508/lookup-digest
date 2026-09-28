"""Input adapters: a normalized thread / note / task → one Document the extractor sees, plus the per-source text the
evidence check verifies quotes against (exactly what the model saw)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from ..ingest.notes import RawNote
from ..normalize import NormalizedWorld
from ..schemas import NormalizedMessage, NormalizedTask, NormalizedThread, RouterType


@dataclass
class Document:
    source_id: str                      # thread:<root id> | note:<path> | task:<id>
    kind: str                           # thread | note | task
    router_type: RouterType | None      # threads only
    text: str                           # rendered for the LLM
    sources: dict[str, str] = field(default_factory=dict)   # evidence source_id → text quotes must come from
    meta: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


def _stamp(dt: datetime) -> str:
    return f"{dt.isoformat(timespec='seconds')} ({dt.strftime('%a')})"


def _addr(name: str, addr: str) -> str:
    return f"{name} <{addr}>" if name else addr


def message_source_text(m: NormalizedMessage) -> str:
    parts = [m.subject or "", m.body_new or ""]
    if m.signature_block:
        parts.append(m.signature_block)
    return "\n".join(parts)


def render_message(m: NormalizedMessage, n: int) -> str:
    head = [f"--- message {n} · source_id: msg:{m.message_id}"]
    if m.forwarded_by:
        head.append(f"(forwarded by {m.forwarded_by}; original sender and time below as quoted in the forward)")
    head.append(f"from: {_addr(m.from_name, m.from_addr)}" + ("  [this is Avery]" if m.is_from_avery else ""))
    if m.to:
        head.append("to: " + ", ".join(m.to))
    if m.cc:
        head.append("cc: " + ", ".join(m.cc))
    head.append(f"sent: {_stamp(m.sent_at)}")
    head.append(f"subject: {m.subject}")
    body = m.body_new.strip() or "(empty)"
    out = "\n".join(head) + "\n\n" + body
    if m.signature_block:
        out += "\n[signature]\n" + m.signature_block.strip()
    return out


def thread_document(t: NormalizedThread, owner_email: str | None) -> Document:
    lines = [f"THREAD {t.thread_id}", f"router guess: {t.router_type}", f"messages: {len(t.messages)}",
             f"Avery's address: {owner_email or 'unknown'}", ""]
    sources: dict[str, str] = {}
    for i, m in enumerate(t.messages, 1):
        lines.append(render_message(m, i))
        lines.append("")
        sources[f"msg:{m.message_id}"] = message_source_text(m)
    return Document(source_id=t.thread_id, kind="thread", router_type=t.router_type, text="\n".join(lines).rstrip(),
                    sources=sources, meta={"message_ids": [m.message_id for m in t.messages],
                                           "last_message_by": t.messages[-1].from_addr,
                                           "last_message_at": t.messages[-1].sent_at.isoformat()})


def note_document(n: RawNote) -> Document:
    sid = f"note:{n.path}"
    head = [f"NOTE {sid}", f"title: {n.title}", f"date: {n.header_date.isoformat() if n.header_date else 'unknown'}",
            "attendees: " + (", ".join(n.attendees) if n.attendees else "unknown"),
            f"cite lines as {sid}#L<line>; quotes must not include the 'L<n>:' prefix", ""]
    body = [f"L{i}: {ln}" for i, ln in enumerate(n.text.split("\n"), 1)]
    return Document(source_id=sid, kind="note", router_type=None, text="\n".join(head + body).rstrip(),
                    sources={sid: n.text}, meta={"path": n.path, "title": n.title})


def task_document(t: NormalizedTask) -> Document:
    sid = f"task:{t.task_id}"
    line = f"- [{'x' if t.status == 'done' else ' '}] {t.title}" + (f" (due: {t.due.isoformat()})" if t.due else "")
    text = "\n".join([f"TASK {sid}", f"status: {t.status}", f"due: {t.due.isoformat() if t.due else 'none'}", "", line])
    return Document(source_id=sid, kind="task", router_type=None, text=text, sources={sid: line},
                    meta={"task_id": t.task_id, "title": t.title})


def documents_for(world: NormalizedWorld) -> list[Document]:
    docs = [thread_document(t, world.owner_email) for t in world.threads]
    docs += [note_document(n) for n in world.notes]
    docs += [task_document(t) for t in world.tasks]
    return docs


def directory_hash(directory: list[dict], standing_topics: list[str]) -> str:
    return hashlib.sha256(json.dumps({"d": directory, "t": standing_topics}, sort_keys=True).encode()).hexdigest()[:16]
