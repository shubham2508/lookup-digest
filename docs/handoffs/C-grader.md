# Track C · Grader — handoff

You are **the eval harness**: mostly code that scores run artifacts against the answer key, plus one LLM judge
for the fuzzy qualities, a simulated Avery for the multi-day loop, and the report. You do not build the product
and you do not write the world.

## Read first, in this order
1. `CLAUDE.md` (golden rules; the addendum).
2. This file.
3. `specs/eval.md` (all). Then `eval/manifest_schema.py` (what you score against) and `digest/runs.py` (`ARTIFACTS`: what you score) with `digest/schemas.py` (their shapes).
4. `specs/prompts.md` E1 and E2; `specs/architecture.md` §8–§10 (hard rules, render grammar, artifacts).
5. `docs/DESIGN_LOG.md` §10 for the *why*.

## Never open
`digest/` stage code (`ingest/ … render/`, `compile/`), `generator/`, `world/`. You read `runs/…` artifacts and
`eval/manifests/…`, and you import only the contracts: `digest.schemas`, `digest.runs`, `digest.llm`, `digest.config`.
Build the scorer from the spec, not from the pipeline's quirks.

## Milestone M6 · scorer, assertions, P0 gate, judge, sim_avery, report
1. **Loaders**: `eval.manifest_schema.load_manifest`; run artifacts from `runs/<world>/<as_of>[_<variant>]/` via `RunContext(...).read_jsonl/read_json` or plain files; `digest.md` parser (sections, items, citations `[email: …]`, action blocks, header line) — it follows architecture §9.
2. **Metrics per stage (eval.md §2)**, each a function returning numbers + the per-item misses:
   - extraction: type / domain / intent / ball accuracy; commitments and asks precision/recall matched on about key (fuzzy ≥ 0.85, like compute) + owner; due dates within granularity; recall on planted schedule mentions / role changes / claims / stage signals; evidence validity rate; injection recall.
   - contacts/compute: category, subtype, stage accuracy per run day; about-key merge accuracy on `should_merge` / `should_not_merge`; candidate recall and precision vs `run_days[].candidates`.
   - triage: include P/R; priority confusion matrix; section accuracy; sender-vs-content cells; action-type confusion matrix; question-card ambiguity type + default present.
   - compose/digest: **P0 recall (the gate)**, one-thing accuracy, must-not rate (`noise_source_ids` that appeared / total), section placement, compose-vs-reduce disagreement flags, length/header/citations from `verify.json`.
   - materializer code checks: ≤3 sentences, banned phrases, no drafts to `never_draft` contacts or recruiters, assumptions present when the brief listed any, numbers match effective facts.
3. **Assertion checkers**: one per `AssertionKind` in `eval/manifest_schema.py` (all 32), each returning `{id, passed, evidence, attributed_stage, artifact_links}`. Kinds are documented next to the enum; if an arg shape is unclear, define it in the docstring and note it in STATUS.md.
4. **Stage attribution**: every missed expectation is attributed to the first stage that lost it (extraction → compute → triage → compose → materializer) using the artifacts, with a link to the artifact line.
5. **Judge (E1)**: `prompts/judge.md` (front matter `model_role: judge`); two rubrics, fixed for every item: drafts (factual consistency with evidence, tone for recipient category, assumptions flagged; 1–5 each with a one-line reason) and digest (answers the three questions, no noise, honest about gaps; 1–5 each). Call `digest.llm.LLM().complete("judge", …)`; until Shubham picks the model, `LLMRoleUnconfigured` is caught and the report says "judge: skipped (no model configured)". **Calibration** (one-time, in DESIGN.md): on ~20 items from the first dev run, you score them yourself with the same rubric and compare; agreement within 1 point on ≥ 80% keeps the cheap judge.
6. **sim_avery (E2)**: code first: parse question cards from `digest.md` / `compose.json`, match scope to `manifest.sim_avery` by about key or contact, emit `digest answer Q<n> <option>`; fall back to the `sim_avery` LLM role only when no match. Drives `digest simulate --days 5` (eval.md §7 assertions).
7. **Report** `eval/reports/<world>_<date>.md` in the §9 layout: summary table (pipeline vs baseline, dev vs held-out: P0 recall, trap assertions passed, must-not rate, one-thing accuracy, cost/run from `cost.json`), per-stage metrics, failed assertions with stage + artifact links, customize and variant results, label-audit note. Plus `eval/history.py` with `append(date, prompt, version, before, after)` for `eval/history.md`.
8. **Expected profile.yaml** (prompts.md P1 eval): hand-write `eval/expected/profile.yaml` from `profile/profile.md` for the field-level diff; Shubham reviews it.
9. **Customize suite inputs** (eval.md §6): the six `profile/customize/*.md` files and their assertions.
10. `eval/cli.py`: `evaluate(world, variant, customize_suite, baseline)` and `simulate(world, days)` implemented.
Acceptance: `digest eval --world tests/fixtures/mini`-style run on your own fake artifacts under `tests/fixtures/mini_runs/` (you write them, shaped by `digest/schemas.py`) passes unit tests for every metric and checker; then the real `digest eval --world dev` writes a report at integration.

**Later:** honesty-variant assertions (§5), customize assertions (§6), simulation assertions (§7), baseline scoring (§8), held-out column.

## Rules of the road
- Labels per item, one generic rubric per stage type, specific assertions per trap. No bespoke rubric per case.
- The judge is reported, not gated. P0 recall is the only gate.
- Questions → `OPEN_QUESTIONS.md`, then stop. Tests: `tests/test_c_<topic>.py`. Commit `[C-grader] M6: …`, your paths only.
- Finish a session with a STATUS.md line and `/export sessions/C-grader_M<n>.txt`.
