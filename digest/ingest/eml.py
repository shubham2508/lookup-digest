"""Parse one .eml file (RFC 5322) with the stdlib `email` package, policy default.

Output is a RawMessage: headers and the plain-text body as written, quoted history still inside.
Normalization (quote stripping, threading, forwards) happens in digest/normalize.
"""
from __future__ import annotations

import email
import email.utils
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

# headers the router and the extractor may look at (architecture §4); everything else is dropped
KEPT_HEADERS = (
    "List-Unsubscribe", "List-Id", "List-Post", "Precedence", "Auto-Submitted", "X-Auto-Response-Suppress",
    "Reply-To", "Return-Path", "Sender", "X-Mailer", "X-Priority", "Importance", "X-Mailgun-Tag",
    "X-SES-Outgoing", "Feedback-ID", "X-Campaign", "Content-Type",
)

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<\s*(br|/p|/div|/tr|/li|/h[1-6])\s*/?>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


@dataclass
class RawMessage:
    path: str                       # file path (for diagnostics)
    message_id: str                 # as in the header, with angle brackets: "<id@host>"
    in_reply_to: str | None
    references: list[str]
    sent_at: datetime               # aware, in the digest timezone
    from_addr: str
    from_name: str
    to: list[str]
    cc: list[str]
    subject: str
    body: str                       # plain text, quoted history still present
    headers: dict[str, str] = field(default_factory=dict)
    display_names: dict[str, str] = field(default_factory=dict)   # address → display name seen in headers

    @property
    def participants(self) -> list[str]:
        return [self.from_addr, *self.to, *self.cc]


def _bracket(mid: str) -> str:
    mid = mid.strip()
    if not mid:
        return mid
    if not mid.startswith("<"):
        mid = "<" + mid
    if not mid.endswith(">"):
        mid = mid + ">"
    return mid


def split_message_ids(value: str | None) -> list[str]:
    """'<a@x> <b@y>' → ['<a@x>', '<b@y>'] (References may be whitespace- or comma-separated)."""
    if not value:
        return []
    return [_bracket(m) for m in re.split(r"[\s,]+", value.strip()) if m.strip()]


def html_to_text(raw: str) -> str:
    raw = _STYLE_RE.sub("", raw)
    raw = _BR_RE.sub("\n", raw)
    raw = _TAG_RE.sub("", raw)
    text = html.unescape(raw)
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def _body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        if msg.get_content_maintype() == "text":
            try:
                return str(msg.get_content())
            except Exception:  # noqa: BLE001 - undecodable single-part body
                return msg.get_payload(decode=True).decode("utf-8", "replace") if msg.get_payload(decode=True) else ""
        return ""
    try:
        content = part.get_content()
    except Exception:  # noqa: BLE001 - bad charset: decode leniently
        payload = part.get_payload(decode=True) or b""
        content = payload.decode(part.get_content_charset() or "utf-8", "replace")
    if not isinstance(content, str):
        content = str(content)
    if part.get_content_subtype() == "html":
        content = html_to_text(content)
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _addresses(msg: EmailMessage, header: str) -> list[tuple[str, str]]:
    """[(addr, display name)] for To/Cc/From, lowercased addresses, order kept, blanks dropped."""
    out: list[tuple[str, str]] = []
    values = msg.get_all(header, [])
    for v in values:
        addrs = getattr(v, "addresses", None)
        if addrs is not None:
            for a in addrs:
                if a.addr_spec:
                    out.append((a.addr_spec.lower(), a.display_name or ""))
        else:
            for name, addr in email.utils.getaddresses([str(v)]):
                if addr:
                    out.append((addr.lower(), name or ""))
    return out


def parse_eml_bytes(data: bytes, path: str, tz: ZoneInfo) -> RawMessage:
    msg = email.message_from_bytes(data, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    from_list = _addresses(msg, "From")
    from_addr, from_name = from_list[0] if from_list else ("", "")
    to = _addresses(msg, "To")
    cc = _addresses(msg, "Cc")
    names = {a: n for a, n in [*from_list, *to, *cc] if n}

    date_hdr = msg.get("Date")
    sent_at: datetime | None = None
    if date_hdr:
        try:
            sent_at = email.utils.parsedate_to_datetime(str(date_hdr))
        except (TypeError, ValueError):
            sent_at = None
    if sent_at is None:
        raise ValueError(f"{path}: missing or unparseable Date header")
    sent_at = sent_at.replace(tzinfo=tz) if sent_at.tzinfo is None else sent_at.astimezone(tz)

    mid = _bracket(str(msg.get("Message-ID") or "").strip())
    if not mid:
        mid = f"<{Path(path).stem}@local.missing-id>"
    irt = split_message_ids(msg.get("In-Reply-To"))
    headers = {h: str(msg.get(h)) for h in KEPT_HEADERS if msg.get(h) is not None}
    return RawMessage(
        path=path, message_id=mid, in_reply_to=irt[0] if irt else None,
        references=split_message_ids(msg.get("References")), sent_at=sent_at,
        from_addr=from_addr, from_name=from_name, to=[a for a, _ in to], cc=[a for a, _ in cc],
        subject=str(msg.get("Subject") or "").strip(), body=_body_text(msg), headers=headers, display_names=names,
    )


def parse_eml(path: Path, tz: ZoneInfo) -> RawMessage:
    return parse_eml_bytes(path.read_bytes(), str(path), tz)
