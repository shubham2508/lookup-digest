"""Track A · M3: router (architecture §4) — headers and domains first, `unsure` when the signals are weak."""
from digest.normalize.router import is_automated, is_bulk, route_messages
from digest.runs import parse_as_of
from digest.schemas import NormalizedMessage


def _m(frm, subject="hi", headers=None, name="", avery=False, forwarded_by=None):
    return NormalizedMessage(message_id=f"<{frm}>", sent_at=parse_as_of("2026-09-22T10:00"), from_addr=frm, from_name=name,
                             subject=subject, headers=headers or {}, is_from_avery=avery, forwarded_by=forwarded_by)


def test_bulk_and_automated_signals():
    assert is_bulk(_m("a@b.example", headers={"List-Unsubscribe": "<mailto:x>"}))
    assert is_bulk(_m("a@b.example", headers={"Precedence": "bulk"})) and not is_bulk(_m("a@b.example"))
    assert is_automated(_m("dse@docusign.net")) and is_automated(_m("noreply@anything.example"))
    assert is_automated(_m("bob@corp.example", headers={"Auto-Submitted": "auto-generated"}))
    assert not is_automated(_m("renee.tan@halberd.com"))


def test_routes():
    assert route_messages([_m("brief@scbrief.example", "SCB #212: model price cuts", {"List-Unsubscribe": "x"}, "The Supply Chain Brief")]) == "newsletter"
    assert route_messages([_m("hello@mail.rippleboard.example", "New: automate approvals in one click", {"List-Unsubscribe": "x", "Precedence": "bulk"}, "Rippleboard")]) == "marketing"
    assert route_messages([_m("someone@unknown.example", "Update", {"List-Unsubscribe": "x"})]) == "unsure"
    assert route_messages([_m("dse@docusign.net", "Please DocuSign")]) == "automated"
    assert route_messages([_m("renee.tan@halberd.com", "Rollout?")]) == "human"
    assert route_messages([_m("hello@startup.example", "quick question")]) == "unsure"
    assert route_messages([_m("brief@scbrief.example", "Fwd: SCB", {"List-Unsubscribe": "x"}), _m("avery@tessera.io", avery=True)]) == "human"
    # a forwarded newsletter inside a human forward: the head message decides
    assert route_messages([_m("brief@scbrief.example", "SCB #1", forwarded_by="tomas@tessera.io"), _m("tomas@tessera.io", "Fwd: SCB #1")]) == "human"
