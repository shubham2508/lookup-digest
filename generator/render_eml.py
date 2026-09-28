"""Render prose threads and bulk items into RFC 5322 .eml files (data_generation §8)."""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .timeline import Timeline
from .world import World

_LOCAL_RE = re.compile(r"[^a-z0-9.]+")


@dataclass
class RenderedMessage:
    source_id: str                 # thread id or bulk item id
    local_id: str | None
    message_id: str
    day: int
    time: str
    sent_at: datetime
    from_email: str
    from_name: str
    to: list[str]
    cc: list[str]
    subject: str
    body: str                      # full rendered body (with quotes / forward blocks / signature)
    new_text: str                  # what the sender typed (for must_include and label-word checks)
    in_reply_to: str | None
    references: list[str]
    bulk: bool
    beat_ref: str | None
    is_from_avery: bool
    must_include: list[str]
    filename: str
    forwarded: list[dict] = field(default_factory=list)


def _fmt_addr(a: dict[str, str]) -> str:
    name = a.get("name") or ""
    if name and name != a["email"]:
        safe = name.replace('"', "")
        return f'{safe} <{a["email"]}>' if re.search(r"[^\w .'-]", safe) is None else f'"{safe}" <{a["email"]}>'
    return a["email"]


def _message_id(tl: Timeline, when: datetime, email: str, seen: set[str], salt: str) -> str:
    local, domain = email.split("@", 1)
    local = _LOCAL_RE.sub("", local.lower()) or "mail"
    stamp = when.strftime("%Y%m%d-%H%M")
    mid = f"<{stamp}.{local}@{domain}>"
    if mid in seen:
        mid = f"<{stamp}.{local}.{hashlib.sha1(salt.encode()).hexdigest()[:6]}@{domain}>"
    seen.add(mid)
    return mid


def _quote(text: str) -> str:
    return "\n".join(("> " + line) if line.strip() else ">" for line in text.rstrip("\n").split("\n"))


def _attribution(when: datetime, name: str, email: str) -> str:
    return f"On {when.strftime('%a, %b %-d, %Y at %-I:%M %p')}, {name} <{email}> wrote:"


def _forward_block(w: World, tl: Timeline, chain: list[dict]) -> str:
    """Gmail-style: header block for the newest message, its body, then nested quoted history of the older ones."""
    parts: list[str] = []
    newest = chain[-1]
    older = chain[:-1]
    fr = w.addr(newest["from"])
    when = tl.dt(newest["day"], newest["time"])
    parts.append("---------- Forwarded message ---------")
    parts.append(f"From: {_fmt_addr(fr)}")
    parts.append(f"Date: {when.strftime('%a, %b %-d, %Y at %-I:%M %p')}")
    subj = newest.get("subject") or ""
    parts.append(f"Subject: {subj}")
    parts.append("To: " + ", ".join(_fmt_addr(w.addr(x)) for x in newest.get("to", [])))
    if newest.get("cc"):
        parts.append("Cc: " + ", ".join(_fmt_addr(w.addr(x)) for x in newest["cc"]))
    parts.append("")
    body = newest["body"].rstrip("\n")
    sig = _signature(w, newest.get("from"), newest.get("signature", "none"))
    if sig:
        body += "\n\n" + sig
    parts.append(body)
    # nested history: the newest older message is quoted once, each earlier one a level deeper (Gmail style)
    nested = ""
    for msg in older:
        a = w.addr(msg["from"])
        t = tl.dt(msg["day"], msg["time"])
        b = msg["body"].rstrip("\n")
        s = _signature(w, msg.get("from"), msg.get("signature", "none"))
        if s:
            b += "\n\n" + s
        block = _attribution(t, a["name"], a["email"]) + "\n" + _quote(b)
        nested = block if not nested else (block + "\n" + _quote(nested))
    if nested:
        parts.append("")
        parts.append(nested)
    return "\n".join(parts)


def _signature(w: World, from_ref, spec) -> str:
    if spec in (None, "none", False):
        return ""
    if spec == "default" or spec is True:
        p = w.person_for(from_ref)
        return (p.signature or "").strip() if p else ""
    return str(spec).strip()


def _filename(when: datetime, from_email: str, subject: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:40] or "mail"
    local = _LOCAL_RE.sub("", from_email.split("@")[0].lower())[:20]
    return f"{when.strftime('%Y-%m-%d-%H%M')}-{local}-{slug}.eml"


def render_thread(w: World, tl: Timeline, thread: dict, seen_ids: set[str], rng: random.Random) -> list[RenderedMessage]:
    out: list[RenderedMessage] = []
    by_local: dict[str, RenderedMessage] = {}
    subject0 = thread["subject"]
    for m in thread["messages"]:
        fr = w.addr(m["from"])
        when = tl.dt(m["day"], m["time"], second=rng.randint(0, 59))
        mid = _message_id(tl, when, fr["email"], seen_ids, f"{thread['thread_id']}:{m['id']}")
        parent = by_local.get(m.get("reply_to") or "")
        subject = subject0 if parent is None else (parent.subject if parent.subject.lower().startswith("re:") else "Re: " + parent.subject)
        if m.get("subject"):
            subject = m["subject"]
        text = m["body"].rstrip("\n")
        body = text
        sig = _signature(w, m["from"], m.get("signature", "default"))
        if sig:
            body += "\n\n" + sig
        if m.get("forward_of"):
            body += "\n\n" + _forward_block(w, tl, m["forward_of"])
        if parent is not None and m.get("quotes_previous"):
            body += "\n\n" + _attribution(parent.sent_at, parent.from_name, parent.from_email) + "\n" + _quote(parent.body)
        refs = (parent.references + [parent.message_id]) if parent else []
        rm = RenderedMessage(
            source_id=thread["thread_id"], local_id=m["id"], message_id=mid, day=m["day"], time=m["time"], sent_at=when,
            from_email=fr["email"], from_name=fr["name"],
            to=[_fmt_addr(w.addr(x)) for x in m.get("to", [])], cc=[_fmt_addr(w.addr(x)) for x in m.get("cc", [])],
            subject=subject, body=body + "\n", new_text=text, in_reply_to=parent.message_id if parent else None,
            references=refs, bulk=bool(m.get("bulk")), beat_ref=m.get("beat_ref"),
            is_from_avery=fr["email"] in w.avery.emails, must_include=list(m.get("must_include") or []),
            filename=_filename(when, fr["email"], subject), forwarded=list(m.get("forward_of") or []),
        )
        by_local[m["id"]] = rm
        out.append(rm)
    return out


def render_bulk_item(w: World, tl: Timeline, item: dict, seen_ids: set[str], rng: random.Random) -> RenderedMessage:
    fr = w.addr(item["from"])
    when = tl.dt(item["day"], item["time"], second=rng.randint(0, 59))
    mid = _message_id(tl, when, fr["email"], seen_ids, item["id"])
    text = item["body"].rstrip("\n")
    body = text
    sig = _signature(w, item.get("from"), item.get("signature", "none"))
    if sig:
        body += "\n\n" + sig
    return RenderedMessage(
        source_id=item["id"], local_id=None, message_id=mid, day=item["day"], time=item["time"], sent_at=when,
        from_email=fr["email"], from_name=fr["name"],
        to=[_fmt_addr(w.addr(x)) for x in item.get("to", ["avery"])], cc=[_fmt_addr(w.addr(x)) for x in item.get("cc", [])],
        subject=item["subject"], body=body + "\n", new_text=text, in_reply_to=None, references=[],
        bulk=bool(item.get("bulk")), beat_ref=item.get("beat_ref"), is_from_avery=False,
        must_include=list(item.get("must_include") or []), filename=_filename(when, fr["email"], item["subject"]),
    )


def to_eml(tl: Timeline, m: RenderedMessage) -> str:
    """RFC 5322 text: non-ASCII display names and subjects are RFC 2047-encoded; the body is 8-bit UTF-8."""
    from email.message import EmailMessage
    from email.policy import default as default_policy

    msg = EmailMessage(policy=default_policy.clone(cte_type="8bit", max_line_length=200, linesep="\n"))
    msg["Message-ID"] = m.message_id
    msg["Date"] = tl.rfc2822(m.sent_at)
    msg["From"] = _fmt_addr({"name": m.from_name, "email": m.from_email})
    msg["To"] = ", ".join(m.to)
    if m.cc:
        msg["Cc"] = ", ".join(m.cc)
    msg["Subject"] = m.subject
    if m.in_reply_to:
        msg["In-Reply-To"] = m.in_reply_to
        msg["References"] = " ".join(m.references)
    if m.bulk:
        domain = m.from_email.split("@", 1)[1]
        msg["List-Unsubscribe"] = (f"<mailto:unsubscribe@{domain}?subject=unsubscribe>, "
                                   f"<https://{domain}/u/{hashlib.md5(m.message_id.encode()).hexdigest()[:8]}>")
        msg["Precedence"] = "bulk"
    msg.set_content(m.body, subtype="plain", charset="utf-8", cte="8bit")
    return msg.as_bytes().decode("utf-8")   # as_string() would base64 an 8-bit body; as_bytes keeps it readable


def write_eml(tl: Timeline, m: RenderedMessage, inbox: Path) -> Path:
    p = inbox / m.filename
    n = 2
    while p.exists():
        p = inbox / (m.filename[:-4] + f"-{n}.eml")
        n += 1
    p.write_text(to_eml(tl, m), encoding="utf-8")
    m.filename = p.name
    return p
