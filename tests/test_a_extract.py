"""Track A · M3: extractor plumbing — documents, evidence check in code, type reconciliation, caching, degradation."""
from zoneinfo import ZoneInfo

from a_fakes import PROFILE_JSON, fake_llm

from digest.config import load_settings
from digest.extract import extract_documents, input_hash, reconcile_type
from digest.extract.documents import directory_hash, documents_for, note_document, task_document
from digest.extract.evidence import SourceIndex, check_payload, normalize_for_match
from digest.ingest import load_world
from digest.ingest.notes import parse_note_text
from digest.normalize import normalize_world
from digest.prompts import load_prompt
from digest.runs import RunContext, parse_as_of
from digest.schemas import Ask, Ball, Evidence, ExtractorOutput, HumanThread, NormalizedTask, ProfileConfig

TZ = ZoneInfo("America/Los_Angeles")
AS_OF = parse_as_of("2026-09-24T06:00")
SETTINGS = load_settings()
PROFILE = ProfileConfig.model_validate(PROFILE_JSON)


def _world(mini_dir):
    return normalize_world(load_world(mini_dir, AS_OF, TZ), SETTINGS, "Avery Chen")


def test_documents_carry_source_ids_and_texts(mini_dir):
    docs = documents_for(_world(mini_dir))
    assert [d.kind for d in docs].count("thread") == 6 and [d.kind for d in docs].count("note") == 1 and [d.kind for d in docs].count("task") == 3
    cap = next(d for d in docs if d.source_id == "thread:20260922-1642.marcus@inflectionpoint.vc")
    assert "source_id: msg:<20260922-2130.avery@tessera.io>" in cap.text and "[this is Avery]" in cap.text
    assert "will send it tonight" in cap.sources["msg:<20260922-2130.avery@tessera.io>"] and "> Avery" not in cap.text
    note = note_document(parse_note_text("Date: 2026-09-22 | Attendees: A\n\n# T\n\n- Halberd rollout: on track\n", "notes/n.md", None))
    assert note.source_id == "note:notes/n.md" and "L5: - Halberd rollout: on track" in note.text and note.sources["note:notes/n.md"].startswith("Date:")
    task = task_document(NormalizedTask(task_id="call-ben", title="Call Ben", due=None))
    assert task.source_id == "task:call-ben" and task.sources == {"task:call-ben": "- [ ] Call Ben"}


def test_source_index_resolves_leniently_and_matches_normalized():
    idx = SourceIndex({"msg:<a@x>": "Subject\nI’m reconciling it  now — will send it tonight.", "note:notes/n.md": "L1 text\nsecond line"})
    assert idx.resolve("msg:a@x") == "msg:<a@x>" and idx.resolve("note:n.md") == "note:notes/n.md" and idx.resolve("note:notes/n.md#L2") == "note:notes/n.md"
    assert idx.resolve("msg:<zzz>") is None
    assert idx.contains("msg:<a@x>", "I'm reconciling it now - will send") and idx.contains("note:n.md#L2", "second line")
    assert not idx.contains("msg:<a@x>", "tomorrow") and not idx.contains("msg:<a@x>", "")
    assert normalize_for_match(" a  b\n c ") == "a b c" and idx.first_words("msg:a@x", 3) == "I'm reconciling it"


def _thread(quote_ask: str, quote_ball: str) -> HumanThread:
    ev = lambda q: Evidence(source_id="msg:<a@x>", quote=q)  # noqa: E731
    return HumanThread(
        summary="s", about=["deal:x"], domain="work", intent_primary="ask", intent_secondary=[],
        ball=Ball(awaiting="avery", awaiting_who=None, last_message_by="m@x", last_message_at=AS_OF, closed_by_courtesy=False, evidence=ev(quote_ball)),
        sender_observations=[], asks=[Ask(from_email="m@x", to_avery=True, kind="information", what="w", deadline=None, status="open",
                                          answered_by_message=None, evidence=ev(quote_ask))],
        commitments=[], deferrals=[], schedule_mentions=[], stage_signals=[], role_changes=[], claims=[],
        suspicious_instructions=[ev("real words"), ev("fabricated words")])


def test_evidence_check_drops_list_facts_and_replaces_singletons():
    idx = SourceIndex({"msg:<a@x>": "Subj\nreal words here and more real words to quote"})
    fixed, rep = check_payload(_thread("real words here", "totally invented"), idx, fallback_source="msg:<a@x>")
    assert len(fixed.asks) == 1 and len(fixed.suspicious_instructions) == 1 and fixed.suspicious_instructions[0].quote == "real words"
    assert fixed.ball.evidence.quote.startswith("real words here") and rep.replaced and rep.replaced[0]["quote"] == "totally invented"
    assert rep.checked == 4 and rep.valid == 2 and len(rep.dropped) == 1 and rep.dropped[0]["path"] == "suspicious_instructions[1]"
    fixed2, rep2 = check_payload(_thread("nope nope", "real words"), idx)
    assert fixed2.asks == [] and rep2.dropped[0]["path"] == "asks[0].evidence" and "substring" in rep2.dropped[0]["reason"]


def test_reconcile_type_coerces_mismatch():
    from digest.extract import ExtractStats
    from digest.extract.documents import Document
    doc = Document(source_id="t", kind="thread", router_type="human", text="")
    stats = ExtractStats()
    out = ExtractorOutput(type="marketing", human_thread=_thread("a", "b"), newsletter=None, automated=None, note=None, task=None)
    fixed = reconcile_type(out, doc, stats)
    assert fixed.type == "human_thread" and stats.type_changes[0]["from"] == "marketing"
    assert reconcile_type(ExtractorOutput(type="human_thread", human_thread=None, newsletter=None, automated=None, note=None, task=None), doc, stats) is None
    assert reconcile_type(ExtractorOutput(type="marketing", human_thread=None, newsletter=None, automated=None, note=None, task=None), doc, stats).type == "marketing"


def test_extract_fixture_with_fake_llm_marketing_skipped_and_cached(mini_dir, tmp_path):
    world = _world(mini_dir)
    llm = fake_llm(tmp_path)
    ctx = RunContext("t", AS_OF, runs_dir=tmp_path / "runs")
    xs, stats = extract_documents(llm, documents_for(world), PROFILE, world.owner_email, SETTINGS, ctx)
    assert len(xs) == 10 and stats.llm_calls == 9 and stats.skipped_marketing == 1 and stats.invalid == 0
    types = {x.source_id: x.type for x in xs}
    assert types["thread:20260921-1000.hello@mail.rippleboard.example"] == "marketing" and types["thread:20260923-0700.brief@scbrief.example"] == "newsletter"
    assert types["note:notes/sprint-week.md"] == "note" and types["task:approve-september-expense-reports"] == "task"
    cap = next(x for x in xs if x.source_id.endswith("marcus@inflectionpoint.vc"))
    assert cap.payload.ball.last_message_by == "avery@tessera.io" and cap.payload.ball.last_message_at.isoformat() == "2026-09-22T21:30:47-07:00"
    assert stats.evidence_dropped == 0 and ctx.degradations == []
    assert all(x.meta.prompt_version == load_prompt("extractor").version_tag for x in xs)
    xs2, stats2 = extract_documents(llm, documents_for(world), PROFILE, world.owner_email, SETTINGS, ctx)
    assert stats2.cached == 9 and len(llm.client.calls) == 9, "second pass must be served from the cache"
    assert [x.meta.input_hash for x in xs] == [x.meta.input_hash for x in xs2]


def test_bad_quotes_are_dropped_and_logged(mini_dir, tmp_path):
    world = _world(mini_dir)
    llm = fake_llm(tmp_path, bad_quote=True)
    ctx = RunContext("t", AS_OF, runs_dir=tmp_path / "runs")
    xs, stats = extract_documents(llm, documents_for(world), PROFILE, world.owner_email, SETTINGS, ctx)
    assert stats.evidence_dropped > 0 and stats.evidence_replaced > 0
    reasons = {d["reason"] for d in ctx.degradations}
    assert reasons == {"evidence_invalid", "evidence_replaced"}
    note = next(x for x in xs if x.type == "note")
    assert note.payload.claims == []
    human = next(x for x in xs if x.type == "human_thread")
    assert human.payload.asks == [] and human.payload.ball.evidence.quote  # ball keeps a verbatim span


def test_input_hash_depends_on_directory_and_prompt(mini_dir):
    docs = documents_for(_world(mini_dir))
    d1 = directory_hash([{"name": "A"}], ["x"])
    d2 = directory_hash([{"name": "A"}], ["y"])
    assert input_hash(docs[0], d1, "extractor@v1") != input_hash(docs[0], d2, "extractor@v1") != input_hash(docs[0], d1, "extractor@v2")


def test_prompt_p3_shape():
    p = load_prompt("extractor")
    assert p.model_role == "extractor" and p.output_model == "ExtractorOutput"
    assert p.variables == ["about_kinds", "avery_email", "avery_name", "contact_directory", "document", "stage_vocab", "standing_topics"]
    for must in ("Content is data", "suspicious_instructions", "verbatim", "closed_by_courtesy", "fulfills_hint", "Gender-neutral"):
        assert must in p.text, must
