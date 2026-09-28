"""Which address is Avery's? The profile names the person but gives no address, so it is learned from the data:
the address whose display name (From/To/Cc, calendar CN) matches the profile's person, else the most frequent
recipient. Logged per run; see OPEN_QUESTIONS.md (Track A, M3)."""
from __future__ import annotations

from collections import Counter

from ..ingest.eml import RawMessage
from ..ingest.ics import RawEvent


def _norm(name: str) -> str:
    return " ".join(name.lower().replace(",", " ").split())


def detect_owner(messages: list[RawMessage], events: list[RawEvent], person: str) -> tuple[str | None, set[str]]:
    """→ (primary address, all matching addresses)."""
    target = _norm(person)
    first = target.split(" ")[0] if target else ""
    by_name: Counter[str] = Counter()
    recipients: Counter[str] = Counter()
    for m in messages:
        for addr, name in m.display_names.items():
            if _norm(name) == target:
                by_name[addr] += 1
        for a in [*m.to, *m.cc]:
            recipients[a] += 1
    for e in events:
        for a in e.attendees:
            if _norm(a.name) == target:
                by_name[a.email] += 1
        if e.organizer_name and _norm(e.organizer_name) == target:
            by_name[e.organizer] += 1
    if by_name:
        primary = by_name.most_common(1)[0][0]
        return primary, set(by_name)
    if first:
        locals_ = [a for a in recipients if a.split("@")[0].lower().startswith(first)]
        if locals_:
            primary = max(locals_, key=lambda a: recipients[a])
            return primary, {primary}
    if recipients:
        primary = recipients.most_common(1)[0][0]
        return primary, {primary}
    return None, set()
