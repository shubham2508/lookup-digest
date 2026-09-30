"""#27: the mail kind of each thread the headers leave open comes from Jev (a person, a system ask, a system FYI, list
mail); a guess below MIN_P, a Jev failure or no Jev means the thread is read. Offline: a fake decider."""
from a_fakes import AVERY, msg, thread, world

from digest.compute.jev import JevDecider, JevError
from digest.compute.routing import KINDS, MIN_P, route_by_kind
from digest.read import threads_to_read


class FakeJev:
    def __init__(self, answers=None, fail=False):
        self.answers, self.fail, self.asked = answers or {}, fail, {}

    def classify(self, task, instructions, items, options):
        self.asked = dict(items)
        assert set(options) == set(KINDS) and "none" not in options
        if self.fail:
            raise JevError("HTTP 402")
        return {k: v for k, v in self.answers.items() if k in items}


def _world():
    person = thread(msg("p1", "2026-09-23T09:00", "renee.tan@halberd.com", subject="Rollout?"))
    sign = thread(msg("d1", "2026-09-22T09:15", "dse@docusign.net", subject="Please DocuSign: Offer Letter"))
    fyi = thread(msg("r1", "2026-09-22T09:20", "receipts@stripe.com", subject="Your receipt"))
    unsure = thread(msg("u1", "2026-09-22T09:30", "ops@vendor.example", subject="Account update"))
    nl = thread(msg("n1", "2026-09-22T07:00", "brief@scbrief.example", subject="Brief #1"), router="bulk")
    mine = thread(msg("m1", "2026-09-22T08:00", "kai@northstar.example"), msg("m2", "2026-09-22T09:00", AVERY, to=["kai@northstar.example"]))
    return world([person, sign, fyi, unsure, nl, mine])


def test_jev_kinds_route_and_unsure_or_unanswered_threads_are_read():
    w = _world()
    ids = {t.messages[0].message_id: t.thread_id for t in w.threads}
    jev = FakeJev({ids["<p1>"]: ("person", 0.97), ids["<d1>"]: ("system_ask", 0.93), ids["<r1>"]: ("system_fyi", 0.91),
                   ids["<u1>"]: ("system_fyi", MIN_P - 0.1)})
    st = route_by_kind(w, jev)
    route = {t.messages[0].message_id: t.router_type for t in w.threads}
    assert route == {"<p1>": "human", "<d1>": "human", "<r1>": "automated", "<u1>": "human", "<n1>": "bulk", "<m1>": "human"}
    assert set(jev.asked) == {ids["<p1>"], ids["<d1>"], ids["<r1>"], ids["<u1>"]}, "list mail and threads the owner wrote in are facts"
    assert st.unsure == 1 and {r["by"] for r in st.rows} == {"jev", "jev_unsure"}
    assert "Please DocuSign: Offer Letter" in jev.asked[ids["<d1>"]]
    read = {t.messages[0].message_id for t in threads_to_read(w, w.as_of)}
    assert read == {"<p1>", "<d1>", "<u1>", "<m1>"}, "a system FYI is not read; a system ask and an unsure guess are"


def test_jev_failure_or_no_jev_reads_everything_the_headers_leave_open():
    for decider in (FakeJev(fail=True), None):
        w = _world()
        st = route_by_kind(w, decider)
        assert {t.router_type for t in w.threads if t.router_type != "bulk"} == {"human"}
        assert st.failed == ("HTTP 402" if decider is not None else None)


def test_classify_sends_choice_questions_without_none_in_chunks(monkeypatch, tmp_path):
    sent = []

    def post(self, body, tag, role="linker"):
        sent.append((body, tag, role))
        return {"answers": {q: {"choice": "person", "probabilities": {"person": 0.9, "bulk": 0.1}} for q in body["questions"]}}

    monkeypatch.setattr(JevDecider, "_post", post)
    items = {f"t{i}": f"thread {i}" for i in range(30)}
    out = JevDecider(api_key="x").classify("mail_kind", "classify", items, KINDS)
    assert len(sent) == 2 and len(sent[0][0]["questions"]) == 25, "25 questions per request"
    q = sent[0][0]["questions"]["t0"]
    assert q["type"] == "choice" and set(q["criteria"]) == set(KINDS) and sent[0][2] == "router"
    assert out["t29"] == ("person", 0.9)
