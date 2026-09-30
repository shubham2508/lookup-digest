"""Router (architecture §4): header facts only. No domain, sender-name or subject-word lists (OPEN_QUESTIONS #26).

human: the owner wrote in the thread, or nothing in the headers marks it as machine mail; a thread reader reads it.
bulk: list mail (List-Unsubscribe, List-Id or List-Post, or Precedence bulk/list/junk); the news sweep reads it.
automated: Auto-Submitted set (RFC 3834); a thread reader reads it too. What a system asks of the owner (a signature,
a failed payment) is the reader's judgment, not a keyword's."""
from __future__ import annotations

from ..schemas import NormalizedMessage, RouterType


def sender_domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def _headers(msg: NormalizedMessage) -> dict[str, str]:
    return {k.lower(): v for k, v in msg.headers.items()}


def is_bulk(msg: NormalizedMessage) -> bool:
    h = _headers(msg)
    if "list-unsubscribe" in h or "list-id" in h or "list-post" in h:
        return True
    prec = (h.get("precedence") or "").strip().lower()
    return prec in ("bulk", "list", "junk")


def is_automated(msg: NormalizedMessage) -> bool:
    auto = (_headers(msg).get("auto-submitted") or "").strip().lower()
    return bool(auto) and auto != "no"


def route_messages(messages: list[NormalizedMessage]) -> RouterType:
    """Route a thread from its messages. Anything Avery wrote in is a human thread; a forward is routed by the
    forwarding message, not by the mail it carries."""
    if any(m.is_from_avery for m in messages):
        return "human"
    first = next((m for m in messages if not m.forwarded_by), messages[0])
    if is_bulk(first):
        return "bulk"
    if is_automated(first):
        return "automated"
    return "human"
