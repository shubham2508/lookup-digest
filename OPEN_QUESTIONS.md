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

### 2. Anchor date for `heldout` — needed at M8 (dev is decided: 2026-09-24, see bottom)

Day 30 must be a Thursday. Worlds are relative, so any Thursday works; the only real choice is whether the 30-day window crosses a DST change (PT offset flips −07:00 ↔ −08:00 mid-world, which exercises date parsing).

| Option | day 30 | day 1 | DST crossing | Note |
|---|---|---|---|---|
| dev A | Thu 2026-09-24 | Wed 2026-08-26 | none | "the last 30 days" as of setup; all PDT |
| dev B | Thu 2026-10-22 | Wed 2026-09-23 | none | recent at walkthrough time |
| heldout A | Thu 2026-03-26 | Wed 2026-02-25 | spring-forward on Mar 8 (day 12) | in the past |
| heldout B | Thu 2026-11-12 | Wed 2026-10-14 | fall-back on Nov 1 (day 19) | future-dated files |

**Decided for dev:** option A, 2026-09-24. **Suggestion for heldout:** option A, 2026-03-26, so held-out carries the DST flip in its history (not in its run days) as a fair extra stress; both are past dates, so file mtimes look normal. Decide at M8.

### 3. Held-out world size — needed at M8

Options: full ~500 emails · minimum ~150. Cost is now session time, not API spend.
**Suggestion:** full. The assignment says "synthetic data sets", plural, and a small held-out world weakens the anti-overfitting story.

### 4. Storyline review — M1 gate (Data session)

Every `expectations:` block in `world/dev/storylines/*.yaml` needs `reviewed: true` from Shubham before `digest generate` will run. Nothing to decide yet; this is a reminder that it is the largest single block of Shubham's time (~1–2 h of careful reading).

### 6. Track A · M3 contract notes (A-product, 2026-09-28) — confirm or redirect; implemented as suggested so integration is not blocked

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 6a | **Thread and source ids** for `extractions.jsonl` / evidence. No spec fixes the format; Track C's scorer must join my ids to the manifest. | (1) `thread:<root Message-ID without brackets>`, root = earliest real message; (2) opaque hash; (3) generator-assigned `t-0142` (the product can't know it) | (1). Evidence ids as the schema says: `msg:<Message-ID>` with brackets, `note:notes/<file>.md#L<n>`, `task:<slug-of-title>`; `Extraction.source_id` is `thread:…` / `note:notes/…` / `task:…`. Forwarded messages get synthetic ids `<fwdN.<parent id>>` and live in the `messages` table, so citations resolve. |
| 6b | **Avery's email address.** The extractor input lists it, `profile.md` never states it, and `config/` is orchestrator-owned. | (1) detect from the data: the address whose display name matches `ProfileConfig.person` in From/To/Cc/ICS CN, else the most frequent recipient; (2) add `owner_email` to `settings.yaml`; (3) add it to `profile.md` (verbatim from the assignment, so no) | (1), logged in `run.json` as `owner_email`. Happy to add (2) as an override if you want it explicit. |
| 6c | **`tasks.md` staleness via file mtime does not survive `git clone`** (mtime = checkout time, so the planted "12 days old" only holds on the generating machine). | (1) generator writes a sidecar or header line (`<!-- last-modified: … -->`) that ingest prefers over mtime; (2) accept: staleness is only exercised on the generating machine; (3) `digest generate` re-touches mtimes and the README says to run it after cloning | Ingest reads mtime today. Suggest (1) for B; A adds the header parse in a few lines once the format is named. |
| 6d | **Honesty variants live in ingest** (data_generation §10: `stale_inbox` = ignore mail after as_of−30h, `no_notes` = notes dir hidden, `corrupt_ics` = work.ics truncated at half). Implemented now as run conditions in `digest/ingest/loader.py` because the loader had to handle missing/unreadable sources anyway. | keep · move to eval-side data mutation | keep (zero extra code in M7; C's assertions can rely on `run.json.freshness` and `degradations.jsonl`). |
| 6e | **`Ball.evidence` / `Automated.evidence` are required singletons**, so "drop the fact" can't apply when only the quote is bad. | (1) replace with a verbatim span from the right source and log `evidence_replaced`; (2) drop the whole extraction; (3) relax the schema to optional | (1). Logged per item in `degradations.jsonl` and counted in `run.json.extract.evidence_replaced`; the fact keeps verbatim, code-checked provenance. |
| 6f | **`run` exit code at M3.** `digest run` executes compile → ingest → normalize → extract, writes `extractions.jsonl`, then exits 3 ("stages … not implemented (M4/M5)") so nothing mistakes it for a digest. `tests/test_cli.py` (orchestrator-owned) no longer lists `run` among the stubs; a `run` on a missing world exits 2 with a hint. | — | Note for the orchestrator; `eval` in the same test now fails because C's `eval/cli.py` also outgrew the stub (not touched by A). |

### 7. Track C · M6 contract gaps (C-grader, 2026-09-28): confirm or redirect; built as suggested, isolated in `eval/scorer/artifacts.py`

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 7a | **`reduce.json`, `actions.jsonl`, `verify.json` have no model in `digest/schemas.py`**, but the scorer needs item ids → about/priority/citations, drafts per recipient, and verify drops/stats. | (1) orchestrator pins them as Pydantic models in `digest/schemas.py`; (2) leave free-form, C adapts at integration | (1), with the shapes in the `eval/scorer/artifacts.py` docstring: reduce `{items:[{id, about, candidate_ids, priority, section, confidence, citations, proposed_actions, ambiguity, entities}], overflow, about_merges}`; actions `{item_id, type, target, recipient_name, recipient_category, brief, brief_assumptions, text, draft, assumptions, evidence}`; verify `{violations:[{rule, item_id, detail, fix: fixed\|dropped\|unresolved}], stats:{words, budget, header_present, items, items_cited, citations_total, citations_resolved}}`. The reader tolerates missing keys and files. |
| 7b | **Every manifest item needs `messages[].message_id`**: the scorer maps product evidence to manifest items only through them (A's ids in 6a are resolved this way). The fixture manifest labels 2 of 6 items; for unlabeled items absence checks pass vacuously (the report warns). Notes and tasks: the manifest `source_id` should use A's forms, `note:notes/<file>.md` and `task:<slug-of-title>`. | (1) B emits messages for every thread/newsletter/automated/marketing item, and the fixture manifest gets them (orchestrator); (2) scorer re-parses `data/` headers | (1). Tests patch the four missing fixture labels in `tests/c_helpers.py`. |
| 7c | **Run-dir names for customize and baseline runs.** `RunContext` names a dir by as_of + variant only, so a `--customize` run overwrites the default run of that day. | (1) `digest run --customize …/x.md` uses variant `customize-x`, `digest baseline` uses `baseline`; (2) a separate world dir per mode | (1): the scorer looks for `…_customize-<stem>/` and `…_baseline/`. |
| 7d | **About-key merges are not logged in any artifact**, so the §2.2 merge-accuracy metric can't be computed. | (1) compute writes `about_merges: [{canonical, merged:[…]}]` into `reduce.json`; (2) a new artifact | (1). Until then the report shows "not scoreable". |
| 7e | **Assertion arg shapes** the enum comments leave open (defined in the `eval/scorer/assertions.py` docstring): every item-level kind takes the selectors `about` (+`cites_any`) · `source_id` · `type` (str or list, prefix match) · `category` · `source_kind`; phrases may be lists of alternatives; `item_present.position_max`, `draft_contains.require_draft`, `no_draft_to.rule\|category`, `priorities_only.or_categories`, `ruling_applied.expect`, `content_overrides_ruling.priority_max`, `injection_not_acted.require_flag`. | B authors manifest assertions with these · redirect | B uses them; the customize suite (`eval/customize_suite.yaml`) already does. |
| 7f | **`tests/test_cli.py` (orchestrator-owned)**: `eval` and `simulate` removed from the stub list, since they are implemented now (their tests are in `tests/test_c_report.py`). | — | Note for the orchestrator. |

## Decided

- **2026-09-28 · deadline:** the repo is submitted the morning of 2026-09-29; the walkthrough is the following week. Cut line recorded in CLAUDE.md ("Deadline") and `docs/handoffs/STATUS.md`. Building continues after submission until the walkthrough.
- **2026-09-28 · dev anchor = 2026-09-24** (Thursday = day 30; day 1 = 2026-08-26; run days Sun 20 – Thu 24 Sept; all PDT, no DST crossing). `world/dev/world.yaml` carries `anchor: 2026-09-24`; `digest generate --anchor` overrides. Held-out anchor is decided separately at M8.
- **2026-09-28 · OpenRouter key limit:** Shubham raises it; not a build concern. Cost is still logged per run.
- **2026-09-28 · commit policy (a):** each track session commits its own paths at milestone ends with a `[A-product]` / `[B-data]` / `[C-grader]` prefix; the orchestrator commits foundation, integration and docs; never `git add -A`; stagger commits if sessions run at the same moment.
- **2026-09-28 · generator = Claude Code session (Fable 5.1), not an API model.** The Data track session writes every email body, note, and background item as prose files with labels under `world/<world>/prose/`; `generator/` code turns them into `.eml` / `.ics` / notes / tasks with real headers, threading, and DST-correct dates, emits the manifest, and runs the validator. Reproducible from world files + committed prose; a changed beat means rewriting its prose file. Zero OpenRouter spend for generation. `models.yaml` records `generator: claude-code-session`.
