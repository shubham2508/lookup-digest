# Open Questions

Claude Code: add questions here instead of deciding silently. Format: what · where · options · suggestion.
Shubham reviews every addition (checkpoint 4). Answered items move to **Decided** at the bottom, with the date.

## Pending decisions for Shubham

### 1. Model IDs per role (`config/models.yaml`) — judge still open; needed to finish M0

Direction from Shubham (2026-09-28): small budget; GPT-6 Luna is the workhorse at per-stage reasoning effort; **generation is done by a Claude Code session (Fable 5.1), not by an API model** (decided, see bottom); a stronger model only for the judge, chosen after a short calibration. Family rule: judge ≠ OpenAI (pipeline) and ≠ Anthropic (generator). Prices are $ per 1M tokens, in / out, from the live OpenRouter catalogue; all support structured output, and Luna supports `reasoning_effort`.

| Role | Direction | Options |
|---|---|---|
| `extractor`, `triage`, `compose`, `materializer`, `compiler` | `openai/gpt-6-luna` (0.10 / 0.50), per-role `reasoning_effort`: extractor low · triage medium · compose high · materializer low · compiler low | `openai/gpt-6-luna-pro` (same price) for `compose` only |
| `generator` | **decided:** Claude Code session (Fable 5.1) writes the prose files; `generator/` code assembles, labels, validates | — |
| `judge` | third family; mid-tier is enough, because it applies one fixed rubric with the evidence attached, and everything with an expected output is scored by code | `google/gemini-3.8-flash` (0.75 / 3.75, ≈ $1 total) · `x-ai/grok-4.7` (1.6 / 4.8, ≈ $1.6) · stronger fallback `google/gemini-3.1-pro-preview` (2 / 12, ≈ $3) |
| `sim_avery` | cheapest; mostly code (matches a question card to the manifest's intended answer by about-key), LLM only as fallback | `openai/gpt-5-nano` (0.05 / 0.40) or reuse `gpt-6-luna` |

Judge plan (Shubham, 2026-09-28): the first judging round runs on Fable via the `judge_reference` role in `config/models.yaml` (≈ $1 for ~20 items); the third-family candidate (Gemini 3.8 Flash or Grok 4.7) scores the same items with the same rubric; agreement within 1 point on ≥ 80% keeps the cheap judge, recorded in DESIGN.md. Fable is never the judge of record (same family as the generator). Shubham picks after that round.

OpenRouter spend on this config ≈ $4–5 (pipeline ≈ $3, judge ≈ $1–1.6, sim_avery ≈ 0). Generation costs nothing on OpenRouter.

### 14. Track A · M4–M9 notes (A-product, 2026-09-28): implemented as suggested; confirm or redirect

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 14a | **`calendar_conflict:family` without an overlapping work event.** §6.4 requires overlap with an accepted/organized work event, but the M4 acceptance (and the fixture) expect the pediatrician at 15:00 with nothing booked. | (1) strict overlap only; (2) also flag a personal-domain slot that falls inside the workday (Mon–Fri 09:00–18:00) with `facts.overlaps_work_event = false`, triage decides | (2). Overlaps, when present, are listed in `facts.overlaps`. |
| 14b | **Calendar freshness.** §3 says `latest_item_time` = max event `last_modified`, so a calendar nobody edited for two days reads "calendar stale (2 days)" on quiet mornings. | (1) spec literal; (2) also count the `.ics` file mtime (the sync time) | (2): `max(event stamps, ics mtime)`; unreadable/missing still flagged; `corrupt_ics` still yields "calendar unreadable". |
| 14c | **`digest/llm.py` `_strip`** removed any schema key named `default`, including the *property* `Ambiguity.default`, so triage could never emit it (two failed packs per run). Fixed in place: keys inside a `properties` map are field names, never keywords. `tests/test_schemas.py` `_walk` adjusted the same way. Orchestrator-owned file; please review the 3-line change. | — | fixed |
| 14d | **Handoff example "Fri→Tue = 2 business days"** conflicts with the decided rule #8(a) (weekday dates strictly between message and run date: Fri→Tue = 1). | — | Implemented #8(a); `tests/test_a_compute.py` documents Fri→Mon 0, Fri→Tue 1, Thu→Tue 2, Wed→Tue 3. |
| 14e | **Triage packing.** `TriageBatch {results: [TriageResult]}` registered in `digest/schemas.py` (allowed by the handoff) so 5–10 candidates share one call; a pack that fails validation twice is retried candidate-by-candidate before any fallback. `BaselineDigest {markdown}` registered for `digest baseline`. | — | done |
| 14f | **`tests/test_cli.py`** lost `test_stubs_say_not_implemented`: every command is real now (A: run/answer/baseline; B: generate; C: eval/simulate). Replaced by no-state checks for `answer` and `baseline`. | — | done |
| 14g | **`digest answer` picks the latest plain run** (no variant/customize/baseline suffix) of the world; a question number refers to that digest only. `digest simulate` runs days in order, so this is the intended card. | — | done |

## Decided

- **2026-09-28 · Track C M7–M9 questions (#13, restored below), ruled:**
  (13a) **`rulings.yaml` lives at `runs/<world>/rulings.yaml`**, now `settings.store.rulings_path_template`; `digest answer` and `digest simulate` write it, the store's `rulings` table mirrors it, per-world so dev rulings never leak into held-out.
  (13b) **`digest simulate --fresh` (opt-in) stays**: it renames the old `rulings.yaml` and store aside, never deletes. The integration and eval runs always pass `--fresh` so the §7 assertions start from clean state.
  (13c) **The header phrase is `applied N learned rules`**, exactly as architecture §10 specifies, rendered when N ≥ 1 and omitted when N = 0. Track A also writes `rulings_applied: N` into `run.json`; the scorer prefers that field and falls back to the header regex `applied (\d+) learned rules?`. Track A confirms 13a and 13c by implementing them in M9.
- **2026-09-28 · Track A's edits to shared files accepted:** `digest/llm.py` `_strip` no longer drops a property that happens to be named like a schema keyword (a real bug: `Ambiguity.default` was being stripped); `TriageBatch` and `BaselineDigest` added to `digest/schemas.py` and `LLM_OUTPUT_MODELS`. A commits them with its milestone.

<details><summary>Track C's #13 as written (restored; my cleanup had dropped it)</summary>

### 13. Track C · M9: where `rulings.yaml` lives, and how `digest simulate` starts clean (C-grader, 2026-09-28): built as suggested

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 13a | **`rulings.yaml` path.** architecture §10 names the file; no spec says where. The simulation checks that an answered card produced a ruling for that scope. | (1) `runs/<world>/rulings.yaml`, next to `store.sqlite`; (2) repo root; (3) `profile/rulings.yaml` | (1). The scorer reads (1), then falls back to (2). Entries as §10: `{id, scope: {contact\|about\|thread_kind}, ruling, option_chosen, from_question, created, expires}`. |
| 13b | **Simulation state.** `digest simulate` runs days 26–30 in order, so rulings and digest history must start empty, or earlier runs leak into the escalation and ruling checks. | (1) `simulate --fresh` renames `runs/<world>/rulings.yaml` and `store.sqlite` to `*.bak-<timestamp>` first (reversible, never deletes); (2) product flag `--state-dir`; (3) accept leakage | (1), opt-in; without it the report notes any pre-existing rulings. |
| 13c | **"applied N learned rules"** in the header (§10) is how the scorer sees a ruling applied when triage output alone is ambiguous. | keep the phrase · redirect | Keep; the scorer matches `applied \d+ learned rule`. |

</details>

- **2026-09-28 · M1 storyline review: approved.** All 16 `world/dev/storylines/*.yaml` are `reviewed: true`; the eight judgment calls (former #5) are confirmed as drafted; S3 keeps the three-business-day rule.

- **2026-09-28 · full scope, no cut line.** Everything through M10 is built today; submission tomorrow morning; walkthrough the following week. Nothing is deferred.
- **2026-09-28 · held-out anchor = 2026-03-26** (Thursday = day 30; day 1 = Wed 2026-02-25; the window crosses the Mar 8 spring-forward on day 12, in the history, not in the run days). Held-out world is **full size** (~500 emails), same trap types, different disguises and names, written in a separate Data session.
- **2026-09-28 · Track A M3 contract notes (#6), all accepted as implemented:** (6a) `Extraction.source_id` = `thread:<root Message-ID>` / `note:notes/<file>.md` / `task:<slug-of-title>`; evidence ids `msg:<Message-ID>` (with brackets), `note:…#L<n>`, `task:<slug>`, `event:<uid>`; forwarded messages get `<fwdN.<parent id>>`. (6b) Avery's address detected from the data, logged as `owner_email`. (6c) the generator writes `<!-- last-modified: <ISO> -->` as the first line of `tasks.md` and every note; ingest prefers it over mtime. (6d) honesty variants stay in ingest. (6e) a required singleton evidence with a bad quote is replaced by a verbatim span and logged as `evidence_replaced`. (6f) `tests/test_cli.py` updated.
- **2026-09-28 · Track C M6 contract gaps (#7), all accepted:** (7a) `ReduceItem/ReduceResult`, `MaterializedAction`, `VerifyViolation/VerifyStats/VerifyResult` are pinned in `digest/schemas.py`; Track A writes `reduce.json`, `actions.jsonl`, `verify.json` in those shapes. (7b) every manifest email item carries `messages[].message_id`; the fixture manifest now does too; notes/tasks use A's source-id forms. (7c) `RunContext.suffix`: `--customize x.md` → `…_customize-x`, `digest baseline` → `…_baseline`, combined with `+`. (7d) compute/reduce writes `about_merges` into `reduce.json`. (7e) assertion arg shapes as defined in `eval/scorer/assertions.py`; Track B authors to them. (7f) done.
- **2026-09-28 · business days (#8): option (a).** Weekday dates strictly after the message date and strictly before the run date. S3 stays as drafted.
- **2026-09-28 · about keys for computed candidates (#9): (a) + (b).** The `world/dev/README.md` convention for the manifest; the scorer falls back to type + shared entity/citation when the key does not fuzzy-match. Track A uses the same slugs in compute.
- **2026-09-28 · expected-item matching (#10): option (b).** Fuzzy about key **or** any rendered citation in `cites_any`; "present" = full item, one-liner, or "Also pending" line.
- **2026-09-28 · cadence formula (#11): as suggested.** Each gap belongs to the window of its later message; if the recent window has no complete gap, use the current gap (as_of − last inbound); merge predecessor + successor at the same org/role. Track A implements exactly this with S6/S7 as the unit tests.
- **2026-09-28 · S2 (#12): option (a),** keep as drafted; the contradiction comes from the calendar join, not the thread's ball.

- **2026-09-28 · deadline:** the repo is submitted the morning of 2026-09-29; the walkthrough is the following week. Cut line recorded in CLAUDE.md ("Deadline") and `docs/handoffs/STATUS.md`. Building continues after submission until the walkthrough.
- **2026-09-28 · dev anchor = 2026-09-24** (Thursday = day 30; day 1 = 2026-08-26; run days Sun 20 – Thu 24 Sept; all PDT, no DST crossing). `world/dev/world.yaml` carries `anchor: 2026-09-24`; `digest generate --anchor` overrides. Held-out anchor is decided separately at M8.
- **2026-09-28 · OpenRouter key limit:** Shubham raises it; not a build concern. Cost is still logged per run.
- **2026-09-28 · commit policy (a):** each track session commits its own paths at milestone ends with a `[A-product]` / `[B-data]` / `[C-grader]` prefix; the orchestrator commits foundation, integration and docs; never `git add -A`; stagger commits if sessions run at the same moment.
- **2026-09-28 · generator = Claude Code session (Fable 5.1), not an API model.** The Data track session writes every email body, note, and background item as prose files with labels under `world/<world>/prose/`; `generator/` code turns them into `.eml` / `.ics` / notes / tasks with real headers, threading, and DST-correct dates, emits the manifest, and runs the validator. Reproducible from world files + committed prose; a changed beat means rewriting its prose file. Zero OpenRouter spend for generation. `models.yaml` records `generator: claude-code-session`.
