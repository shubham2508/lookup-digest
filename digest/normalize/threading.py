"""Threading: Message-ID / In-Reply-To / References, falling back to normalized subject + participants (architecture §3).

Thread ids are `thread:<root Message-ID without brackets>` where the root is the earliest real (non-forwarded)
message of the group, so anyone holding the .eml files can recompute the same id.
"""
from __future__ import annotations

from ..ingest.eml import RawMessage
from .text import normalize_subject


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def strip_brackets(mid: str) -> str:
    return mid.strip().strip("<>").strip()


def thread_id_for(root_message_id: str) -> str:
    return f"thread:{strip_brackets(root_message_id)}"


def group_messages(messages: list[RawMessage], owner_emails: set[str], bulk: set[str]) -> dict[str, list[RawMessage]]:
    """→ {thread_id: [messages, chronological]}. `bulk` = message ids that never thread by subject."""
    uf = _UnionFind()
    by_id = {m.message_id: m for m in messages}
    linked: set[str] = set()
    for m in messages:
        uf.find(m.message_id)
        for ref in ([m.in_reply_to] if m.in_reply_to else []) + m.references:
            if ref and ref != m.message_id:
                uf.union(m.message_id, ref)
                linked.add(m.message_id)
    # fallback: subject + participants, for unlinked non-bulk messages, in time order
    groups_meta: dict[str, dict] = {}   # root → {"subject": str, "participants": set}
    for m in sorted(messages, key=lambda x: (x.sent_at, x.message_id)):
        root = uf.find(m.message_id)
        subj = normalize_subject(m.subject)
        others = {p for p in m.participants if p and p not in owner_emails}
        if m.message_id not in linked and m.message_id not in bulk and subj:
            for other_root, meta in list(groups_meta.items()):
                if other_root == root:
                    continue
                if meta["subject"] == subj and (meta["participants"] & others or not others and not meta["participants"]):
                    uf.union(other_root, root)
                    root = uf.find(root)
                    merged = groups_meta.pop(other_root)
                    meta = groups_meta.setdefault(root, {"subject": subj, "participants": set()})
                    meta["participants"] |= merged["participants"]
                    break
        meta = groups_meta.setdefault(root, {"subject": subj, "participants": set()})
        meta["participants"] |= others
        if not meta["subject"]:
            meta["subject"] = subj
    buckets: dict[str, list[RawMessage]] = {}
    for m in messages:
        buckets.setdefault(uf.find(m.message_id), []).append(m)
    out: dict[str, list[RawMessage]] = {}
    for msgs in buckets.values():
        msgs.sort(key=lambda x: (x.sent_at, x.message_id))
        out[thread_id_for(msgs[0].message_id)] = msgs
    del by_id
    return dict(sorted(out.items(), key=lambda kv: (kv[1][0].sent_at, kv[0])))
