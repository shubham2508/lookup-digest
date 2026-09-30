"""Track B · v2: the three sweeps. What each one reads (window, declines, code-computed overlaps and due dates, reader
findings), batching, the as_of cache salt, and the citation check that drops invented quotes. Offline."""
import json

from a_fakes import AVERY, PROFILE_JSON, TZ, event, fake_llm, msg, thread, world

import digest.compute.sweeps as sw
from digest.compute.contacts import build_contacts
from digest.ingest.notes import parse_note_text
from digest.llm import LLMResult, Usage
from digest.runs import RunContext
from digest.schemas import Evidence, Finding, NormalizedTask, ProfileConfig, SweepOutput

PROFILE = ProfileConfig.model_validate(PROFILE_JSON)


def _finding(fid="f1", *, title="Reply to Oren about the SLA", needs="yes", contradictions=(), cite=("msg:<a1>", "the SLA")) -> Finding:
    return Finding(finding_id=fid, origin="thread_reader", needs_avery=needs, title=title, kind="reply owed", why="w", priority="P1",
                   urgency="today", deadline=None, stakes="medium", confidence="high", section="urgent", entities=["oren-tal"],
                   about=["contract:halden-sla"], citations=[Evidence(source_id=cite[0], quote=cite[1])], proposed_actions=[],
                   ambiguity=None, contradictions=list(contradictions), freshness_caveat=None, suspicious_instructions=[])


def _world(**kw):
    evs = [
        event("lumen", "Lumen demo", "2026-09-24T10:30", "2026-09-24T11:15", organizer="dana@lumen.example", attendees=[(AVERY, "NEEDS-ACTION")]),
        event("sync", "Q2 planning sync", "2026-09-24T14:30", "2026-09-24T15:30", attendees=[(AVERY, "ACCEPTED"), ("priya@tessera.io", "ACCEPTED")]),
        event("ped", "Wren - pediatrician", "2026-09-24T15:00", "2026-09-24T16:00", organizer="sam@parkfamily.example", calendar="shared_family"),
        event("mon", "Leadership sync", "2026-09-28T10:00", "2026-09-28T10:45"),
        event("tue", "Board prep", "2026-09-29T10:00", "2026-09-29T10:45"),
        event("qbr", "Customer QBR", "2026-09-17T10:00", "2026-09-17T11:00", organizer="oren@halden.example", attendees=[(AVERY, "DECLINED")]),
        event("oldx", "Old declined", "2026-09-01T10:00", "2026-09-01T11:00", organizer="x@y.example", attendees=[(AVERY, "DECLINED")]),
    ]
    note = parse_note_text("Date: 2026-09-21 | Attendees: Jordan Liu\n# Hiring sync\n- Avery to send the comp band by Fri\n- designer req paused",
                           "notes/hiring-sync.md", None, TZ)
    tasks = [NormalizedTask(task_id="board", title="Send the September board update", due=__import__("datetime").date(2026, 9, 15)),
             NormalizedTask(task_id="later", title="Plan offsite", due=__import__("datetime").date(2026, 10, 2))]
    nl = [thread(msg(f"n{i}", f"2026-09-2{i}T07:00", "brief@scbrief.example", subject=f"Brief #{i}", body="Freight surcharges drop 12% from Nov 1. " * 40),
                 router="bulk") for i in range(1, 4)]
    sam = msg("s1", "2026-09-01T10:00", "sam@parkfamily.example", subject="hi", name="Sam Park")
    return world([thread(sam), *nl], events=evs, notes=[note], tasks=tasks, **kw)


def test_calendar_sweep_reads_the_window_declines_and_computed_overlaps():
    w = _world()
    d = build_contacts(w, PROFILE, None, None, None)
    c = sw.calendar_call(w, d, [_finding(contradictions=["calendar says Fri; the thread moved it to Mon"])], PROFILE, w.as_of)
    window = c.text.split("=== CALENDAR WINDOW", 1)[1].split("=== END CALENDAR WINDOW", 1)[0]
    assert "event:lumen" in window and "event:mon" in window and "event:tue" not in window, "today through the 2nd business day (Mon)"
    declines = c.text.split("=== DECLINED IN THE LAST 14 DAYS", 1)[1]
    assert "event:qbr" in declines and "event:oldx" not in declines
    assert "overlaps the Thu 09:00–11:00 deep-work block by 30 minutes" in c.text and "event:sync (Q2 planning sync) and event:ped (Wren - pediatrician) overlap 30 minutes" in c.text
    assert "calendar says Fri; the thread moved it to Mon" in c.text, "reader contradictions are passed in"
    assert '"contact_id": "sam-park"' in c.text and '"never_draft"' in c.text, "attendee contact records"
    assert c.sources["event:lumen"] == "Lumen demo" and set(c.sources) == {"event:lumen", "event:sync", "event:ped", "event:mon", "event:qbr"}
    assert "today (Thu)" in c.text and "{{" not in c.text


def test_notes_tasks_sweep_numbers_lines_and_dates_tasks():
    w = _world()
    c = sw.notes_tasks_call(w, [_finding()], PROFILE, w.as_of)
    assert "L3: - Avery to send the comp band by Fri" in c.text and "dated: 2026-09-21 (3 days ago)" in c.text
    assert "task:board · [ ] Send the September board update · due 2026-09-15 (Tue 15 Sep; 9 days overdue)" in c.text
    assert "task:later" in c.text and "in 8 days" in c.text
    assert c.sources["note:notes/hiring-sync.md"].startswith("Date: 2026-09-21") and c.sources["task:board"] == "Send the September board update"
    assert '"subject": "ARR"' in c.text, "profile facts for drift"


def test_news_sweep_only_with_open_items_and_batches(monkeypatch):
    w = _world()
    assert sw.news_calls(w, [_finding(needs="no")], PROFILE, w.as_of) == [], "nothing open: no call"
    one = sw.news_calls(w, [_finding(), _finding("f2", needs="no", title="FYI only")], PROFILE, w.as_of)
    assert len(one) == 1 and one[0].name == "news" and "FYI only" not in one[0].text and len(one[0].sources) == 3
    monkeypatch.setattr(sw, "BATCH_TOKENS", 500)
    many = sw.news_calls(w, [_finding()], PROFILE, w.as_of)
    assert [c.name for c in many] == ["news-b1", "news-b2", "news-b3"] and all(len(c.sources) == 1 for c in many)


class StubLLM:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def complete_many(self, calls, max_workers=8):
        self.calls = calls
        out = []
        for c in calls:
            o = self.outputs.get(c["tag"])
            out.append(o if isinstance(o, Exception) else LLMResult(output=SweepOutput.model_validate(o or {"findings": []}), role=c["role"], model="stub",
                                                                   cached=False, usage=Usage(), retries=0, latency_ms=0, cache_key="", raw=""))
        return out


def test_run_sweeps_checks_citations_sets_origin_and_salts_the_cache(tmp_path):
    from b_fakes import finding

    w = _world()
    good = finding("f1", "Protect deep work: Lumen demo", ("event:lumen", "Lumen demo"))
    fake = finding("f2", "Invented conflict", ("event:lumen", "Board dinner with the whole team"))
    note = finding("f1", "Send the comp band", ("note:notes/hiring-sync.md#L3", "Avery to send the comp band by Fri"))
    llm = StubLLM({"sweep:calendar": {"findings": [good, fake]}, "sweep:notes_tasks": {"findings": [note]}, "sweep:news": RuntimeError("boom")})
    ctx = RunContext("t", w.as_of, runs_dir=tmp_path / "runs")
    out = sw.run_sweeps(w, build_contacts(w, PROFILE, None, None, None), [_finding()], PROFILE, None, llm, ctx, w.as_of)
    assert [(f.finding_id, f.origin) for f in out] == [("calendar:f1", "calendar_sweep"), ("notes_tasks:f1", "notes_tasks_sweep")]
    assert out[1].citations[0].source_id == "note:notes/hiring-sync.md", "line refs resolve to the note"
    reasons = [(d["item"], d["reason"]) for d in ctx.degradations]
    assert ("calendar", "citation_invalid") in reasons and ("calendar", "finding_dropped_no_citation") in reasons and ("news", "RuntimeError") in reasons
    assert {c["cache_salt"] for c in llm.calls} == {"2026-09-24"} and [c["role"] for c in llm.calls] == ["calendar_sweep", "notes_tasks_sweep", "news_sweep"]


def test_run_sweeps_end_to_end_on_the_fake_client(tmp_path):
    w = _world()
    llm = fake_llm(tmp_path)
    d = build_contacts(w, PROFILE, None, llm, None)
    out = sw.run_sweeps(w, d, [_finding()], PROFILE, None, llm, None, w.as_of)
    assert {(f.origin, f.citations[0].source_id) for f in out} == {("calendar_sweep", "event:lumen"), ("notes_tasks_sweep", "task:board")}
    again = sw.run_sweeps(w, d, [_finding()], PROFILE, None, llm, None, w.as_of)
    assert [f.model_dump() for f in again] == [f.model_dump() for f in out]
    rows = [json.loads(ln) for ln in (tmp_path / "cost.jsonl").read_text().splitlines()]
    assert sum(1 for r in rows if r["role"].endswith("_sweep") and r["cached"]) == 3, "the rerun is served from the cache"
    assert sw.run_sweeps(w, d, [], PROFILE, None, None, None, w.as_of) == []


def test_reader_brief_is_compact():
    rows = json.loads(sw.reader_brief([_finding(contradictions=["x"]), _finding("f2", needs="no")]))
    assert rows[0] == {"id": "f1", "needs_avery": "yes", "priority": "P1", "title": "Reply to Oren about the SLA", "kind": "reply owed",
                       "entities": ["oren-tal"], "about": ["contract:halden-sla"], "contradictions": ["x"]}
    assert "contradictions" not in rows[1]
