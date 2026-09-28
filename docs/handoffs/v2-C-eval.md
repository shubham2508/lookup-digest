# v2 · Track C · Eval — handoff

You rewire the **eval** for v2: digest-level metrics stay the target; stage metrics become diagnostics. Start with one
line: **"Track C, v2"**.

Work in the worktree `/Users/shubham/Desktop/work/lookup-digest-v2-c-eval` (branch `v2-c-eval`; `.env` is there).
Never edit the main checkout.

## Read first, in this order
1. `CLAUDE.md` golden rules 2, 8, 10.
2. `specs/PIVOT_SPEC.md` §4, §6, §8 and `MIGRATION_PLAN.md` §1 (eval table), §2.
3. `digest/findings.py` (`finding_row` is the `findings.jsonl` line), the `Finding` block in `digest/schemas.py`.
4. `eval/scorer/artifacts.py` (`RunView`), `extraction.py`, `compute.py`, `triage.py`, `attribution.py`,
   `assertions.py`, `report.py`; `eval/manifest_schema.py`; `tests/test_c_*.py`, `tests/fixtures/mini_runs/`.
5. `eval/reports/dev_2026-09-29.md` and `heldout_2026-09-29.md`: the v1 numbers (tag `v1-extraction-centric`).

## You own
`eval/` except `eval/manifests/` (never edit the answer key), `tests/test_c_*.py`, `tests/fixtures/mini_runs/`
(add `findings.jsonl` to the fake runs). Do not touch `digest/`, `world/`, `generator/`, `prompts/`.

## Artifact contract (what a v2 run writes)
Unchanged shapes: `candidates.jsonl` (`type` is now any string: a v1 rule name for safety nets, a reader's free-text
`kind` otherwise), `triage.jsonl`, `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`, `digest.md`,
`contacts.json`, `links.jsonl`, `run.json`, `cost.json`, `degradations.jsonl`, `trace.jsonl`.
New: `findings.jsonl`, one line per Finding (all origins, including `needs_avery: "no"` ones) = `Finding` fields +
`candidate_id` (null when no candidate was made), `thread_id`, `rescued_by_safety_net`.
Gone: `extractions.jsonl`. Stage names for attribution: `read` → `sweep` → `net` → `merge` → `compose` →
`materialize` → `verify` (a miss is attributed to the first stage that lost it, as before).

## Deliverables

**C1 · reader diagnostics** (replace `scorer/extraction.py`): per labeled thread in the manifest (`kind: thread`),
the expected `needs_avery` is implied by the label: `ball_awaiting == avery`, or an ask `to_avery: true, status:
open`, or a commitment `owner: avery, status_in_thread: open` → yes; else no. Report per run day: reader recall on
planted threads (`needs_avery` right; priority within the expected item's band when that thread backs an expected
item; an expected action type present), precision on `must_not_surface` threads (no `needs_avery: yes`), and the
list of misses with `findings.jsonl#L` links. Newsletter/automated/marketing labels: only "no finding said yes".

**C2 · sweep and net diagnostics** (replace `scorer/compute.py`): planted calendar and notes traps (the manifest's
per-day `candidates:` of types `calendar_conflict:*`, `declined_meeting`, `task_due`, `obligation_cadence`,
`profile_drift`, `contradiction`) found by any finding (match on `about`, `cites_any`, or the safety-net `kind`);
**rescue list**: findings with `rescued_by_safety_net: true`, by kind, with what they rescued; merge errors
(one expected item rendered twice, or two expected items merged into one).

**C3 · assertions** (`scorer/assertions.py`): `candidate_present`, `candidate_absent`, `count_items_of_type`,
`no_candidates_of_type` now match a finding/candidate whose `type` equals the v1 type name **or** whose `about`
matches (existing fuzzy about match) with `cites_any`; everything item-level is unchanged. `triage.py` keeps the
hard-rule checks on `triage.jsonl`. `attribution.py` uses the new stage names.

**C4 · report**: §1 gains a **v1 / v2 / baseline** table for dev and held-out (P0 recall, traps passed, must-not
rate, one-thing accuracy, judge scores, cost per run). v1 numbers are fixed, from the two 2026-09-29 reports:
dev 100% · 115/175 · 6.6% · 100% · $0.054 (cached) ; held-out 84.6% · 129/207 · 6.6% · 50% · $0.19 (cold extraction)
; baseline dev 75% · 34/74 · 1.2% · 0% ; baseline held-out 62.5% · 44/83 · 2.8% · 0%. Put them in
`eval/v1_results.yaml` so the table does not depend on those files. §2 becomes "Diagnostics".

**C5 · judge**: `digest eval --judge` runs on `deepseek/deepseek-v4.1-flash` (already configured); make sure the
condition and simulation scoring still read the unchanged artifacts.

**Acceptance:** `uv run digest eval --world tests/fixtures/mini --runs tests/fixtures/mini_runs` works on fake runs
that include `findings.jsonl` (extend `make_fake_run.py`); `uv run pytest -q` green in your worktree; then, when the
orchestrator has a real v2 dev run, `uv run digest eval --world dev` writes a report with §1 comparison table,
reader/sweep diagnostics and the rescue list. Write `docs/handoffs/v2-C-STATUS.md` and stop.

## Commits
`[v2-C] C1: reader diagnostics …`, your paths only. The orchestrator merges `v2-c-eval` into `main`.

## Unattended mode (Shubham is asleep)
Do not stop to ask. When something is ambiguous: write it to `OPEN_QUESTIONS.md` (what, options, what you picked),
take the default from `MIGRATION_PLAN.md` §5 or the most conservative option, and continue. When a permission or
tool prompt would block you, prefer the path that does not need it. Finish every deliverable you can, write your
STATUS file, and stop only then. The orchestrator reviews everything at the merge.
