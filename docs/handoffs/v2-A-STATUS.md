# v2 · Track A · status

**2026-09-29 · stopped at the P2 gate.** Review: `docs/handoffs/v2-A-checkpoint.md` (five planted threads, raw ↔ Finding ↔ v1
triage, plus seven problems that need a decision). P3–P5 wait for Shubham.

## Landed (branch `v2-a-readers`)

| Deliverable | Where | Notes |
|---|---|---|
| A1 raw-thread renderer | `digest/read/render.py` | every message oldest first with `msg:<id>`, name + email, PT ISO time with offset and weekday, To/Cc, clean body, signature cut to 4 lines (citations may quote the full one), forwards attributed to the original sender; one fenced untrusted block, fake fence lines in bodies defused; `world_source_text` backs citations of retrieved context with the real source |
| A2 reader prompt | `prompts/thread_reader.md` v1 | rubric, sections and taxonomy copied verbatim from v1 `triage.md` lines 16–34; instructions and code facts in the system message, untrusted blocks (retrieved context, raw thread) in the user message; leak grep clean; examples use the made-up cast only |
| A3 reader stage | `digest/read/__init__.py` | human/unsure threads with a message in the last 30 days; thin-index facts computed in code (business days waiting, who wrote last, Avery's last reply); contact cards with the profile's own notes; rulings scoped to the thread's contacts; `cache_salt` = as_of date; citations checked (invalid quotes dropped and logged, a finding with none left dropped); entity names → contact ids plus the thread's own contacts; a failed call degrades (header says "N thread(s) could not be read today") |
| A4 pipeline | `digest/pipeline.py`, `digest/compute/__init__.py`, `digest/triage/__init__.py` | profile → ingest → normalize → spine → read → [sweeps → nets → reconcile → group: B's, called when present] → `enforce_all` → reduce → compose → materialize → verify → render. `findings.jsonl` written (all origins, "no" rows with `candidate_id: null`). Triage LLM call, extractor stage, `extractor.md`, `triage.md` deleted. P0 floor now also accepts `family:`/`incident:` tags and family-category contacts; any finding with suspicious instructions is never P0 |
| Compose, minimal | `digest/compose/__init__.py` | reader titles in fallback / Also-pending lines; compose sees kind, urgency, stakes, deadline phrase, contradictions |
| CLI | `digest/cli.py` | `digest run` prints the read stats instead of extraction stats |

Tests: `tests/test_a_read.py` (11 new), `test_a_stages.py` and `test_a_pipeline.py` ported to readers, `a_fakes.py` has a
`ReaderOutput` fake (planted: invented quotes, a reply to Sam, an unearned P0, a "no" finding). `test_a_extract.py`
deleted (its evidence-index test moved to `test_a_read.py`). Full suite green.

## Cost of a Thursday run (dev, 2026-09-24T06:00, cold cache)

$0.211: 175 reader calls $0.205 (≈ $0.0012 per thread), compose $0.006, materializer $0.001. Reading 198 s at 8 workers.
Warm rerun of the same morning: $0 for readers.

## Not done (waits for the gate)

- **A5** (P5): compose raw excerpts (`item_view`, `compose.md` v5), materializer raw message (`materializer.md` v3).
- Checkpoint problems #2, #3, #6 and #7 are Track A work planned for P5; #1 and #4 are Track B's (retrieval, `group_findings`).

## For the orchestrator (merge notes)

- **Track B integration points**, all detected at run time, so either merge order works: `build_contacts` with the new
  signature (the v1 signature is detected by its `extractions` parameter), `compute.context.retrieve` (else the
  calendar-only fallback in `digest/read/__init__.py`), `compute.sweeps.run_sweeps`, `compute.candidates.safety_nets` (its
  `ComputeInputs` is built from whichever fields exist), `reconcile` and `group_findings` in `compute.merge` or
  `compute.linker`. Rescued = a net finding that survives `reconcile`.
- `compute_world` (v1) stays in `digest/compute/__init__.py` with lazy imports, only for `tests/test_a_compute.py`, which
  Track B moves to `test_b_compute.py`; delete both together.
- `prompts/topic_grouper.md` **kept** (the handoff listed it for deletion, but `Linker.group_topics` loads it and B5 reuses it).
- `digest/runs.py` `ARTIFACTS` still lists `extractions.jsonl`; v2 no longer writes it (my pipeline test allows that).
- `eval/history.md` has no line for `thread_reader@v1` yet: rule 10 wants the eval after a prompt change, and this track
  may not run the matrix. The line belongs with the P6 v1/v2/baseline run.
