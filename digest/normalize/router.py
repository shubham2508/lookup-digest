"""Router (architecture §4): headers and domains first; `unsure` → the extractor decides. Code only."""
from __future__ import annotations

import re

from ..schemas import NormalizedMessage, RouterType

AUTOMATED_DOMAINS = (
    "docusign.net", "docusign.com", "stripe.com", "expensify.com", "github.com", "gitlab.com", "rippling.com",
    "gusto.com", "brex.com", "ramp.com", "mercury.com", "intuit.com", "zoom.us", "calendly.com", "notion.so",
    "slack.com", "linear.app", "atlassian.net", "atlassian.com", "hubspot.com", "salesforce.com", "zendesk.com",
    "intercom.io", "pagerduty.com", "datadoghq.com", "sentry.io", "vercel.com", "amazonaws.com", "hellosign.com",
    "dropbox.com", "box.com", "greenhouse.io", "lever.co", "ashbyhq.com", "carta.com", "pulley.com", "bill.com",
    "adp.com", "1password.com", "okta.com", "google.com", "microsoft.com", "apple.com", "quickbooks.com",
    "rippleboard.example", "calendar.google.com",
)
AUTOMATED_LOCALS = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "do_not_reply", "notifications",
                    "notification", "alerts", "alert", "mailer-daemon", "postmaster", "receipts", "billing", "dse",
                    "calendar-notification", "invitations", "system", "bot", "automated", "robot")
NEWSLETTER_DOMAINS = ("substack.com", "beehiiv.com", "ghost.io", "buttondown.email", "list-manage.com",
                      "convertkit.com", "getrevue.co", "stratechery.com", "axios.com", "morningbrew.com")
NEWSLETTER_WORDS = ("newsletter", "brief", "digest", "weekly", "daily", "issue", "edition", "roundup", "dispatch",
                    "bulletin", "recap", "insider", "letter", "memo", "review")
MARKETING_LOCALS = ("hello", "marketing", "news", "team", "product", "updates", "promo", "promotions", "offers", "sales",
                    "growth", "success", "community", "info", "welcome", "onboarding", "email", "mail", "campaigns",
                    "deals", "events", "webinars", "learn")
MARKETING_SUBDOMAINS = ("mail.", "email.", "mkt.", "go.", "e.", "em.", "marketing.", "info.", "promo.", "news.", "hello.")
MARKETING_WORDS = ("% off", "webinar", "new:", "introducing", "upgrade", "free trial", "last chance", "what's new",
                   "whats new", "now available", "limited time", "discount", "black friday", "pricing", "demo", "unlock",
                   "announcing", "we've launched", "just launched", "new feature", "product update", "sale ends")
_ISSUE_RE = re.compile(r"(#\s?\d{1,4}\b|\bissue\s+\d+|\bno\.\s?\d+|\bvol\.?\s?\d+)", re.I)


def sender_domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def sender_local(addr: str) -> str:
    return addr.split("@", 1)[0].lower() if "@" in addr else addr.lower()


def _domain_in(domain: str, suffixes: tuple[str, ...]) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in suffixes)


def is_bulk(msg: NormalizedMessage) -> bool:
    h = {k.lower(): v for k, v in msg.headers.items()}
    if "list-unsubscribe" in h or "list-id" in h or "list-post" in h:
        return True
    prec = (h.get("precedence") or "").strip().lower()
    return prec in ("bulk", "list", "junk")


def is_automated(msg: NormalizedMessage) -> bool:
    h = {k.lower(): v for k, v in msg.headers.items()}
    auto = (h.get("auto-submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    dom, local = sender_domain(msg.from_addr), sender_local(msg.from_addr)
    if _domain_in(dom, AUTOMATED_DOMAINS) and not is_bulk(msg):
        return True
    return local in AUTOMATED_LOCALS or local.startswith(("noreply", "no-reply", "notifications", "no_reply", "donotreply"))


def _bulk_kind(msg: NormalizedMessage) -> RouterType:
    dom, local = sender_domain(msg.from_addr), sender_local(msg.from_addr)
    text = f"{msg.from_name} {local} {msg.subject}".lower()
    news = 0
    mkt = 0
    if _domain_in(dom, NEWSLETTER_DOMAINS):
        news += 2
    news += sum(1 for w in NEWSLETTER_WORDS if w in text)
    if _ISSUE_RE.search(msg.subject):
        news += 1
    if local in MARKETING_LOCALS:
        mkt += 1
    if any(dom.startswith(p) for p in MARKETING_SUBDOMAINS):
        mkt += 1
    mkt += sum(1 for w in MARKETING_WORDS if w in text)
    if news > mkt:
        return "newsletter"
    if mkt > news:
        return "marketing"
    return "unsure"


def route_messages(messages: list[NormalizedMessage]) -> RouterType:
    """Route a thread from its messages. Anything Avery wrote in is a human thread."""
    if any(m.is_from_avery for m in messages):
        return "human"
    first = next((m for m in messages if not m.forwarded_by), messages[0])
    if is_bulk(first):
        return _bulk_kind(first)
    if is_automated(first):
        return "automated"
    local = sender_local(first.from_addr)
    if local in MARKETING_LOCALS and len(messages) == 1:
        return "unsure"
    return "human"
