# v2 · Track C · status

**2026-09-29 · C1–C5 done on branch `v2-c-eval`; stopped.** 360 tests green (Track C 159 → 181). Interpretation
choices made unattended are in `OPEN_QUESTIONS.md` #21 (a–f); please confirm or redirect.

## Landed

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

## Measured

| Run | P0 | Traps | Must-not | One thing | Notes |
|---|---|---|---|---|---|
| v1 dev runs, rescored (5 days) | 100% | 118/175 | 6.6% | 100% | as reported 115/175: +3 are items v1 rendered under other keys (#21a) and the approval count (#21d) |
| v1 held-out runs, rescored | 84.6% | 137/207 | 6.6% | 50% | as reported 129/207 |
| v2 dev Thursday, readers only (A's P2 run, day 30 only) | 87.5% | 56/124 (52 not run: other days) | 6.0% | 0% | reader recall 92% (24/26), priority in band 86%, action type 40%, must-not precision 88% (15 of 123 must-not threads said yes), trap recall 5/11 (no sweeps/nets yet), 3 duplicated items (no merge yet). Report in the session scratchpad, not committed (partial run) |

## For the orchestrator

- Run `digest eval --world dev` (and `heldout`) once B's sweeps/nets and A5 are merged and the five mornings are run;
  the report then carries the full comparison table, diagnostics and rescue list. Judge: `--judge-export`, judge
  in-session, `--judge-scores`.
- The base fake run keeps its committed v1 `extractions.jsonl`: `test_a_stages.py` / `test_a_compute.py` read it.
  Delete it once no test does.
- `OPEN_QUESTIONS.md` #18 (claimed-key guard) is still open and untouched; with readers' light tags it bites less.
- `/export sessions/C-grader_v2.txt` from this session (Shubham), grep it for `github_pat_|sk-or-|OPENROUTER_API_KEY=`.
