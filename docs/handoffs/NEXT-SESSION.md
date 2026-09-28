# Orchestrator handoff — start here (written 2026-09-28, late)

Read `CLAUDE.md` first, then this page, then `docs/handoffs/STATUS.md` and `OPEN_QUESTIONS.md` → Decided (#13–#17).
Shubham wants short, plain answers, tables over paragraphs, and a status line between long steps.

## Where things stand

- **Build:** all milestones M0–M10 exist. Tracks A, B, C are done and closed; this orchestrator owns everything now.
- **Submission:** the repo is due the morning of 2026-09-29; walkthrough the following week.
- **Last commit:** `196e557` — known issues fixed in code (thread-level merge in reduce, earned P0, exact-scope rulings,
  linker for role-at-org, P0 one-thing guard) and **Jev** behind the linker. All tests green.
- **No final numbers yet on this code.** The stale dev report was deleted (a7ae466+); the final matrix writes the
  reports to quote. Earlier numbers (before commit 5038594, the prompt-leak fix) are not results.

## What to do next, in order

1. **Live Jev check — done once (it did finish):** Thursday dev gave P0 19 → 12 (key: 8), 12 items on the page, 348 of 448 link decisions by Jev, $0.22 for the run. Jev failed on two question types with `max_tokens_exceeded` (news and topics: too many long options per request); `jev.py` now splits requests by size (commit after 8f6ec60). Rerun Thursday once to confirm no fallback, and look at why compose picked Jordan's Veritas incident as the one thing (the key expects the cap table on day 30; both are P0 due today — check the compose trace before changing anything).
   Previous note, kept for reference: The first attempt was cut off by a 15-minute tool timeout during
   triage (it got through extraction and linking: Jev 21 calls, $0.02). Run it detached so no timeout kills it:
   `rm -rf runs/dev && mkdir -p runs/dev && nohup uv run digest run --world dev --as-of 2026-09-24T06:00 > runs/dev/thu.log 2>&1 &`
   then wait for `runs/dev/2026-09-24T06-00/run.json`. When it finishes:
   - `links.jsonl`: decisions marked `"by": "jev"` with `p=` probabilities; spot-check a few for sense.
   - Two question types fell back to the LLM (`linker@v2`, `topic_grouper@v2` calls in `cost.jsonl`). Find why in
     `degradations.jsonl` (`jev_failed_fallback_llm`) or the trace; likely a request-size or option-count limit
     (Jev: 255 options per question, ~32k tokens per request). Fix in `digest/compute/jev.py` (chunking) if simple.
   - `digest.md`: P0 count should now be near the answer key's 8 on Thursday; page ≤ 12 items; one thing = cap table.
2. **Final runs** (nothing else may run at the same time; do not edit `digest/`, `prompts/`, `config/`, `eval/`
   while they run):
   ```
   rm -rf runs/dev runs/heldout runs/_archive && mkdir -p runs/dev runs/heldout   # _archive = superseded local runs
   nohup sh -c 'uv run digest eval --matrix --world dev --keep-going > runs/dev/matrix.log 2>&1; uv run digest eval --matrix --world heldout --keep-going > runs/heldout/matrix.log 2>&1' >/dev/null 2>&1 &
   ```
   ~1.5 h. Cost ~$1–1.5 per world (extractor v2 is cached for dev days already run; held-out reads cold).
   OpenRouter key: limit $10, ~$4 left at 17:30 UTC — check with the `/auth/key` call before starting.
   If a step times out (provider stall), rerun that morning and the later ones in order, then `digest eval`.
3. **Fill the results**: `DESIGN.md` "Results" sentence (dev + held-out: P0 recall, traps, must-not, one thing,
   cost/run, memory checks; baseline side by side). Replace `HELDOUT_RESULTS`. Add an `eval/history.md` line for
   triage v5 / linker+Jev with before→after.
4. **Refresh `runs/examples/dev/`** from the final runs (digest, run.json, cost.json, compose/reduce/triage/candidates,
   actions, verify, links; trace only for the Thursday default run), and add one held-out example.
5. **Known-issues list in DESIGN.md**: only what the final report still shows. Shubham does not want shipped issues
   described as "week two" when they are fixable; fix first, list only what truly remains.
6. Commit. Tell Shubham to export this session (`/export sessions/orchestrator_final.txt`), scrub it
   (`grep -nE 'github_pat_|sk-or-v1-[A-Za-z0-9]{20,}'`), and push.

## Things decided tonight (details in OPEN_QUESTIONS.md → Decided)

| # | Decision |
|---|---|
| 15 | Simulation runs write to `<as_of>_sim/` (`--tag sim`); plain runs stay rulings-free |
| 16 | **Linker**: an LLM (and now Jev first) decides "same thing?"; code only narrows options by hard facts. No string similarity anywhere in `digest/` |
| 17 | **Prompt-example leak removed**: examples use a made-up cast (Dara Quinn/Brightwater, Oren Tal/Halden Mills, Nia Okoro, Jun Park, Pellucid Freight). Never reuse world names in prompts; the `debug-trap` skill has the grep |
| — | Honesty in code: sync-gap qualifier, confidence cap, calendar "unreadable" (B's reading over C's stricter suite, noted) |
| — | One page: ≤ 12 items; P0 never cut to also-pending; also-pending shows 8 lines + a count |
| — | P0 must be earned: profile P0 contact (tier), escalation/incident, or family calendar conflict |

## Tools that exist

- `uv run digest ui` (or F5 "Digest" in VS Code): run a morning, then tabs Digest / Why each item / LLM calls; buttons
  for Score runs, Full matrix, Simulate. It refuses to launch while another pipeline runs.
- `.claude/skills/debug-trap/SKILL.md`: the procedure for any failing assertion or missing item.
- Explainer pages (claude.ai artifacts, private): Digest Engine Walkthrough, Digest Agents and Prompts. Their numbers
  are stale; republish from this repo's final numbers if Shubham asks.

## Watch-outs

- Never run two pipelines at once (they deadlock on the store/cache). Edit code only when nothing runs, or in a git
  worktree.
- OpenRouter sometimes stalls a call for minutes; timeouts are 90 s per request and 30 min per matrix step.
- Held-out: never tune on it. Report it once, on the final code.
