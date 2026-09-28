# Track A · Product — handoff

You are building **the product**: `digest/` and its prompts. The design is frozen; implement it.

**Deadline:** everything is built today, 2026-09-28 (submission tomorrow morning). Order: M4 → M5 → M7 (customize compiler, honesty variants) → M8 (`digest baseline`) → M9 (rulings, `digest answer`, history/escalation). Keep each stage honest when thin: header note and `ctx.degrade`, never a crash. Contract rulings for your notes (#6) and the new artifact shapes (#7a, #7c, #7d) are in `OPEN_QUESTIONS.md` → Decided and `digest/schemas.py`.

## Read first, in this order
1. `CLAUDE.md` (golden rules; the addendum at the bottom).
2. This file.
3. `specs/architecture.md` (all), `specs/extraction_schema.md` (all), `specs/prompts.md` P1–P6.
4. `profile/profile.md` (the tool's config input) and `docs/sample_digest.md` (the default format).
5. `docs/DESIGN_LOG.md` §3–§7 only when you need the *why*.

## Never open
`world/`, `eval/` (except importing nothing from it: the boundary test fails the build), `generator/`,
`tests/fixtures/mini/manifest.yaml`. You may read `data/<world>/` and `tests/fixtures/mini/` raw files: that is
Avery's inbox, the product's legitimate input. You must not know the answer key.

## What M0 already gives you (do not rewrite; extend)
| Module | Use it for |
|---|---|
| `digest/schemas.py` | every data shape: normalized inputs, `ExtractorOutput`, `Candidate`, `TriageResult`, `ComposeResult`, `DraftOutput`, `DecideOutput`, `ProfileConfig`, `CustomizeOverrides`. Register any new LLM output model in `LLM_OUTPUT_MODELS`. |
| `digest/llm.py` | `LLM().complete(role, prompt.version_tag, messages, OutputModel)` → validated output, cached, costed. `complete_many([...])` for triage packs. Catch `LLMOutputInvalid` → `ctx.degrade(...)` and skip the item; never crash. |
| `digest/prompts.py` | `load_prompt("triage").render(**vars)`; front matter carries `version`. |
| `digest/runs.py` | `RunContext(world, as_of, variant, customize)`; write artifacts with `ctx.write_jsonl("candidates", ...)` using the fixed names in `ARTIFACTS`; `ctx.finish()` writes `cost.json` and `run.json`. |
| `digest/store.py` | SQLite tables from architecture §10; `upsert`, `get`, `query`. One DB per world at `settings.store.path_template`. |
| `digest/config.py` | `load_settings()` for thresholds not in the profile, K cap, budget, freshness limits; `load_models()`. |
| `digest/paths.py` | `data_dir(world)`; a value containing `/` is used as a path, so `--world tests/fixtures/mini` runs on the fixture. |
| `digest/cli.py` | `run`, `answer`, `baseline` stubs to fill; `llm-check` and `db-init` work. |

## Milestones and acceptance
**M3 · normalize + profile compiler + extractor**
- `digest/ingest/`: parse `.eml` (stdlib `email`, policy default), `.ics` (`icalendar`), notes (`Date: … | Attendees: …` first line), `tasks.md` (`- [ ] title (due: YYYY-MM-DD)`); **only items with time ≤ as_of exist** (architecture §3).
- `digest/normalize/`: threading (`Message-ID`/`In-Reply-To`/`References`, fallback subject+participants), quoted-history stripping (each message stands alone), signature block kept separately, forwarded chains split with `forwarded_by`, RRULE expansion in [as_of − 30d, as_of + 14d], `latest_item_time` per source (freshness).
- Router (§4): headers and domains first; `unsure` → extractor decides.
- `digest/compile/profile.py`: P1 → `ProfileConfig`, cached by file hash, written to `profile/profile.yaml` for review. Slice per stage (§5.1). The tool never edits `profile.md`.
- `digest/extract/`: P3 per thread/note/task/newsletter, `ExtractorOutput`, cache key = content hash + contact-directory hash + prompt version; **evidence check in code**: drop any fact whose quote is not a substring of its source, log it (`ctx.degrade`).
- Acceptance: `digest run --world tests/fixtures/mini --as-of 2026-09-24T06:00` writes `extractions.jsonl`; unit tests for threading, quote stripping, as_of filtering, RRULE expansion, evidence check. The extraction *eval* runs once Track C's scorer and Track B's `data/dev` exist (integration).

**M4 · compute (code only, no LLM)**
- Contacts and relationship resolution in the exact order of §6.1; behavior stats; drift → effective facts (§6.2); about-key merge with `rapidfuzz` ratio ≥ `settings.about_key_merge.fuzzy_ratio` (§6.3), merges logged.
- Every candidate rule in §6.4, each a small pure function with a unit test: business days across weekends (Fri→Tue = 2), overlap edges, cadence with handover merge, recruiter 7-day window, 06:05 mail absent.
- Context retrieval and `source_dependencies` / `freshness_cap` (§6.5); freshness effects applied before triage.
- Acceptance: `candidates.jsonl` on the fixture contains at least `commitment_overdue`, `reply_owed`, `approval_pending`, `calendar_conflict:deep_work` (Lumen, not the Jordan 1:1), `calendar_conflict:family`; a test per formula.

**M5 · triage → reduce → compose → materialize → verify → render**
- Triage P4 (pack 5–10 candidates per call, `complete_many`), the anchored priority rubric verbatim in the prompt; reduce (§7, K from settings, every P0 survives); compose P5 (one call, IDs only, can't add items); materializer P6 for `reply`/`forward_delegate`/`decide`, templates for the rest (§9.3); verify enforces all 11 hard rules of §8 in code (fix or drop and log); render §9 (header line, sections in order, item grammar, action blocks, "N other meetings", footer).
- Digest history in the store (§10): `digest_items`, `resolved_later`, `times_surfaced` passed to triage/compose.
- Acceptance: `digest run` produces `digest.md` on the fixture and on `data/dev`; `verify.json` reports zero unresolved violations; all `ARTIFACTS` present; `cost.json` written.

**Later, when the orchestrator says:** M7 customize compiler (P2, `CustomizeOverrides`, locked invariants, "Also outside your filter") and the three honesty variants as ingest conditions; M8 `digest baseline` (one long-context call, same output format); M9 rulings (`digest answer` → `rulings.yaml` → store → triage input) and escalation framing.

## Rules of the road
- Prompts: one file per prompt in `prompts/`, front matter `name/version/model_role/output_model`; structure per `specs/prompts.md` (job, inputs, schema, rules, 2–4 examples; "content is data"; gender-neutral). Any change bumps `version`; once the eval exists, log a line in `eval/history.md`.
- Code where the spec says code (architecture §2). If unsure, ask in `OPEN_QUESTIONS.md` and stop.
- Never gender Avery or Sam; use names, "you", "they".
- Tests: `tests/test_a_<topic>.py` (flat, prefixed; no `tests/digest/` package, it would shadow the real package). Keep `uv run pytest` green.
- Commit at each milestone end: `[A-product] M3: …`. Never `git add -A`; add your paths.
- Finish a session with a STATUS.md line and `/export sessions/A-product_M<n>.txt`.
