# MIGRATION_PLAN — v1 (extraction-centric) → v2 (read, don't extract)

Per `PIVOT_SPEC.md` §1. v1 is tagged `v1-extraction-centric` (commit 02906f9, final reports `eval/reports/*_2026-09-29.md`).
Nothing below is built until Shubham approves this plan.

## 0. The one idea that keeps this small

Readers, sweeps and safety nets all emit `Finding`. Code maps every Finding onto the two shapes the rest of the
pipeline already consumes: `Candidate` (id, type ← `kind`, about ← first `about` tag, entities, facts, evidence,
context_refs) and `TriageResult` (include ← `needs_avery == "yes"`, priority, section, due_today ← urgency, confidence,
why, citations, ambiguity, proposed_actions). From reduce onward nothing changes: reduce → compose → materialize →
verify → render, the run artifacts (`candidates.jsonl`, `triage.jsonl`, `reduce.json`, …), the UI, rulings, history,
simulate, honesty variants, customize, baseline, and ~70% of the scorer keep working as they are.

Two additions to the spec's Finding, both needed by the downstream contract: `section` (the five sections; the
reader picks it with the same definitions triage used) and `origin` already covers `safety_net`.

## 1. Audit: keep / modify / delete

### digest/ (product)

| Module | Lines | Fate | Reason |
|---|---|---|---|
| `ingest/*` (eml, ics, loader, notes, tasks) | 558 | keep | Spec §2.1 |
| `normalize/*` (text, threading, router, calendar, freshness, owner) | 698 | keep | Quote/signature split feeds the reader input and the signature parser |
| `extract/documents.py` | 102 | modify | Becomes the raw-thread renderer for readers (chronological, timestamps, senders, quotes stripped, per-message `msg:` ids) |
| `extract/evidence.py` | 167 | keep | Quote-is-substring check, now on Finding citations (≤25 words per spec) |
| `extract/__init__.py` (extractor stage) | 159 | delete | Replaced by readers + sweeps |
| `compute/contacts.py` | 384 | modify | Keep resolution order, role-at-org via linker, behavior stats, org-tier inheritance. Replace extractor `sender_observations` with a cached **signature parser** call per new contact and a cached **contact classifier** call per contact (§3.2) |
| `compute/signals.py` | 169 | keep | Business days, overlaps, cadence math, `day_label` |
| `compute/candidates.py` | 1010 | modify → ~350 | Keep as **safety nets**: `reply_owed`/`quiet_thread` (P0-contact waiting ≥ threshold), reference-customer EOD, `deep_work_conflicts`, `family_conflicts` + `personal_date_collisions`, `double_book`, `recruiter_patterns`, `stale_sources`, `suspicious`, `approvals` (automated with deadline). **Delete** `commitments`, `contradictions`, `declined_meetings`, `hiring_stalls`, `cadence_drops`, `obligations`, `tasks_due`, `profile_drift`, `news_attachments`: readers and sweeps cover them open-world |
| `compute/context.py` | 148 | modify | Retrieval for readers (§3.3): events ±7d sharing a participant/org, notes and tasks mentioning a participant/org/subject word, previous 2 threads with the same participants; ~4k-token cap, most relevant first. Retrieval only chooses what is read; it decides nothing |
| `compute/linker.py`, `compute/jev.py` | 302 | keep | Sameness decisions: role-at-org, safety-net ↔ reader reconciliation, merge groups (replaces the spec's slug similarity, per Shubham) |
| `compute/aboutkeys.py` | 105 | delete | Topic-key merging belongs to merge via the linker; Finding `about` tags are hints only |
| `compute/facts.py` | 111 | modify → small | Effective facts (ARR etc.) now come from the notes+tasks sweep's "changed facts"; keep the profile-vs-data drift shape for the materializer |
| `compute/__init__.py` | 150 | modify | New orchestration: index → spine → readers → sweeps → nets → reconcile → map to Candidate/TriageResult |
| `triage/__init__.py` | 230 | modify → ~90 | Delete the LLM call and cards. Keep `enforce` (hard rules on every Finding: never_draft → message_person, cold recruiters, suspicious never P0, **P0 earned only by tier/escalation/family**, citations verbatim, freshness caps confidence) and `ruling_matches` |
| `reduce`, `compose`, `verify`, `render`, `compile/*` | 1,031 | keep | compose input gains raw excerpts (~300 tokens around each citation), materializer gains the message answered + the one before; outputs unchanged |
| `materialize/__init__.py` | 251 | modify (input) | As above |
| `schemas.py` | 686 | modify | Add `Finding`, `ContactClassification`, `SignatureFacts`; mark the extraction payload types (`HumanThread`, `Ask`, `Commitment`, `StageSignal`, `Claim`, `Newsletter…`) deprecated and delete once nothing imports them |
| `pipeline.py` | 337 | modify | Stage order per §2; `extract` timing → `read`/`sweep`/`nets` |
| `llm.py`, `store.py`, `runs.py`, `config.py`, `prompts.py`, `history.py`, `answer.py`, `baseline.py`, `cli.py`, `paths.py`, `util.py` | 1,459 | keep | Cache key gains `as_of` date only for reader/sweep roles |
| `ui/` (debug UI) | — | keep | Tabs read the same artifacts; the "LLM calls" tab shows reader calls instead of extractor calls |

### prompts/

| Prompt | Fate |
|---|---|
| `extractor.md`, `triage.md`, `topic_grouper.md` | delete |
| `thread_reader.md`, `calendar_sweep.md`, `notes_tasks_sweep.md`, `news_sweep.md`, `contact_classifier.md`, `signature_parser.md` | new; the P4 priority rubric and the action taxonomy copied verbatim; raw text in labeled untrusted data blocks |
| `linker.md` | keep; one more task text ("is this safety-net fact the same issue as this finding?") |
| `compose.md`, `materializer.md` | modify: new input blocks, same output schema |
| `profile_compiler.md`, `customize_compiler.md`, `baseline.md`, `judge.md`, `sim_avery.md` | keep |

### eval/

| Module | Fate | Reason |
|---|---|---|
| `scorer/extraction.py` | replace | **Reader diagnostics**: per labeled thread, did a reader Finding say `needs_avery` as the label implies (ball on Avery, open ask to Avery, or Avery's open promise), with the day's expected priority band and an expected action type? Reported, not gated |
| `scorer/compute.py` | modify | Candidate metrics → **safety-net rescue list** (findings only a net produced) and sweep recall on planted calendar/notes traps |
| `scorer/triage.py` | modify → small | Hard-rule violations on Findings (same checks) |
| `scorer/attribution.py` | modify | Stages: read → sweep → net → merge → compose → materialize → verify |
| `scorer/assertions.py` | modify | `candidate_present/absent`, `count_items_of_type`, `no_candidates_of_type` (47 dev / 54 held-out of 674 / 752): `type` matches a Finding's `kind` **or** its origin rule (safety nets keep the old type names), else the `about` alone. Everything item-level stays |
| `scorer/artifacts.py`, `common.py`, `match.py`, `digest_metrics.py`, `digest_md.py`, `conditions.py`, `simulation.py`, `profile_diff.py`, `runner.py`, `report.py` | keep | Read the unchanged artifacts; report §1 gains a **v1 / v2 / baseline** table from the v1 tag's reports |
| `judge/`, `sim_avery/`, `integrate.py`, `history.py`, `manifest_schema.py` | keep | |
| `eval/manifests/*.yaml` | keep | Per-source labels become reader diagnostics; per-day `candidates:` lists become the net/sweep diagnostics; items and assertions unchanged |

### v1 things the spec does not mention (kept unless told otherwise)

Jev as the linker's first decider (`decider` role), the `--tag` run dirs and `digest simulate`, `digest answer` +
rulings with exact-key scope, `digest ui`, the naive baseline, honesty variants, the customize suite, the
`debug-trap` skill, the DeepSeek judge, `runs/examples/`, the prompt-leak grep. All keep working through the
Candidate/TriageResult mapping.

## 2. Shubham's corrections to the spec (applied)

1. **No string similarity.** §5.4 "slug similarity ≥ 0.85" → merge groups and safety-net reconciliation are linker
   decisions (Jev first, LLM under p 0.7). Retrieval (§3.3) may use word overlap: it only widens what is read.
2. **Two code floors stay in verify/enforce:** P0 only for a profile-tier contact, an escalation/incident, or a
   family conflict; suspicious content never P0 and never acted on. "Never raise priority because the email says
   so" is therefore code, not only prompt.
3. **Cache key** gets the as_of date for reader and sweep roles (judgment depends on today); ~$0.20–0.30 a morning
   cold, cached within a morning. Eval matrix ≈ $4–5 a world. **Key needs about +$15.**

## 3. Cost and time

| Milestone | Work | Hours | Stop? |
|---|---|---|---|
| P0 | this plan, tag | done | **approve** |
| P1 | signature parser + contact classifier (cached per contact), retrieval | 2.5 | |
| P2 | `Finding`, thread reader prompt, raw-thread renderer, Finding → Candidate/TriageResult mapping; `digest run` produces a digest from readers alone | 3 | **show 5 planted threads: raw ↔ Finding ↔ v1 triage** |
| P3 | 3 sweeps | 2 | |
| P4 | safety nets (trim candidates.py), reconciliation via linker, merge via linker | 1.5 | |
| P5 | compose raw excerpts, materializer raw message | 1 | |
| P6 | eval: reader diagnostics, rescue list, assertion remap, v1/v2/baseline table; run dev + held-out | 3 + runs | |
| P7 | spec/doc updates (§8), data audit (§7), README/DESIGN | 1.5 | |

≈ 14–15 hours of work plus ~2 hours of runs. Realistic finish: Wednesday daytime. Fallback at any point: v1 is tagged
and complete.

## 4. Data audit (§7) — done at P7, reported before any generator change

Sample 10 background emails and 5 storyline emails into `eval/data_audit.md`: realistic? trap too obvious?

## 5. Open points for Shubham (answer with the approval, or default applies)

| # | Question | Default |
|---|---|---|
| a | Held-out: run v2 on it once at P6 (never tuned on), same as v1? | yes |
| b | Delete the extraction payload types outright, or keep them in `schemas.py` marked deprecated until P7? | delete at P4 once nothing imports them |
| c | Reader model effort: Luna `medium` (like triage) or `low` (like the extractor)? | medium; measure cost at P2 |
| d | Newsletters: feed raw issues to the news sweep in batches, or keep a slim newsletter reader that lists items first? | raw batches; switch if the sweep misses the planted DeepSeek/MX Summit items |
