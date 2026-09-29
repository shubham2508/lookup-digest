# Status board

Each session appends a dated line when it finishes a milestone or gets blocked. Newest at the bottom of each track.

## Deadline
**Full scope today, 2026-09-28. Submission tomorrow morning; walkthrough the following week.** Nothing deferred. Next up: A → M4/M5 then M7/M8/M9 · B → M2 after Shubham's approval, then M8 held-out (anchor 2026-03-26) in a fresh session · C → M7/M8/M9 halves · orchestrator → integration as soon as A M5 + B M2 land, then M10.

## Orchestrator
- 2026-09-29 ~08:30 · **v2 built, merged, measured.** A/B/C merged into main; orchestrator: A5, reduce/merge fixes, compose v6, final matrices both worlds, in-session judge (#20), DESIGN.md/README/history/examples. Dev P0 100% · traps 126/175 · noise 5.5% · one thing 2/2; held-out P0 84.6% · traps 149/207 · noise 6.1% · one thing 2/2. Grader rewired without string similarity (#23). Next: docs/handoffs/NEXT-SESSION.md (exports, push).
- 2026-09-29 ~05:00 · **v2 pivot approved** (specs/PIVOT_SPEC.md, MIGRATION_PLAN.md). v1 tagged `v1-extraction-centric`. Shared contracts landed: `Finding` schema, `digest/findings.py` mapping, reader/sweep roles, `cache_salt`, `findings.jsonl`. Three worktrees: `../lookup-digest-v2-{a-readers,b-spine,c-eval}`; gate after A's P2: 5 planted threads side by side (`v2-A-checkpoint.md`). The tracks' reports are folded in below.
- 2026-09-28 ~23:00 · Known issues fixed in code; Jev behind the linker (196e557). No final numbers on this code yet. **Next session: read docs/handoffs/NEXT-SESSION.md.**
- 2026-09-28 17:20 · First dev day (26) exposed a candidate flood (124 candidates, 50 items, $0.47/run) and the S3 trap failing. Fixed in compute + prompts: cold-inbound threads never become candidates; Capital asks without a deadline carry `below_quiet_threshold` and triage excludes them before 3 business days (S3); news attaches only to exact contact/org slugs or whole active about-key slugs (14 → 1); schedule contradictions use one occurrence per recurring event; claim conflicts only when they touch a profile fact or a draft; about-key merge unifies board-update spellings, offer~candidate, and same-kind token overlaps; triage v3, compose v2 (one thing = one item). Day 26 rerun: 93 candidates, 31 items, $0.05. Matrix relaunched. Held-out authored by B (de321b4), gated on review; its run also needs the key limit raised (≈ $1.5 more).
- 2026-09-28 16:20 · **Integration started.** B M2 landed (523 emails, 416 labeled items, 182 assertions). #15 done: simulation runs write to `<as_of>_sim` (`--tag` on run/answer; history and scorer keyed by tag). Running `digest eval --matrix --world dev --keep-going` → `runs/dev/matrix.log`, `runs/dev/integration.json`, then `eval/reports/dev_*.md`. README finalized; DESIGN.md results line waits for the report.
- 2026-09-28 15:05 · Ruled #13, #14 (accepted), #15 (simulate → `_sim` run dirs via `RunContext.tag`). Fixed `runs.py` list-of-models JSON bug (C's finding). Board: A done M3–M9 · C done M6–M9 + matrix · B mid-M2 (90 threads, 10 notes, generator 1.4k lines, validator not yet green) and mid-M8. Integration starts the moment `data/dev` + `eval/manifests/dev.yaml` land.
- 2026-09-28 · Ruled on OPEN_QUESTIONS #2, #3, #6–#12 (all accepted as the tracks implemented); pinned reduce/actions/verify models and run-dir suffixes; labeled every fixture manifest item. Suite green.
- 2026-09-28 · M0 done. 43 tests green; `digest llm-check` shows a live Luna call costed ($0.000035) and cached. Handoffs written. Next: integration once A M5 + B M2 + C M6 land.

## A · Product
- 2026-09-28 · M3 done. `digest run --world tests/fixtures/mini --as-of 2026-09-24T06:00` → ingest (as_of filter, variants), normalize (threading, quote/signature split, forwards→`forwarded_by`, RRULE ±30/14d, freshness), router, profile compiler (P1 v2 → `profile/profile.yaml`, cached by hash), extractor (P3 v1, evidence check in code) → `extractions.jsonl` + store; 9 Luna calls ≈ $0.01, 19/19 quotes verified, 0 degradations; exits 3 until M5 (stages compute→render pending). 38 `test_a_*` tests + boundary green. Contract notes in OPEN_QUESTIONS.md #6 (thread/source ids, Avery's address from data, tasks.md mtime vs git, variants in ingest). `tests/test_cli.py` no longer lists `run` as a stub. Next: M4 compute, then M5 (deadline).
- 2026-09-28 · M4–M9 done. `digest run --world tests/fixtures/mini --as-of 2026-09-24T06:00` produces a full digest (exit 0): compute (contacts §6.1 order, behavior stats, drift/effective facts, about-key merge with logged merges, all 20 candidate rules as pure functions, context ±14d, freshness caps) → triage P4 v2 (packs of 6, per-candidate retry, code checks: citations verbatim, never_draft→message_person, recruiter drafts dropped, suspicious never P0) → reduce (merge by about, sort, K cap, every P0 survives) → compose P5 (validated: ids, placement, question budget, code fallback) → materializer P6 (LLM drafts with ≤3-sentence/banned-phrase check + retry; templates for 8 types) → verify (11 hard rules, fixes logged) → render (§9 grammar C's parser reads) → store `digest_items`. Fixture run: 12 candidates, 7 items, 129/350 words, 0 violations, ≈$0.005. M7: `--customize` via P2 + locked invariants in code; focus `only` hides non-focus items and keeps P0 as 'Also outside your filter'; 3 honesty variants flow through the header and item text. M8: `digest baseline` (one Luna call, corpus truncation oldest-first) → `…_baseline/`. M9: `digest answer Q<n> <opt> --world w` → `runs/<world>/rulings.yaml` (settings.store.rulings_path_template) + store; triage sees matching rulings, header says 'applied N learned rules'; `times_surfaced` / `resolved_later` / answered-after-digest across runs. Found and fixed a bug in shared `digest/llm.py` (`_strip` deleted the `Ambiguity.default` property → every triage pack failed; OPEN_QUESTIONS #14c). 95 `test_a_*` tests; full suite green except `test_b_world` (stale M1-gate assertion) and `test_c_simulation::…ignores_rulings` (flaky: pass/fail on identical code). Notes #14a–g in OPEN_QUESTIONS.md. `data/dev` not generated yet: the real dev run + `digest eval` is the next step at integration.

## B · Data
- 2026-09-28 · M1 **approved by Shubham** (all 16 storylines `reviewed: true`, judgment calls confirmed, S3 kept as drafted). Gate open for M2.
- (not started) Next: M1 storyline drafts → Shubham review gate.
- 2026-09-28 · M1 drafted, **waiting on Shubham's review gate**. `world/dev/`: world.yaml (anchor 2026-09-24, 24 orgs, 60 people with truth/style), 16 storylines with beats, labels, per-run-day expectations (26–30), assertions (AssertionKind + args), sim_avery answers, S1 `fulfilled` variant; background.yaml (full + pass-1 targets, TalentBridge ×3, injection, 3 expense reports, Stripe payout, EU AI Act decoy, 12 classification cases, every must-not with reason); calendar.yaml, notes.yaml (10 notes + 5 tasks), variants.yaml (honesty). `tests/test_b_world.py` green (14). Questions #8–#13 in OPEN_QUESTIONS.md (business-day rule, computed about keys, citation-fallback matching, cadence edges, S2 last-word intent, judgment calls). No data generated. Next: review → `reviewed: true` → M2 pass 1.

- 2026-09-28 · **M2 done, full size.** `digest generate --world dev` → `data/dev/` (523 .eml, both .ics, 10 notes, tasks.md with `<!-- last-modified -->` headers and 12-day-old mtime) + `data/dev__fulfilled/` (S1 variant) + `eval/manifests/dev.yaml` (416 items incl. 32 calendar events, 64 contacts, 182 assertions, 5 variants, 8 sim_avery answers; 436 KB). Validator (§9) passes: every must_include verbatim, threading resolves, PT offsets, no label words, pronoun check, category counts within ±10% (internal 104/100, notifications 69/70, newsletters 80, customers 69/70, marketing 61/60, investors 39/40, recruiters 25, vendors 26/25, hiring 20, lawyer 15, personal 15). Prose under `world/dev/prose/` (FORMAT.md is the contract; 11 subagents wrote it). Renderers: RFC 2047 headers + 8-bit UTF-8 bodies, `>` quoted history, Gmail-style nested forwards (the 14-message Northstar chain), VTIMEZONE/RRULE/PARTSTAT/CREATED. `tests/test_b_generate.py` (7) + `test_b_world.py` (14) green; suite green. Notes for C: `ExpectedItem.actions` holds only must-have actions; any-of choices are in `notes` ("actions_any: […]") and in the assertions' `actions_any`. Notes for A: forwarded chains render as one forwarded header block plus nested `>` quotes; event uids carry no domain (`event:lumen-demo-20260924`). Next: M8 held-out (separate session, in progress).
- 2026-09-28 · M8 authored, **waiting on Shubham's review gate**. `world/heldout/` (anchor 2026-03-26, DST crossing on day 12 in the history): world.yaml (65 people, 24 orgs; profile names kept, everyone else new), 16 storylines with the same trap types in new disguises (disguise map in `world/heldout/README.md`; reference-customer roles rotated), background (HireVector pattern, NimbusPay injection, Brex ×3, Gusto payroll-funding failure, EU CRA decoy, all §6 cases), calendar, notes, variants, and full prose (Fable 5.1 agents). Dry-run of M2's generator into the scratchpad: 529 emails + `fulfilled` variant + manifest; validator clean except `reviewed: false`. `tests/test_b_heldout.py` green (17). Next: Shubham flips `reviewed: true` → `digest generate --world heldout`.

## C · Grader
- 2026-09-28 · M6 done (scorer side). `digest eval --world tests/fixtures/mini --runs tests/fixtures/mini_runs` writes `eval/reports/tests_fixtures_mini_2026-09-28.md`: per-stage metrics (§2.1–2.5), P0 gate (fails on purpose: the fake run's triage drops the daycare P0), 32/32 assertion checkers, stage attribution with `file#Lnn` links, judge (E1, skipped: no model yet; calibration table via `--calibrate-judge`), sim_avery (E2, code-first + LLM fallback), `eval/history.py`, expected `eval/expected/profile.yaml` + field diff (Shubham reviews), six `profile/customize/*.md` + `eval/customize_suite.yaml`. Also scored A's real M3 extractions on the fixture: 6/6 joined via `thread:<Message-ID>`, all fields correct. 117 `test_c_*` tests; full suite green. Contract gaps in OPEN_QUESTIONS.md #7 (reduce/actions/verify shapes, manifest message labels on every item, customize/baseline run-dir suffixes, about-merge log, assertion arg shapes). Next: real `digest eval --world dev` at integration; M7 customize/variant runs.
- 2026-09-28 · M7/M8/M9 eval halves done on fake artifacts. **M7:** conditions scored as rows (report §4): honesty variants via `eval/variant_suite.yaml` (§5; `tasks_stale` on default runs when the manifest declares it), storyline variants against their own run-day expectations, customize suite (§6) with `p0_kept` (no P0 hidden vs the default run) and a formal-tone shift check. **M8:** baseline scored from `digest.md` alone (citation resolver, action parser, about-key inference), digest-level metrics + citation validity, pipeline-only kinds n/a, misses attributed to `baseline`; baseline and held-out columns in the summary, baseline digest judged. **M9:** `digest simulate [--fresh]` saves `simulation.json`; generic §7 checks (ruling recorded, ruling applied next run, escalation framing) + the manifest's multi-day assertions (report §6). #9 candidate-key fallback implemented. Fixture: 10 condition runs under `tests/fixtures/mini_runs/` (planted: `no_notes` unhedged draft; baseline wrong one thing, marketing, draft to Sam). 145 `test_c_*` tests; full suite green. New question #13 (rulings.yaml path, simulate state). Next: real `digest eval --world dev` + `digest simulate` at integration.
- 2026-09-28 · #13 applied + integration matrix. (13a) rulings path from `settings.store.rulings_path_template` (also used by `simulate --fresh`); (13c) `run.json.rulings_applied` preferred, header regex fallback. Matrix: `digest eval --matrix --world dev|heldout|<path> [--dry-run] [--keep-going]` or `scripts/integrate.sh <world>`: run days, 3 honesty variants + 6 customize + baseline on the last day, `simulate --fresh`, then `eval --customize-suite --baseline`; log in `runs/<world>/integration.json`; exit 0 ok · 3 blocked · 1 failed. On `tests/fixtures/mini` against A's real pipeline: 13/13 steps ok; report `eval/reports/tests_fixtures_mini_2026-09-28.md` (P0 100% pipeline and baseline, traps 7/7 vs 4/5). dev/heldout: blocked (exit 2) until B writes their manifests. Found on real output: **`contacts.json` is written as model repr strings** (`RunContext.write_json` doesn't dump a *list* of models; orchestrator-owned `digest/runs.py`), reported as a malformed artifact, not a crash; the #9 fallback now also matches rendered items and triage (A keys the pediatrician conflict `family:wren`); markdown parser handles quoted draft lines and `↳ Decide:`. 159 `test_c_*` tests green (B's in-progress `test_b_*` failures are B's).

## Blockers / waiting on Shubham
- **Held-out storyline approval** (`world/heldout/storylines/*`, 16 files, `reviewed: false`) → orchestrator flips → `digest generate --world heldout`.
- **OpenRouter key limit** still $3 (≈ $2 left): enough for the dev matrix, not for the held-out extraction + matrix (≈ $1.5). Raise to ~$15.
- Export `sessions/B-data_M8.txt` from the held-out session.
- (none) · #13 (rulings path, --fresh, header phrase) ruled in OPEN_QUESTIONS.md → Decided; Track A implements in M9.
- Judge model pick (OPEN_QUESTIONS.md #1) — after the Fable calibration round (`judge_reference` role). Scorer work is unblocked.
- Held-out review gate (Track B M8): 16 `world/heldout/storylines/*.yaml` expectations blocks need `reviewed: true` before `digest generate --world heldout` renders data + manifest.

## v2 track reports (2026-09-29; folded from the per-track STATUS files)

### Track A · readers
**2026-09-29 · stopped at the P2 gate.** Review: `docs/handoffs/v2-A-checkpoint.md` (five planted threads, raw ↔ Finding ↔ v1
triage, plus seven problems that need a decision). P3–P5 wait for Shubham.

#### Landed (branch `v2-a-readers`)

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

#### Cost of a Thursday run (dev, 2026-09-24T06:00, cold cache)

$0.211: 175 reader calls $0.205 (≈ $0.0012 per thread), compose $0.006, materializer $0.001. Reading 198 s at 8 workers.
Warm rerun of the same morning: $0 for readers.

#### Not done (waits for the gate)

- **A5** (P5): compose raw excerpts (`item_view`, `compose.md` v5), materializer raw message (`materializer.md` v3).
- Checkpoint problems #2, #3, #6 and #7 are Track A work planned for P5; #1 and #4 are Track B's (retrieval, `group_findings`).

#### For the orchestrator (merge notes)

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

### Track B · spine, sweeps, safety nets, reconcile
**2026-09-29 · B1–B5 done, integrated with main (A and C already merged) on branch `v2-b-spine`, suite green.**
Decisions taken unattended: `OPEN_QUESTIONS.md` #22 (a–i). Ready for the orchestrator's merge.

#### Landed

| Deliverable | Where | Notes |
|---|---|---|
| B1 spine | `digest/compute/contacts.py`, `prompts/signature_parser.md` v1, `prompts/contact_classifier.md` v2 | `build_contacts(world, profile, linker, llm, ctx)`. Profile (email or exact name) → internal domain → automated → classifier (LLM, one cached call per contact with mail; input = parsed signature, domain, same-domain profile contacts, role rules, ≤5 messages, all-visible stats: no run date, so it re-runs only on new evidence) → role-at-org by the linker (signature title/org + the classifier's reason) → learned domain as fallback → org-tier inheritance (moved here) → behavior stats. Signature fields and classifier quotes are checked against their source; stage checked against the category's vocabulary. `ContactDirectory.signatures` / `.classifications` keep the raw outputs. Dev: 138 contacts, 5 unresolved; recruiters, family, candidates, investors, deal counsel all right on inspection. |
| B2 retrieval | `digest/compute/context.py` `retrieve()`, `ContextRef` | events ±7 d with the same people or org, note lines (±1, with `L<n>`) and tasks mentioning a participant, org or subject word, the two related threads with the same people ranked by subject-word overlap (before or after the thread), first + last message verbatim; ~4k-token cap, most relevant first. Word overlap here only. Fixes checkpoint problem #1: thread 5's false "overdue feedback" finding is gone in the integrated run. |
| B3 sweeps | `digest/compute/sweeps.py`, `prompts/calendar_sweep.md` v1, `notes_tasks_sweep.md` v2, `news_sweep.md` v2 | `run_sweeps(world, directory, findings, profile, settings, llm, ctx, as_of)`; three calls in parallel, `cache_salt` = as_of date, batches at ~60k tokens; code hands over the date math (day labels, overdue days, overlaps with other events and deep-work blocks, the weekdays after each note's date); citations checked per sweep (`event:` quotes are titles). Dev Thursday: calendar 3 (Lumen deep work, Wren collision, the moved IPV call now colliding with Monday's leadership sync), notes 5 (overdue monthly update with stale ARR $3.2M vs $3.4M, Plant Bundle sign-off, Lumen vs Metrika, SOC 2 task already done, profile drift), news 3 (Halberd and Northstar case studies at MX Summit, DeepSeek-V4 Pro −30% against Priya's inference-spend decision), no decoys. |
| B4 safety nets | `digest/compute/candidates.py` (1010 → 502 lines) | `safety_nets(ci) -> list[Finding]`, `ComputeInputs(world, profile, settings, as_of, directory, findings=…)`. Kept: waiting on Avery (capital ≥ 3 business days → `quiet_thread`; other P0 → `reply_owed`; a teammate's reply counts), reference customer past end of day, deep work, family (personal-domain events), double booking, recruiter pattern, stale source (`needs_avery: no`), suspicious (reader-reported + code guard, never P0, no action), automated requests. Each `why` starts with the computed fact. Deleted: every extraction rule, `aboutkeys.py`. |
| B5 reconcile + merge | `digest/compute/merge.py`, `linker.py` (task `net_covers_finding`) | `reconcile(findings, nets, linker, *, msg_thread=None, summaries=None, ignore_entities=(), log=None)`: a waiting net on a thread the reader read is covered by that reading (attached to a same-thread finding, or closed as judged; #22a); every other net goes to the linker with options narrowed and labelled by hard facts ([same message] / [same event] / [same thread] / [same person]); decisions go to `links.jsonl`. `group_findings(findings, linker)` (same-kind about tags via `Linker.group_topics`), `apply_merges`, `thread_of`, `net_fact`. Dev Thursday: 22 nets → 8 attached, 6 closed by the reader, 6 by the linker, 3 rescues (TalentBridge pattern, Ramp ×3, Stripe payout). |
| Driver | `python -m digest.compute.sweeps --world dev --as-of 2026-09-24T06:00 [--findings runs/…/findings.jsonl]` | prints contacts by category, nets, sweep findings, reconcile decisions and rescues; reads reader summaries from the run's `trace.jsonl`. |

Tests: `tests/test_b_compute.py` (28: formulas, spine resolution order, classifier input (evidence not names, stable
across mornings), signature/classifier checks, fixture nets, retrieval ×2, every net, reconcile ×4, merge),
`tests/test_b_sweeps.py` (6: inputs of each sweep, batching, citation check + origin + salt, end to end on the fake
client), `tests/b_fakes.py` (fake answers for the three new schemas; `a_fakes.FakeClient` routes to it). `tests/test_a_compute.py`
deleted (its formula tests moved). Full suite green after merging main.

#### Cost

Dev Thursday, cold: spine ≈ $0.03 (52 signature + 63 classifier calls), sweeps ≈ $0.01–0.02, linker < $0.01. Integrated
`digest run` on this branch: $0.27 cold (readers $0.24 of it, cache cold because retrieval changed their input), $0.01
warm. Total spent this session ≈ $0.40.

#### For the orchestrator (merge notes)

- Branch contains `Merge branch 'main' into v2-b-spine` (conflicts in `compute/__init__.py` and `test_a_stages.py`
  resolved to main's) and one commit touching A-owned files, labelled "integration" (#22g): review or revert.
- **Reduce (#22h):** identical coarse keys across threads are not joined (`meeting:ipv-diligence-call` on 4 findings
  and `family:wren-pediatrician-2026-09-24` on 2 in the dev digest), and `group_findings` merges only take effect on
  qualified keys. Cross-kind duplicates (Priya's backfill cap: `approval:inference-spend-plan` vs
  `other:backfill-concurrency-cap`) are not compared at all (same-kind rule from the handoff). Suggest: reduce joins
  identical v2 keys that share an entity, and every key pair in `comp.about_merges`.
- `eval/history.md` needs a line for the new prompt versions (#22i), with the P6 run.
- `digest run` on dev Thursday: 547 → 396 words after the reconcile fix, still over the 350 budget (compose).
- Heldout was not run (no tuning on it; #20: API spend only for producing digests).

### Track C · eval
**2026-09-29 · C1–C5 done on branch `v2-c-eval`; stopped.** 360 tests green (Track C 159 → 181). Interpretation
choices made unattended are in `OPEN_QUESTIONS.md` #21 (a–f); please confirm or redirect.

#### Landed

| Deliverable | Where | Notes |
|---|---|---|
| Findings in the run view | `eval/scorer/artifacts.py` | every `findings.jsonl` row becomes a `Signal` (origin, kind, about keys, resolved sources, needs_avery, live = yes or unsure-with-card, rescued); a candidate with no finding behind it (v1 runs, fixtures) becomes one too. `findings` is required, `extractions` optional |
| C1 reader diagnostics | `eval/scorer/readers.py` (replaces `extraction.py`) | per run day: reader recall on threads expected to need Avery, priority in the backing item's band, an expected action type, must-not precision, unexpected yes on other threads, labeled noise clean, "not read" vs "read, no finding" (reader calls are tagged by thread in `cost.jsonl`). Truth rules: #21e |
| C2 sweep & net diagnostics | `eval/scorer/sweeps.py`, `merge.py`, `spine.py` (replace `compute.py`) | planted calendar and notes/tasks traps found by any live finding (by origin); **rescue list** with what each rescue matched; merge errors (expected item rendered twice, one item for two expected items) + the about-merge pairs; contact classification per contact |
| C3 assertions | `eval/scorer/common.py` `select_signals`, `assertions.py` | candidate kinds match a live finding by v1 name or by about key (free-text kinds only; structural analogs for contradiction / suspicious / news); key-only selectors borrow the answer key's sources (#21a); count by key for rule-less types (#21d); extra selectors `source_id`, `source_kind`, `category`, `system`. `triage.py` = judgment metrics on `triage.jsonl` + hard-rule checks (never-draft action, suspicious at P0, uncited) |
| Attribution | `eval/scorer/attribution.py` | spine → read → sweep → net → merge → compose → materialize → verify; a code floor overriding a right finding → `net`; verify now its own stage |
| C4 report | `eval/report.py`, `eval/v1_results.yaml` | §1 v1 / v2 / baseline × dev / held-out (P0, traps, must-not, one thing, judge digest + drafts, cost, runs); v1 fixed from the handoff; baseline live when a run exists, else the v1-era number (†); v1 rescored with this scorer on a line under the table. §2 "Diagnostics" per day: digest (target), read, sweep & net (+ rescue list), merge, judgment, spine, materialize |
| C5 judge | `eval/judge/judge.py`, `eval/cli.py` | `--judge` (DeepSeek) unchanged and tested with a fake client; **in-session judging (#20):** `--judge-export items.jsonl` writes every item with its rendered `prompts/judge.md`; `--judge-scores scores.yaml` reads the session's scores back (validated like API output) into §1 and §5. Conditions and simulation still score from the unchanged artifacts |
| Fake runs | `tests/fixtures/mini_runs/make_fake_run.py` | `findings.jsonl` in all 10 runs; planted: Sam's reader says no (P0 gate fails), Lumen sweep at P3 / no decide, no news attachment, two net rescues (DocuSign, pediatrician), spine and materializer defects as before |

#### Measured

| Run | P0 | Traps | Must-not | One thing | Notes |
|---|---|---|---|---|---|
| v1 dev runs, rescored (5 days) | 100% | 118/175 | 6.6% | 100% | as reported 115/175: +3 are items v1 rendered under other keys (#21a) and the approval count (#21d) |
| v1 held-out runs, rescored | 84.6% | 137/207 | 6.6% | 50% | as reported 129/207 |
| v2 dev Thursday, readers only (A's P2 run, day 30 only) | 87.5% | 56/124 (52 not run: other days) | 6.0% | 0% | reader recall 92% (24/26), priority in band 86%, action type 40%, must-not precision 88% (15 of 123 must-not threads said yes), trap recall 5/11 (no sweeps/nets yet), 3 duplicated items (no merge yet). Report in the session scratchpad, not committed (partial run) |

#### For the orchestrator

- Run `digest eval --world dev` (and `heldout`) once B's sweeps/nets and A5 are merged and the five mornings are run;
  the report then carries the full comparison table, diagnostics and rescue list. Judge: `--judge-export`, judge
  in-session, `--judge-scores`.
- The base fake run keeps its committed v1 `extractions.jsonl`: `test_a_stages.py` / `test_a_compute.py` read it.
  Delete it once no test does.
- `OPEN_QUESTIONS.md` #18 (claimed-key guard) is still open and untouched; with readers' light tags it bites less.
- `/export sessions/C-grader_v2.txt` from this session (Shubham), grep it for `github_pat_|sk-or-|OPENROUTER_API_KEY=`.
