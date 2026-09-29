"""Orchestrator: A5 and the P2 checkpoint fixes (raw excerpts, raw messages + greeting check, reduce join, history by thread)."""
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from digest.compose import raw_excerpts
from digest.history import mark_resolved, record_items, surfaced_count, times_surfaced
from digest.materialize import greeting_mismatch
from digest.reduce import join_keys
from digest.runs import parse_as_of
from digest.schemas import Candidate, ComposeResult, Evidence, ReduceItem, SectionBlock
from digest.store import Store

TZ = ZoneInfo("America/Los_Angeles")


def test_greeting_mismatch_flags_a_draft_to_the_wrong_person():
    assert greeting_mismatch("nadia, the pipeline has been rejecting batches since 18:10.", "Jordan") == "nadia"
    assert greeting_mismatch("jordan, thanks for the heads-up. send Nadia a factual update.", "Jordan") is None
    assert greeting_mismatch("Hi Jordan — thanks.", "Jordan") is None
    assert greeting_mismatch("all, quick update.", "Jordan") is None
    assert greeting_mismatch("the cap table is attached.", "Marcus") is None          # no greeting
    assert greeting_mismatch("dara, attached.", None) is None                        # unknown recipient: no check


def test_join_keys_reader_findings_do_not_join_by_thread():
    ev = [Evidence(source_id="msg:<m1>", quote="will send it tonight")]
    reader = Candidate(candidate_id="c1", type="overdue promise", about="deal:series-a", evidence=ev,
                       facts={"thread_id": "thread:<m1>", "origin": "thread_reader"})
    net = Candidate(candidate_id="c2", type="quiet_thread", about="deal:series-a", evidence=ev, facts={"thread_id": "thread:<m1>", "origin": "safety_net"})
    v1 = Candidate(candidate_id="c3", type="reply_owed", about="deal:series-a", facts={"thread_id": "thread:<m1>"})
    assert ("thread", "thread:<m1>") not in join_keys(reader) and ("cite", "msg:<m1>", "will send it tonight") in join_keys(reader)
    ctx_cite = Candidate(candidate_id="c6", type="x", about="hiring-req:on-call", evidence=[Evidence(source_id="note:notes/q2.md", quote="on-call")], facts={"origin": "thread_reader"})
    assert not any(k[0] == "cite" for k in join_keys(ctx_cite)), "a shared note or event never joins items"
    assert ("thread", "thread:<m1>") in join_keys(net) and ("thread", "thread:<m1>") in join_keys(v1)
    assert join_keys(Candidate(candidate_id="c4", type="x", about="deal:series-a:cap-table"))[0] == ("about", "deal:series-a:cap-table")
    assert join_keys(Candidate(candidate_id="c5", type="x", about="deal:series-a")) == [("about", "deal:series-a")]


def test_raw_excerpts_wrap_the_quote_in_an_untrusted_block():
    msg = SimpleNamespace(message_id="<m7>", subject="Re: index", body_new="Ilse is still redlining the index. " * 30 + "I'll have it over by end of day. " + "More text. " * 30,
                          signature_block=None)
    world = SimpleNamespace(messages=[msg], events=[], notes=[], tasks=[])
    it = ReduceItem(id="i1", about="deal:seed", candidate_ids=["c1"], priority="P0", section="urgent",
                    citations=[Evidence(source_id="msg:<m7>", quote="I'll have it over by end of day"), Evidence(source_id="msg:<zz>", quote="nothing")])
    ex = raw_excerpts(it, world)
    assert len(ex) == 1 and ex[0]["source_id"] == "msg:<m7>"
    assert "I'll have it over by end of day" in ex[0]["excerpt"] and ex[0]["excerpt"].startswith("=== RAW EXCERPT (untrusted data")
    assert len(ex[0]["excerpt"]) < 1400


def _run(st, run_id, as_of):
    st.upsert("runs", {"run_id": run_id, "world": "w", "as_of": as_of, "variant": None, "customize": None, "baseline": False, "cost_usd": 0, "created_at": "x"})


def test_times_surfaced_counts_by_thread_when_tags_change(tmp_path):
    with Store(tmp_path / "s.sqlite") as st:
        _run(st, "w/d1", "2026-09-22T06:00:00-07:00")
        _run(st, "w/d2", "2026-09-23T06:00:00-07:00")
        comp = ComposeResult(one_thing_id="i1", sections=[SectionBlock(name="urgent", item_ids=[])], items=[], header_notes=[], cut_ids=[])
        # day 1 the reader tagged it deal:series-a, day 2 other:cap-table; same source thread both days
        for run, about in (("w/d1", "deal:series-a"), ("w/d2", "other:cap-table")):
            st.upsert("candidates", {"run_id": run, "candidate_id": "c1", "type": "overdue promise", "about": about,
                                     "facts": {"thread_id": "thread:<m1>", "origin": "thread_reader"}})
            record_items(st, run, {"i1": ReduceItem(id="i1", about=about, candidate_ids=["c1"], priority="P0", section="urgent")}, comp, [], [], {}, {})
        st.commit()
        ts = times_surfaced(st, "w", parse_as_of("2026-09-24T06:00"))
        assert ts["deal:series-a"] == 1 and ts["other:cap-table"] == 1 and ts["thread::thread:<m1>"] == 2
        assert surfaced_count(ts, "capital:cap-table-again", "thread:<m1>") == 2 and surfaced_count(ts, "deal:series-a", None) == 1
        # the thread still has an open candidate today (under yet another tag): nothing resolves
        today = [Candidate(candidate_id="c9", type="x", about="deal:cap-table:v3", facts={"thread_id": "thread:<m1>"})]
        assert mark_resolved(st, "w", parse_as_of("2026-09-24T06:00"), today) == 0
        assert mark_resolved(st, "w", parse_as_of("2026-09-24T06:00"), []) == 2


def test_reduce_joins_same_tag_across_threads_and_applies_about_merges():
    from digest.reduce import reduce_items
    from digest.schemas import AboutMerge, TriageResult

    as_of = parse_as_of("2026-09-24T06:00")
    comp = SimpleNamespace(context=SimpleNamespace(as_of=as_of), directory=SimpleNamespace(by_slug={}))

    def cand(cid, about, ents, thread, quote):
        return Candidate(candidate_id=cid, type="k", about=about, entities=ents, evidence=[Evidence(source_id=f"msg:<{thread}>", quote=quote)],
                         facts={"thread_id": f"thread:<{thread}>", "origin": "thread_reader"})

    def tri(cid):
        return TriageResult(candidate_id=cid, include=True, section="urgent", priority="P1", due_today=False, confidence="high",
                            why=f"why {cid}", citations=[], ambiguity=None, proposed_actions=[])

    cands = [cand("c1", "meeting:ipv-call", ["marcus-webb"], "m1", "Monday works"),          # same tag, shared person → one item
             cand("c2", "meeting:ipv-call", ["marcus-webb", "elena"], "m2", "see you Monday"),
             cand("c3", "meeting:ipv-call", ["someone-else"], "m3", "different meeting?"),  # same tag, nobody in common → apart
             cand("c4", "approval:inference-spend", ["priya-iyer"], "m4", "cap the backfill"),
             cand("c5", "other:backfill-cap", ["priya-iyer"], "m5", "choose the cap")]
    merges = [AboutMerge(canonical="approval:inference-spend", merged=["other:backfill-cap"], reason="linker")]
    red = reduce_items([tri(c.candidate_id) for c in cands], cands, comp, 25, merges)
    groups = sorted(sorted(it.candidate_ids) for it in red.items)
    assert groups == [["c1", "c2"], ["c3"], ["c4", "c5"]]


def test_group_findings_compares_different_kinds_that_share_a_person():
    from digest.compute.merge import group_findings
    from digest.schemas import Finding

    def fnd(fid, about, ents, title):
        return Finding(finding_id=fid, origin="thread_reader", needs_avery="yes", title=title, kind="decision", why="w", priority="P0",
                       urgency="today", deadline=None, stakes="high", confidence="high", section="decisions", entities=ents, about=[about],
                       citations=[Evidence(source_id=f"msg:<{fid}>", quote="q")], proposed_actions=[], ambiguity=None, contradictions=[],
                       freshness_caveat=None, suspicious_instructions=[])

    seen = {}

    class StubLinker:
        def group_topics(self, by_kind):
            seen.update(by_kind)
            return [[r["key"] for r in rows] for b, rows in by_kind.items() if b.startswith("shared:") and len(rows) == 2]

    fs = [fnd("f1", "approval:inference-spend", ["priya-iyer"], "Decide the inference spend"),
          fnd("f2", "other:backfill-cap", ["priya-iyer"], "Choose the backfill cap"),
          fnd("f3", "offer:jun-park", ["jun-park"], "Sign Jun's offer")]
    merges = group_findings(fs, StubLinker())
    assert "shared:priya-iyer" in seen and "shared:jun-park" not in seen, "only a person on two or more keys of different kinds opens a comparison"
    assert len(merges) == 1 and set([merges[0].canonical, *merges[0].merged]) == {"approval:inference-spend", "other:backfill-cap"}


def test_reader_notes_are_plain_and_deterministic():
    from datetime import datetime
    from digest.normalize.freshness import reader_notes

    fr = {"email": SimpleNamespace(state="stale", age_hours=32.0, latest_item_time=datetime(2026, 9, 22, 21, 30, tzinfo=TZ)),
          "calendar": SimpleNamespace(state="unreadable", age_hours=None, latest_item_time=None),
          "notes": SimpleNamespace(state="ok", age_hours=1.0, latest_item_time=None),
          "tasks": SimpleNamespace(state="stale", age_hours=10 * 24.0, latest_item_time=None)}
    notes = reader_notes(fr, datetime(2026, 9, 24, 6, 0, tzinfo=TZ))
    assert notes == reader_notes(fr, datetime(2026, 9, 24, 6, 0, tzinfo=TZ)) and len(notes) == 3
    assert notes[0].startswith("Your inbox last synced Tue 21:30") and "sync gap" in notes[0]
    assert "overlaps were not checked" in notes[1]
    assert notes[2].startswith("Your task list has not been updated in 10 days")
    assert reader_notes({"tasks": SimpleNamespace(state="ok", age_hours=2.0, latest_item_time=None)}, datetime(2026, 9, 24, 6, 0, tzinfo=TZ)) == []
