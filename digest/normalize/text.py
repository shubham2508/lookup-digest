"""Quoted-history stripping, signature split, forwarded-chain segmentation (architecture §3). Pure text, no LLM.

`segment_body` cuts a message body at the first history separator (an "On … wrote:" attribution, an Outlook
"Original Message" block, a Gmail/Apple "Forwarded message" block, or a run of `>` lines) and parses what
follows into Segments. A reply's segments are quoted history and are discarded (each message is present
separately in the inbox); a forward's segments become forwarded messages with `forwarded_by`.
"""
from __future__ import annotations

import email.utils
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser

FWD_MARKER_RE = re.compile(r"^\s*(?:-{2,}\s*Forwarded message\s*-{2,}|Begin forwarded message:|-{2,}\s*Forwarded by .*-{2,})\s*$", re.I)
ORIG_MARKER_RE = re.compile(r"^\s*(?:-{2,}\s*Original Message\s*-{2,}|_{8,})\s*$", re.I)
HEADER_LINE_RE = re.compile(r"^\s*(From|Sent|Date|To|Cc|Subject|Reply-To):\s*(.*)$", re.I)
ATTRIB_START_RE = re.compile(r"^\s*On\b")
ATTRIB_END_RE = re.compile(r"wrote:\s*$")
QUOTE_RE = re.compile(r"^\s?>\s?")
SIG_SEP_RE = re.compile(r"^-- ?$")
SENT_FROM_RE = re.compile(r"^\s*(Sent from my|Get Outlook for|Sent via)\b.*$", re.I)
FWD_SUBJECT_RE = re.compile(r"^\s*(fwd?|fw|wg|tr)\s*:", re.I)
REPLY_PREFIX_RE = re.compile(r"^\s*((re|fwd?|fw|aw|wg|tr|sv|vs)\s*:\s*)+", re.I)
NAME_RE = re.compile(r"^[A-Z][\w'.-]+(?: [A-Z][\w'.-]+){1,3}$")
TITLE_WORDS = ("partner", "ceo", "cto", "cfo", "coo", "head ", "lead", "manager", "director", "vp", "founder",
               "engineer", "counsel", "associate", "analyst", "ventures", "capital", "partners", "inc", "llc",
               "ltd", "manufacturing", "foods", "components", "@", "www.", "http", "recruit", "talent", "president",
               "officer", "procurement", "sales", "account", "customer", "success", "operations", "principal")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

TZINFOS = {"PT": -7 * 3600, "PDT": -7 * 3600, "PST": -8 * 3600, "ET": -4 * 3600, "EDT": -4 * 3600,
           "EST": -5 * 3600, "CT": -5 * 3600, "CDT": -5 * 3600, "CST": -6 * 3600, "MT": -6 * 3600,
           "MDT": -6 * 3600, "MST": -7 * 3600, "GMT": 0, "UTC": 0, "BST": 3600, "CET": 3600, "CEST": 7200}


@dataclass
class Segment:
    kind: str                           # attribution | forward | original | header | quoted
    depth: int
    from_addr: str = ""
    from_name: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    subject: str = ""
    date_text: str = ""
    sent_at: datetime | None = None
    body: str = ""                      # this segment's own text, its nested history removed
    raw_header: str = ""


def normalize_subject(subject: str) -> str:
    s = REPLY_PREFIX_RE.sub("", subject or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def is_forward_subject(subject: str) -> bool:
    return bool(FWD_SUBJECT_RE.match(subject or ""))


def parse_loose_datetime(text: str, tz: ZoneInfo) -> datetime | None:
    text = text.strip().rstrip(".").strip()
    if not text:
        return None
    try:
        dt = dateparser.parse(text, fuzzy=True, tzinfos=TZINFOS)
    except (ValueError, OverflowError, TypeError):
        try:
            dt = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _dequote(lines: list[str]) -> list[str]:
    return [QUOTE_RE.sub("", ln, count=1) if ln.lstrip().startswith(">") else ln for ln in lines]


def _is_quoted(line: str) -> bool:
    return line.lstrip().startswith(">")


def _attribution_span(lines: list[str], i: int) -> int:
    """If an 'On … wrote:' attribution starts at line i (possibly wrapped over ≤3 lines), return its end index (exclusive)."""
    if not ATTRIB_START_RE.match(lines[i]):
        return -1
    for j in range(i, min(i + 3, len(lines))):
        if not lines[j].strip() and j > i:
            return -1
        if ATTRIB_END_RE.search(lines[j]):
            return j + 1
    return -1


def _header_block_span(lines: list[str], i: int) -> int:
    """If a From:/Sent:/To:/Subject: header block starts at i, return its end (exclusive), else -1."""
    if not re.match(r"^\s*From:\s", lines[i], re.I):
        return -1
    j = i
    seen = 0
    while j < len(lines) and HEADER_LINE_RE.match(lines[j]):
        seen += 1
        j += 1
    return j if seen >= 2 else -1


def _find_separator(lines: list[str], start: int) -> tuple[int, int, str] | None:
    """First separator at or after `start`: (index, end_of_header, kind)."""
    i = start
    while i < len(lines):
        ln = lines[i]
        if FWD_MARKER_RE.match(ln):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            span = _header_block_span(lines, j)
            return i, (span if span > 0 else j), "forward"
        if ORIG_MARKER_RE.match(ln):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            span = _header_block_span(lines, j)
            return i, (span if span > 0 else j), "original"
        span = _attribution_span(lines, i)
        if span > 0:
            return i, span, "attribution"
        span = _header_block_span(lines, i)
        if span > 0:
            return i, span, "header"
        if _is_quoted(ln):
            rest = [x for x in lines[i:] if x.strip()]
            quoted = sum(1 for x in rest if _is_quoted(x))
            if rest and quoted >= max(1, int(0.6 * len(rest))):
                return i, i, "quoted"
        i += 1
    return None


def _parse_header_lines(lines: list[str], seg: Segment, tz: ZoneInfo) -> None:
    for ln in lines:
        m = HEADER_LINE_RE.match(ln)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "from":
            name, addr = email.utils.parseaddr(val)
            seg.from_addr, seg.from_name = addr.lower(), name or (val if "@" not in val else "")
            if not seg.from_addr and EMAIL_RE.search(val):
                seg.from_addr = EMAIL_RE.search(val).group(0).lower()
        elif key in ("sent", "date"):
            seg.date_text = val
            seg.sent_at = parse_loose_datetime(val, tz)
        elif key == "to":
            seg.to = [a.lower() for _, a in email.utils.getaddresses([val]) if a]
        elif key == "cc":
            seg.cc = [a.lower() for _, a in email.utils.getaddresses([val]) if a]
        elif key == "subject":
            seg.subject = val


_ATTRIB_RE = re.compile(r"^\s*On\s+(?P<rest>.+?)\s*wrote:\s*$", re.S)


def _parse_attribution(text: str, seg: Segment, tz: ZoneInfo) -> None:
    flat = " ".join(text.split())
    m = _ATTRIB_RE.match(flat)
    if not m:
        return
    rest = m.group("rest")
    em = EMAIL_RE.search(rest)
    if em:
        seg.from_addr = em.group(0).lower()
        rest_wo = rest[: em.start()].rstrip(" <(") + rest[em.end():].lstrip(">) ")
    else:
        rest_wo = rest
    try:
        dt, tokens = dateparser.parse(rest_wo, fuzzy_with_tokens=True, tzinfos=TZINFOS)
        seg.sent_at = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
        leftovers = " ".join(t.strip(" ,") for t in tokens if t.strip(" ,"))
        leftovers = re.sub(r"^(at|On)\s+", "", leftovers).strip(" ,")
        seg.from_name = leftovers
    except (ValueError, OverflowError, TypeError):
        seg.from_name = rest_wo.strip(" ,")
    seg.date_text = rest


def segment_body(body: str, tz: ZoneInfo, depth: int = 0, max_depth: int = 6) -> tuple[str, list[Segment]]:
    """→ (own text with history removed, segments of history/forwarded content in document order)."""
    lines = [ln.rstrip() for ln in body.replace("\r\n", "\n").split("\n")]
    sep = _find_separator(lines, 0)
    cut = sep[0] if sep else len(lines)
    own = [ln for ln in lines[:cut] if not _is_quoted(ln)]
    own_text = "\n".join(own).strip("\n")
    segments: list[Segment] = []
    if not sep or depth >= max_depth:
        return own_text, segments
    while sep is not None:
        start, hdr_end, kind = sep
        seg = Segment(kind=kind, depth=depth, raw_header="\n".join(lines[start:hdr_end]))
        k = hdr_end
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and _is_quoted(lines[k]):
            # the quoted run right after a header is this segment's body (de-quoted and segmented below)
            while k < len(lines) and (_is_quoted(lines[k]) or not lines[k].strip()):
                k += 1
            nxt = _find_separator(lines, k) if k < len(lines) else None
            body_end = nxt[0] if nxt else len(lines)
            if body_end > k:      # unquoted text after the run belongs to nobody: stop the segment at the run
                body_end = k
                nxt = _find_separator(lines, k)
        else:
            nxt = _find_separator(lines, max(hdr_end, start + 1))
            body_end = nxt[0] if nxt else len(lines)
        seg_lines = lines[hdr_end:body_end]
        if kind == "attribution":
            _parse_attribution(seg.raw_header, seg, tz)
        elif kind in ("forward", "original", "header"):
            _parse_header_lines(lines[start:hdr_end], seg, tz)
        inner = _dequote(seg_lines) if any(_is_quoted(x) for x in seg_lines) else seg_lines
        inner_text, nested = segment_body("\n".join(inner), tz, depth + 1, max_depth)
        seg.body = inner_text
        segments.append(seg)
        segments.extend(nested)
        sep = nxt
        if sep is not None and sep[0] <= start:
            break
    return own_text, segments




def split_signature(text: str) -> tuple[str, str | None]:
    """→ (body, signature block or None). RFC 3676 '-- ' wins; else a trailing paragraph that looks like a card."""
    lines = text.rstrip().split("\n")
    for i, ln in enumerate(lines):
        if SIG_SEP_RE.match(ln):
            body = "\n".join(lines[:i]).rstrip()
            sig = "\n".join(lines[i + 1:]).strip()
            return body, (sig or None)
    # trailing "Sent from my iPhone"
    while lines and (SENT_FROM_RE.match(lines[-1]) or not lines[-1].strip()):
        if SENT_FROM_RE.match(lines[-1]):
            sent_line = lines.pop().strip()
            body = "\n".join(lines).rstrip()
            rest_body, sig = split_signature(body)
            return rest_body, (sig + "\n" + sent_line if sig else sent_line)
        lines.pop()
    text = "\n".join(lines)
    paras = re.split(r"\n\s*\n", text.strip("\n"))
    if len(paras) < 2:
        return text.rstrip(), None
    last = [ln.strip() for ln in paras[-1].split("\n") if ln.strip()]
    if not last or len(last) > 6:
        return text.rstrip(), None
    if _looks_like_signature(last):
        body = "\n\n".join(paras[:-1]).rstrip()
        return body, "\n".join(last)
    return text.rstrip(), None


def _looks_like_signature(lines: list[str]) -> bool:
    joined = " ".join(lines)
    if any(" | " in ln for ln in lines):
        return True
    if PHONE_RE.search(joined) or URL_RE.search(joined) or EMAIL_RE.search(joined):
        return True
    if len(lines) >= 2 and NAME_RE.match(lines[0]) and any(w in lines[1].lower() for w in TITLE_WORDS):
        return True
    if len(lines) >= 2 and NAME_RE.match(lines[0]) and len(lines[1].split()) <= 6 and lines[1][:1].isupper() and len(lines) <= 4:
        # "Marcus Webb / Inflection Point Ventures"-style two-liners without a title keyword
        return not lines[1].endswith((".", "?", "!"))
    return False


def strip_quoted(body: str, tz: ZoneInfo | None = None) -> str:
    """Convenience: the message's own text with quoted history removed (signature still attached)."""
    own, _ = segment_body(body, tz or ZoneInfo("America/Los_Angeles"))
    return own


def utc_offset_hours(dt: datetime) -> float:
    off = dt.utcoffset() or timedelta(0)
    return off.total_seconds() / 3600


__all__ = ["Segment", "segment_body", "split_signature", "strip_quoted", "normalize_subject", "is_forward_subject",
           "parse_loose_datetime", "timezone"]
