"""Track A · router (architecture §4, OPEN_QUESTIONS #26): header facts only, no domain, name or word lists."""
from digest.normalize.router import is_automated, is_bulk, route_messages
from digest.runs import parse_as_of
from digest.schemas import NormalizedMessage


def _m(frm, subject="hi", headers=None, name="", avery=False, forwarded_by=None):
    return NormalizedMessage(message_id=f"<{frm}>", sent_at=parse_as_of("2026-09-22T10:00"), from_addr=frm, from_name=name,
                             subject=subject, headers=headers or {}, is_from_avery=avery, forwarded_by=forwarded_by)


def test_bulk_and_automated_are_header_facts():
    assert is_bulk(_m("a@b.example", headers={"List-Unsubscribe": "<mailto:x>"}))
    assert is_bulk(_m("a@b.example", headers={"Precedence": "bulk"})) and not is_bulk(_m("a@b.example"))
    assert is_automated(_m("bob@corp.example", headers={"Auto-Submitted": "auto-generated"}))
    assert not is_automated(_m("bob@corp.example", headers={"Auto-Submitted": "no"}))
    assert not is_automated(_m("dse@docusign.net")) and not is_automated(_m("noreply@anything.example")), "no address lists"


def test_routes():
    assert route_messages([_m("brief@scbrief.example", "SCB #212: model price cuts", {"List-Unsubscribe": "x"}, "The Supply Chain Brief")]) == "bulk"
    assert route_messages([_m("hello@mail.rippleboard.example", "New: automate approvals", {"Precedence": "bulk"}, "Rippleboard")]) == "bulk"
    assert route_messages([_m("bot@corp.example", "Build failed", {"Auto-Submitted": "auto-generated"})]) == "automated"
    # no header marks it as machine mail: a reader reads it, whatever the address or subject says
    assert route_messages([_m("dse@docusign.net", "Please DocuSign")]) == "human"
    assert route_messages([_m("person@google.com", "intro")]) == "human"
    assert route_messages([_m("hello@startup.example", "quick question")]) == "human"
    assert route_messages([_m("brief@scbrief.example", "Fwd: SCB", {"List-Unsubscribe": "x"}), _m("avery@tessera.io", avery=True)]) == "human"
    # a forwarded newsletter inside a human forward: the head message decides
    assert route_messages([_m("brief@scbrief.example", "SCB #1", forwarded_by="tomas@tessera.io"), _m("tomas@tessera.io", "Fwd: SCB #1")]) == "human"
