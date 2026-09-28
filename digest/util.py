"""Small shared helpers: slugs, name folding, dates."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    """ASCII-fold and lowercase: 'Tomás' → 'tomas'."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


def slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", fold(text)).strip("-")
    return s[:max_len].rstrip("-") or "x"


def norm_name(name: str) -> str:
    return " ".join(fold(name).replace(",", " ").split())


def first_name(name: str) -> str:
    return (name or "").strip().split(" ")[0] if name else ""


def domain_of(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in (addr or "") else ""


def org_from_domain(addr: str) -> str:
    """'renee.tan@halberd.com' → 'Halberd'; 'x@mail.rippleboard.example' → 'Rippleboard'."""
    dom = domain_of(addr)
    if not dom:
        return ""
    parts = dom.split(".")
    generic = {"mail", "email", "www", "hello", "go", "mkt", "info", "news", "example", "com", "io", "vc", "co", "net", "org"}
    core = [p for p in parts if p not in generic]
    label = core[-1] if core else parts[0]
    return label.capitalize()


def to_date(v: datetime | date | None) -> date | None:
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v
