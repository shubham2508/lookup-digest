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


### 18. Scorer: a fuzzy "claimed" key blocks a citation match (orchestrator, 2026-09-29)

**What.** `_by_cites` refuses to match a rendered item to expected item X through its citations when the item's own
about key fuzzy-matches another expected item Y of that day, even if the item cites none of Y's sources. Dev day 30
(commit 4915503): the diligence-call contradiction was on the page as a P0 with both dates, citing Marcus's move
email and the calendar event, but keyed `deal:series-a:diligence`; that fuzzy-matches Elena's
`deal:series-a:diligence-prep`, so the report said "P0 missing".
**Where.** `eval/scorer/common.py` `_by_cites` / `claimed_abouts`.
**Options.** (a) Leave it: the pipeline now keys schedule contradictions by the meeting (1751a1e), so this case no
longer occurs. (b) Block the citation match only when the item also cites one of Y's `cites_any`.
**Suggestion.** (b), noted in DESIGN.md as a grader change made after results were seen. Your call; not changed.


### 21. Track C · v2 scorer interpretations (C-grader, 2026-09-29, unattended): built with the picks below; confirm or redirect

Where: `eval/scorer/common.py` (selectors), `readers.py` (C1), `assertions.py` (C3), `attribution.py`, `report.py`.

| # | What | Options | Picked |
|---|---|---|---|
| 21a | **Key-only selectors miss v2 items.** Readers write light tags (`deal:series-a`), so an assertion with an `about` and no `cites_any` (`S4-d30-present`, `S2-d30-0605-present`, …) finds nothing although the reader flagged the thread. | (1) keep key-only; (2) when a selector names a key but no sources, that day's expected items' `cites_any` for the key stand in; (3) add `cites_any` to every assertion (manifest edit, Track B) | (2), for every item-level check and the candidate kinds, v1 and v2 alike. On v1's own runs it credits items v1 rendered under other keys (franchise tax, press request): dev 115 → 118/175, held-out 129 → 137/207. |
| 21b | **Which v1 numbers head the table.** | (1) as reported (handoff C4); (2) rescored with this scorer (same rules as v2) | Column = (1), line under the table = (2), both in `eval/v1_results.yaml` (the v1 runs are overwritten by v2 runs). Suggest DESIGN.md quotes (2) for any v1-vs-v2 claim. |
| 21c | **C3 about alternative** ("type = v1 name **or** about matches"). Taken literally, rescoring v1 turned three passing absent checks into failures (an `approval_pending` candidate about `candidate:ines-ferreira` counted as a `hiring_stall`). | (1) any finding about the key; (2) the about alternative only for free-text kinds (a finding that names another v1 rule is that rule); `contradiction` / `suspicious_content` / `news_attachment` also need their Finding analog (`contradictions`, `suspicious_instructions`, the news sweep); only live findings (yes, or unsure with a card) | (2). With it, v1 rescored matches v1 as reported except the 21a/21d fixes. |
| 21d | **`count_items_of_type` without `about`** on a type v2 has no rule for (`cadence_drop`, `obligation_cadence`, …): the name never appears in v2. `about` was ignored in v1 (`BG-exp-one-item` counted all 19 approval items). | (1) name only; (2) that day's expected keys of the type, counted by key (not by shared note citations); honour `about` | (2) |
| 21e | **Reader diagnostics truth (C1).** The label rule (ball on Avery / open ask / open promise → yes) disagrees with the answer key on some threads: must-not threads with the ball on Avery (courtesy close, far deadline, S16 fulfilled elsewhere) and per-day timing (S3 before 3 business days). | (1) label only; (2) label + day rules | (2): thread fully visible at as_of; cited by an included item that day → yes with its band and actions (a must-not thread behind a pattern item, e.g. TalentBridge, not scored); `must_not_surface` → no; key in that day's `absent` or an excluded item cites it → no; `fulfilled_by_source` closes a promise. |
| 21f | **Stages the chain lacks.** | — | `spine` (before `read`) for contact classification; `net` also covers the code floors (`enforce`) when they override a right finding, and hard-rule violations in `triage.jsonl`. |


## Decided

- **2026-09-29 · Orchestrator fixes from the final dev runs (implementing the spec, no design change).** Traced with
  the debug-trap procedure; each is a commit with a test. Tier inheritance only at outside firms (every Tessera
  teammate had inherited the co-founder's P0). Jev picks under p 0.7 go to the LLM linker (an obvious meeting move
  came back 0.49). Schedule contradictions are keyed by the meeting, so a date ruling does not attach to the whole
  deal. Triage v6: no invented clock times; due by the next business day counts as today; a P0 contact's ask at
  the quiet threshold is P0. Extractor v3: a promise to deliver later does not answer an ask; event-implied
  deadlines; dated claims carry their date. Evidence match ignores markdown `*`. Ruling ids use the digest's date.
  Escalation framing and freshness qualifiers are enforced in code, including on Also-pending lines. compose.json
  lists the P0 one-liners outside a customize filter.

- **2026-09-28 · #16 the linker: LLM decides "same thing?", no word similarity in compute** (Shubham: "word-match things suck").
  *Before:* rapidfuzz thresholds decided topic-key merges (ratio ≥ 85), calendar event ↔ email meeting (≥ 55), promise already in tasks (≥ 80), promise fulfilled in another thread (≥ 70), task done per email (≥ 80), declined-meeting fallout (≥ 60–70), and news ↔ open item (exact words). They over- and under-merged on real data (five items for one board update; three job candidates merged into one).
  *Now:* `digest/compute/linker.py` + `prompts/linker.md` + `prompts/topic_grouper.md` (role `linker`, Luna, low effort). Code narrows the options with hard facts only (same people, ±7 days, later in time, same topic kind); one batched, cached LLM call per question type decides sameness and writes a reason; every decision goes to `runs/…/links.jsonl` and shows in the UI's LLM calls tab. Without an LLM, or if the call fails, only identical keys match: a missed link is visible, an invented one is not. ~8 calls, ~$0.2 per run cold, cached after.
  *Still string-based:* contact name/org/title matching in `digest/compute/contacts.py` (week two).
  *Alternative evaluated:* TypeSafe's Jev 1.13 (a classifier model, via OpenRouter's `/api/alpha/decisions`): 0.44 s and $0.00002 for a test question, answered correctly with probabilities, but gives no written reason. Plan: add it as a second linker backend after the final runs and compare on dev; not swapped in before the submission numbers.
  *Update (196e557, 1751a1e):* Jev now answers first (role `decider`); the LLM decides a question when Jev fails or its top probability is under 0.7 (`llm.jev_min_probability`). The submission numbers are on this setup.
  Commits: 0435905 (linker), 5038594 (prompt-example leak removed).
- **2026-09-28 · #17 prompt-example leak removed.** Worked examples in six prompts had copied dev storylines (S1 cap table 'will send it tonight', S2 diligence move, S3/S10 $3.4M ARR draft, S5 'Oct 6 still on' reply, S8 Mei, S13 DeepSeek price cut). All replaced with a made-up cast that appears in no mailbox; triage's 'Sam and Wren' rule now reads the family category from the profile. All scores before commit 5038594 were measured with the leak and are not reported as results. The `debug-trap` skill enforces a grep check for world names in prompts.

- **2026-09-28 · held-out planted-pattern section names** stay as the generator's dev names (`talentbridge`, `stripe_payout`), so the held-out manifest tags HireVector and Gusto as `BG-talentbridge` / `BG-stripe`. Cosmetic; renaming would touch the generator and both worlds. Noted for DESIGN.md.
- **2026-09-28 · integration fixes to Track A's compute and prompts** (orchestrator, after the first dev run): see STATUS 17:20. Prompt versions: triage 2 → 3, compose 1 → 2; `eval/history.md` gets the before/after line once the dev report exists.

- **2026-09-28 · Track A M4–M9 notes (#14), all accepted as implemented:** (14a) a personal-domain slot inside the workday is a `calendar_conflict:family` candidate even without an overlapping work event, with `facts.overlaps_work_event=false` for triage to weigh; (14b) calendar freshness = max(event stamps, `.ics` mtime); (14c) the `_strip` fix stands (reviewed: correct, keys inside `properties` are field names); (14d) the handoff example was wrong, #8(a) rules: Fri→Tue = 1; (14e) `TriageBatch`, `BaselineDigest`; (14f) `test_cli.py`; (14g) `digest answer` targets the latest plain run.
- **2026-09-28 · #15 simulate runs get their own folder.** `digest simulate` re-runs days 26–30 with rulings applied, so if it wrote to the plain run dirs the eval would score rulings-applied digests. Decision: `RunContext.tag` (added; joins the suffix) → `digest run --tag sim` writes `runs/<world>/<as_of>_sim/`; simulate passes `--tag sim` and the §7 checks read the `_sim` dirs; plain runs stay rulings-free for P0 recall and trap assertions. Small edits to `digest/cli.py` (`--tag`) and `eval/cli.py`/`sim_avery` (pass and read the tag); the orchestrator makes them at integration.
- **2026-09-28 · integration findings to verify on the real dev run** (from C's matrix on the fixture against A's pipeline; may predate A's final commit): `corrupt_ics` header must say the calendar is unreadable and no calendar conflicts may appear; `stale_inbox` must qualify overdue/quiet items with "may be a sync gap"; `weekend.md` must keep the cap-table P0 as a one-liner (locked invariant). Owner: orchestrator at integration, routed to A only if larger than a small fix.

<details><summary>Track A's #14 as written</summary>

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

</details>

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
