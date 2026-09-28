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

### 4. Storyline review — M1 gate (Data session) — **drafted, waiting on Shubham**

All 16 files in `world/dev/storylines/` are drafted with 5 run-day expectations and assertions each (`reviewed: false`). The orchestrator's structural pre-review found every storyline complete against the checklist in `docs/handoffs/B-data.md`. Shubham approves (or lists changes) and the orchestrator flips `reviewed: true`; then `Track B, M2` renders the full world.

### 5. Judgment calls in the answer key that Shubham should confirm (Track B, M1) — part of the M1 review gate

Recorded in the storylines as `notes:`; listed here so they are not missed during review:
- S1: the **one thing on day 29** is the cap table (6 h overdue), over Priya's inference email (S13) and the diligence-call contradiction (S2).
- S2: priority **P0** for the calendar contradiction on days 29–30 and for Elena's prep request on day 30 (Capital during the raise).
- S4: David Kim's tier is a band **[P0, P1]** (the profile's "another VC" rule, not named).
- S6: the day-30 forward is **P1 in Decisions** with `question`/`read`, never a `reply` draft; the cadence item stays a separate **P2 watch**.
- S7: the second renewal slip is **P1 in Pulse** with `question`/`decide`/`watch`/`task` all acceptable.
- S11: the daycare closure is its own **P0** item (may be composed with the pediatrician item as long as both sources are cited).
- S13: Priya's item is **P0 in Decisions** (a decision, not a reply); the price-cut news attaches on day 30 only.
- Background: the injection email is a P2/P3 one-liner in Pulse (flagged), the press request P2, the tax notice P2, Jae Whitlock P3 "unsure", the wedding invite absent.

### 13. Track C · M9: where `rulings.yaml` lives, and how `digest simulate` starts clean (C-grader, 2026-09-28): built as suggested

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 13a | **`rulings.yaml` path.** architecture §10 names the file; no spec says where. The simulation checks that an answered card produced a ruling for that scope. | (1) `runs/<world>/rulings.yaml`, next to `store.sqlite`; (2) repo root; (3) `profile/rulings.yaml` | (1). The scorer reads (1), then falls back to (2). Entries as §10: `{id, scope: {contact\|about\|thread_kind}, ruling, option_chosen, from_question, created, expires}`. |
| 13b | **Simulation state.** `digest simulate` runs days 26–30 in order, so rulings and digest history must start empty, or earlier runs leak into the escalation and ruling checks. | (1) `simulate --fresh` renames `runs/<world>/rulings.yaml` and `store.sqlite` to `*.bak-<timestamp>` first (reversible, never deletes); (2) product flag `--state-dir`; (3) accept leakage | (1), opt-in; without it the report notes any pre-existing rulings. |
| 13c | **"applied N learned rules"** in the header (§10) is how the scorer sees a ruling applied when triage output alone is ambiguous. | keep the phrase · redirect | Keep; the scorer matches `applied \d+ learned rule`. |

## Decided

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
