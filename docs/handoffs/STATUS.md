# Status board

Each session appends a dated line when it finishes a milestone or gets blocked. Newest at the bottom of each track.

## Deadline and cut line
**Submission: morning of 2026-09-29. Walkthrough: the following week.** For the submission, in priority order:
A reaches M5 (a digest end to end) · B reaches M2 pass 1 (all storylines and traps rendered; filler reduced) · C reaches M6 (one eval report) · orchestrator: integration, README, DESIGN.md, sessions. Everything else is deferred to the walkthrough week (see CLAUDE.md "Deadline"). The storyline review is on the critical path: Shubham reviews as soon as B posts M1.

## Orchestrator
- 2026-09-28 · M0 done. 43 tests green; `digest llm-check` shows a live Luna call costed ($0.000035) and cached. Handoffs written. Next: integration once A M5 + B M2 + C M6 land.

## A · Product
- 2026-09-28 · M3 done. `digest run --world tests/fixtures/mini --as-of 2026-09-24T06:00` → ingest (as_of filter, variants), normalize (threading, quote/signature split, forwards→`forwarded_by`, RRULE ±30/14d, freshness), router, profile compiler (P1 v2 → `profile/profile.yaml`, cached by hash), extractor (P3 v1, evidence check in code) → `extractions.jsonl` + store; 9 Luna calls ≈ $0.01, 19/19 quotes verified, 0 degradations; exits 3 until M5 (stages compute→render pending). 38 `test_a_*` tests + boundary green. Contract notes in OPEN_QUESTIONS.md #6 (thread/source ids, Avery's address from data, tasks.md mtime vs git, variants in ingest). `tests/test_cli.py` no longer lists `run` as a stub. Next: M4 compute, then M5 (deadline).

## B · Data
- (not started) Next: M1 storyline drafts → Shubham review gate.

## C · Grader
- (not started) Next: M6.

## Blockers / waiting on Shubham
- Judge model pick (OPEN_QUESTIONS.md #1) — after the Fable calibration round (`judge_reference` role). Scorer work is unblocked.
- Held-out anchor (#2) — decide at M8; suggestion 2026-03-26. Dev anchor is decided: 2026-09-24.
