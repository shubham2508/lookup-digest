"""Track A · v2: the code floors on reader findings, reduce, compose validation, materializer code checks, verify's hard
rules, render. The stack is the fixture world + the fake thread reader (tests/a_fakes.py) + fake LLM for later stages."""
from pathlib import Path

import yaml
from a_fakes import TZ, fake_llm

from digest.compose import apply_focus, compose_digest, fallback_compose, validate_compose
from digest.compute import assemble, build_spine
from digest.config import load_settings
from digest.ingest import load_world
from digest.materialize import draft_violations, materialize, suggested_tasks_md
from digest.normalize import normalize_world
from digest.read import read_threads
from digest.reduce import reduce_items
from digest.render import CitationIndex, render_digest
from digest.runs import RunContext, parse_as_of
from digest.schemas import (
    ComposeItem,
    ComposeResult,
    Evidence,
    MaterializedAction,
    ProfileConfig,
    ProposedAction,
    SectionBlock,
)
from digest.triage import enforce_all
from digest.verify import verify

SETTINGS = load_settings()
AS_OF = parse_as_of("2026-09-24T06:00")


def _profile() -> ProfileConfig:
    data = yaml.safe_load(Path("profile/profile.yaml").read_text())
    data.pop("_meta", None)
    return ProfileConfig.model_validate(data)


def _stack(mini_dir, tmp_path, rulings=None, **fake):
    """Fixture world → spine → fake thread readers → assemble → code floors; fake LLM for every later stage."""
    world = normalize_world(load_world(mini_dir, AS_OF, TZ), SETTINGS, "Avery Chen")
    profile = _profile()
    llm = fake_llm(tmp_path, **fake)
    ctx = RunContext("t", AS_OF, runs_dir=tmp_path / "runs")
    spine = build_spine(world, profile, SETTINGS, AS_OF, llm=llm, ctx=ctx)
    read = read_threads(llm, world, spine.directory, profile, SETTINGS, AS_OF, ctx, rulings or [])
    comp = assemble(world, spine, read, profile, SETTINGS, AS_OF, llm=llm, ctx=ctx)
    results, stats = enforce_all(comp.triage, comp.candidates, comp, rulings or [], ctx, rulings_applied=read.stats.rulings_applied)
    return world, profile, comp, llm, ctx, results, stats


def test_code_floors_on_reader_findings(mini_dir, tmp_path):
    rulings = [{"id": "R1", "scope": {"contact": "sam-park"}, "ruling": "x"}, {"id": "R2", "scope": {"contact": "nobody-here"}, "ruling": "y"}]
    world, profile, comp, llm, ctx, results, stats = _stack(mini_dir, tmp_path, rulings=rulings)
    readers = [c for c in comp.candidates if c.facts["origin"] == "thread_reader"]
    assert len(results) == len(comp.candidates) and len(readers) == 3 and stats.rulings_applied == 1, "R1 reaches Sam's reader; R2 matches nobody"
    assert {c.facts["origin"] for c in comp.candidates} >= {"calendar_sweep", "notes_tasks_sweep", "safety_net"}, "Track B's sweeps and nets are in"
    by = {r.candidate_id: r for r in results}
    cand = {c.candidate_id: c for c in comp.candidates}
    for cid, r in by.items():
        assert r.citations and all(e in cand[cid].evidence for e in r.citations), "citations only from the finding's verified evidence"
        assert all(e.quote != "a sentence nobody wrote" for e in r.citations), "an invented quote never survives"
    sam = next(r for r in results if "sam-park" in cand[r.candidate_id].entities)
    assert sam.priority == "P0" and all(a.type != "reply" for a in sam.proposed_actions), "never a draft for Sam"
    assert any(a.type == "message_person" for a in sam.proposed_actions)
    renee = next(r for r in results if "renee-tan" in cand[r.candidate_id].entities)
    assert renee.priority == "P1", "a reader's P0 without a P0 contact, family matter or incident is demoted"
    marcus = next(r for r in results if "marcus-webb" in cand[r.candidate_id].entities)
    assert marcus.priority == "P0" and cand[marcus.candidate_id].about == "deal:series-a:cap-table"
    assert any("never_draft" in f for fx in stats.fixes for f in fx["fixes"])
    rows = [row for row in comp.findings if row["origin"] == "thread_reader"]
    no = [row for row in rows if row["needs_avery"] == "no"]
    assert len(rows) == 4 and len(no) == 1 and no[0]["candidate_id"] is None and no[0]["thread_id"]
    assert {row["finding_id"] for row in comp.findings if row["rescued_by_safety_net"]} == \
        {row["finding_id"] for row in comp.findings if row["origin"] == "safety_net"} and comp.stats["rescues"] == 2, \
        "the DocuSign request and the family collision: nothing a reader or the fake sweeps raised covers them"


def test_reduce_merges_sorts_and_caps(mini_dir, tmp_path):
    world, profile, comp, llm, ctx, results, _ = _stack(mini_dir, tmp_path)
    red = reduce_items(results, comp.candidates, comp, k_cap=1, about_merges=comp.about_merges)
    ids = [it.id for it in red.items]
    assert ids == sorted(ids, key=lambda i: int(i[1:])) and red.items[0].priority == "P0"
    cap = next(it for it in red.items if it.about.startswith("deal:series-a"))
    assert cap.priority == "P0" and cap.candidate_types == ["overdue promise to lead investor"]
    assert all(it.priority == "P0" for it in red.items if it.id not in red.overflow)
    p0_ids = {it.id for it in red.items if it.priority == "P0"}
    assert not (p0_ids & set(red.overflow)), "every P0 survives the cap"
    assert "c" in "".join(red.dropped) or red.dropped == [r.candidate_id for r in results if not r.include]


def test_compose_validation_dedupes_and_budgets_questions():
    red = reduce_items([], [], None, 25) if False else None
    from digest.schemas import ReduceItem, ReduceResult
    items = [ReduceItem(id="i1", about="deal:x", candidate_ids=["c1"], priority="P0", section="urgent", why="w1", citations=[Evidence(source_id="msg:<a>", quote="q")],
                        proposed_actions=[ProposedAction(type="question", target=None, brief="q1", assumptions=[], watch_trigger=None, read_start=None)]),
             ReduceItem(id="i2", about="deal:y", candidate_ids=["c2"], priority="P1", section="decisions", why="w2",
                        proposed_actions=[ProposedAction(type="question", target=None, brief="q2", assumptions=[], watch_trigger=None, read_start=None)]),
             ReduceItem(id="i3", about="deal:z", candidate_ids=["c3"], priority="P2", section="pulse", why="w3",
                        proposed_actions=[ProposedAction(type="question", target=None, brief="q3", assumptions=[], watch_trigger=None, read_start=None)]),
             ReduceItem(id="i4", about="deal:w", candidate_ids=["c4"], priority="P0", section="urgent", why="w4")]
    red = ReduceResult(items=items)
    q = ProposedAction(type="question", target=None, brief="q", assumptions=[], watch_trigger=None, read_start=None)
    raw = ComposeResult(one_thing_id="i1", sections=[SectionBlock(name="urgent", item_ids=["i1", "i2", "i2", "i9"]), SectionBlock(name="pulse", item_ids=["i3"])],
                        items=[ComposeItem(id="i1", what="a", why="b", final_actions=[q, q]), ComposeItem(id="i1", what="dup", why="", final_actions=[]),
                               ComposeItem(id="i2", what="c", why="d", final_actions=[q]), ComposeItem(id="i3", what="e", why="f", final_actions=[q]),
                               ComposeItem(id="i9", what="ghost", why="", final_actions=[])], header_notes=[], cut_ids=[])
    from digest.compose import ComposeStats
    st = ComposeStats()
    out = validate_compose(raw, red, question_budget=2, stats=st)
    assert out.one_thing_id == "i1" and [b.item_ids for b in out.sections] == [["i2", "i4"], [], [], ["i3"], []]
    assert [ci.id for ci in out.items] == ["i1", "i2", "i4", "i3"] and len(out.items[0].final_actions) == 1
    assert out.cut_ids == [], "an unplaced P0 is restored to its own section, never left in also-pending"
    types = [a.type for ci in out.items for a in ci.final_actions]
    assert types.count("question") == 2 and types.count("read") == 1, "question budget"
    fb = fallback_compose(red, {})
    assert fb.one_thing_id == "i1" and fb.header_notes and "i4" in [i for b in fb.sections for i in b.item_ids]


def test_draft_violations_and_materializer_retry(mini_dir, tmp_path):
    banned = SETTINGS.drafts.banned_phrases
    assert draft_violations("renee, yes. it's on. thanks.\nAvery", banned, 3) == []
    bad = draft_violations("hi, just wanted to confirm. one. two. three. four!!", banned, 3)
    assert any("banned" in b for b in bad) and any("sentences" in b for b in bad)
    world, profile, comp, llm, ctx, results, _ = _stack(mini_dir, tmp_path, banned_first=True)
    red = reduce_items(results, comp.candidates, comp, 25, comp.about_merges)
    cands = {c.candidate_id: c for c in comp.candidates}
    composed, cst = compose_digest(llm, red, cands, profile, SETTINGS, ctx, freshness_line="inbox ok", rulings_applied=0, compute=comp)
    by_item = {it.id: it for it in red.items}
    actions, mst = materialize(llm, composed, by_item, cands, comp, profile, SETTINGS, ctx)
    replies = [a for a in actions if a.type == "reply"]
    assert replies and all(a.draft and "just wanted to" not in a.draft for a in replies), "banned draft was retried"
    assert mst.draft_retries >= 1 and mst.drafts_dropped == 0
    q = [a for a in actions if a.type == "question"]
    assert all(a.text.startswith("Q") and "Default if unanswered" in a.text and "digest answer Q" in a.text for a in q)
    msg = [a for a in actions if a.type == "message_person"]
    assert msg and all("No draft (Sam)" in a.text for a in msg if a.recipient_name == "Sam Park")
    tasks_md = suggested_tasks_md(actions, "2026-09-24")
    assert tasks_md.startswith("- [ ] ") and "(due: 2026-09-24)" in tasks_md


def test_verify_rules_and_render(mini_dir, tmp_path):
    world, profile, comp, llm, ctx, results, _ = _stack(mini_dir, tmp_path)
    red = reduce_items(results, comp.candidates, comp, 25, comp.about_merges)
    cands = {c.candidate_id: c for c in comp.candidates}
    composed, _ = compose_digest(llm, red, cands, profile, SETTINGS, ctx, freshness_line="inbox ok", rulings_applied=0, compute=comp)
    by_item = {it.id: it for it in red.items}
    actions, _ = materialize(llm, composed, by_item, cands, comp, profile, SETTINGS, ctx)
    # plant violations: a draft to Sam (rule 1), a bad citation (rule 5), a P0 suspicious item (rule 11), a non-proposal (rule 10)
    sam_item = next(it for it in red.items if "sam-park" in it.entities)
    actions.append(MaterializedAction(item_id=sam_item.id, type="reply", target="sam@parkfamily.example", recipient_name="Sam Park", brief="hi", text="↳ Draft to Sam:", draft="sam, ok"))
    renee = next(it for it in red.items if "renee-tan" in it.entities)
    actions.append(MaterializedAction(item_id=renee.id, type="calendar_response", target=None, brief="move", text="move it to 11:15"))
    known = CitationIndex(world).known
    msg_thread = {f"msg:{m.message_id}": t.thread_id for t in world.threads for m in t.messages}
    router = {t.thread_id: t.router_type for t in world.threads}
    tiny_budget = 8
    ver = verify(composed, by_item, actions, cands, comp, results, known, router, tiny_budget, "As of Thu 06:00 PT · inbox ok", None, overflow=red.overflow, msg_thread=msg_thread)
    rules = {v.rule for v in ver.result.violations}
    assert {1, 9, 10} <= rules, rules
    assert not any(a.type == "reply" and a.recipient_name == "Sam Park" for a in ver.actions)
    assert all(a.text.startswith("↳ Propose:") for a in ver.actions if a.type == "calendar_response")
    placed = {ver.compose.one_thing_id} | {i for s in ver.compose.sections for i in s.item_ids}
    assert ver.result.stats.words <= tiny_budget or all(by_item[i].priority == "P0" for i in placed if i), "over budget: drop non-P0 until it fits"
    assert all(by_item[i].priority == "P0" for i in placed if i) or len(ver.also_pending) >= 3
    assert all(e.source_id in known for i in placed if i for e in by_item[i].citations)
    md = render_digest(as_of=AS_OF, header="As of Thu 06:00 PT · inbox ok", compose=ver.compose, reduced=by_item, actions=ver.actions, cands=cands,
                       world=world, also_pending=ver.also_pending, outside_filter=ver.outside_filter, titles={}, header_notes=["note one"])
    assert md.startswith("# Daily Digest — Thursday, September 24, 2026\n\nAs of Thu 06:00 PT · inbox ok · note one\n")
    for title in ("## If there is one thing you must do right now", "## Urgent To-Do Today", "## Decisions & Approvals", "## AI Industry News",
                  "## Team & Product Pulse", "## Calendar & Personal", "## Also pending ("):
        assert title in md, title
    assert "*[email: " in md or "*[cal: " in md or "*[task: " in md
    assert "other meeting" in md and "nothing to act on" in md


def test_focus_only_keeps_family_and_p0_as_outside_filter(mini_dir, tmp_path):
    from digest.compile.customize import default_overrides
    from digest.schemas import Focus
    world, profile, comp, llm, ctx, results, _ = _stack(mini_dir, tmp_path)
    red = reduce_items(results, comp.candidates, comp, 25, comp.about_merges)
    o = default_overrides().model_copy(update={"focus": Focus(entities=[], categories=["family"], mode="only"), "length_words": 100})
    hidden, outside = apply_focus(red, {c.candidate_id: c for c in comp.candidates}, comp, o)
    fam = [it.id for it in red.items if "sam-park" in it.entities]
    assert fam and not (set(fam) & set(hidden)) and not (set(fam) & set(outside))
    assert any(red_it.priority == "P0" for red_it in red.items if red_it.id in outside), "a P0 outside the filter is kept as a one-liner"
    assert all(red_it.priority != "P0" for red_it in red.items if red_it.id in hidden)


def test_stale_inbox_qualifies_reduced_items_too():
    """An item that lands in 'Also pending' keeps the sync-gap qualifier (DESIGN_LOG §4.4)."""
    from datetime import datetime
    from types import SimpleNamespace

    from digest.pipeline import qualify_reduced

    stale = SimpleNamespace(state="stale", latest_item_time=datetime(2026, 9, 22, 18, 0, tzinfo=TZ))
    quiet = SimpleNamespace(candidate_types=["quiet_thread"], why="Quiet for three business days.", citations=[])
    news = SimpleNamespace(candidate_types=["news_attachment"], why="Price cut on Oct 1.", citations=[])
    qualify_reduced(SimpleNamespace(items=[quiet, news]), {"email": stale})
    assert "may be a sync gap" in quiet.why.lower() and "Tue 18:00" in quiet.why
    assert news.why == "Price cut on Oct 1."


def test_third_morning_says_third_time_flagged():
    from types import SimpleNamespace

    from digest.pipeline import frame_escalation

    flat = SimpleNamespace(id="i1", what="Send the index", why="Promised Monday.")
    framed = SimpleNamespace(id="i2", what="Reply to Oren", why="Still waiting after four days.")
    fresh = SimpleNamespace(id="i3", what="Approve expenses", why="Three reports.")
    by_item = {"i1": SimpleNamespace(times_surfaced=2), "i2": SimpleNamespace(times_surfaced=3), "i3": SimpleNamespace(times_surfaced=1)}
    frame_escalation(SimpleNamespace(items=[flat, framed, fresh]), by_item)
    assert flat.why == "Promised Monday. Third time flagged."
    assert framed.why == "Still waiting after four days." and fresh.why == "Three reports."
