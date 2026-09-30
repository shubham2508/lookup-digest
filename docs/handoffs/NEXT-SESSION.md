# Orchestrator handoff — start here (written 2026-09-29 morning, after the v2 build)

Read `CLAUDE.md`, `specs/PIVOT_SPEC.md`, `MIGRATION_PLAN.md`, then this page. `STATUS.md` has the build's timeline and the
three v2 track reports; `v2-A-checkpoint.md` is the evidence behind the P2 gate (`OPEN_QUESTIONS.md` #19). Shubham wants short, plain answers,
tables over paragraphs, a status line between long steps, and no fixable issue shipped as "week two".

## Where things stand

- **2026-09-30, after submission: keyword decisions removed, routing by Jev** (`OPEN_QUESTIONS.md` #26, #27). Headers
  settle what they prove, then Jev picks person / system ask / system FYI / list mail (unsure → read); regex nets gone;
  reader context by the rarest shared person plus every note and the task list; a reader's finding must cite its own
  thread. Dev Thursday 124/175, P0 8/8, one thing right (submitted code rerun cold: 120/175); held-out Thursday, run once,
  P0 8/8, one thing right, 153/207 traps over five mornings (was 151). `runs/examples/*/Thursday` are from this code. The trial key ran out that day; `.env` now holds Shubham's own key. Run one pipeline at a
  time: OpenRouter reserves credit per request in flight.
- **2026-09-29 evening: final code review fixed** (`OPEN_QUESTIONS.md` #25), verified by a Thursday rerun per world
  (`eval/reports/review_fixes_2026-09-29.md`: held-out day 30 now 8/8 P0, five mornings 92.3%; dev unchanged).
- **v2 ("read, don't extract") is built, integrated and measured.** Three parallel sessions (A readers, B spine/sweeps/
  nets, C eval) built on the `Finding` contract; the orchestrator merged them, fixed integration (A5, reduce, merge,
  compose v6), ran both final matrices, judged in-session, and filled `DESIGN.md`, `README.md`, `eval/history.md`.
- **v1 is tag `v1-extraction-centric`**; its reports are `eval/reports/*_2026-09-29_v1.md`. Rejected design, kept for the
  comparison.
- **Final numbers (both worlds, five mornings):** dev P0 100%, traps 127/175, noise 5.5%, one thing 2/2, memory 11/11,
  $0.18 a cold morning; held-out P0 84.6%, traps 149/207, noise 6.1%, one thing 2/2, memory 14/15, $0.29. Judge
  (in-session, `eval/judge/in_session/*.yaml`, read back with `--judge-scores`): dev digest 4.4/3.4/4.4, drafts
  4.7/4.3/3.5; held-out digest 4.4/3.2/4.4, drafts 4.2/4.5/3.2. Reports: `eval/reports/{dev,heldout}_2026-09-29.md`.
- Decisions taken while Shubham slept are in `OPEN_QUESTIONS.md` → Decided (#19 verdict, #20, #21, #22 accepted, #23).
  #18 is closed by **#23**: the grader matches by exact key, unique sources and the product's decider; no string
  similarity remains anywhere in the repo.

## To do next (Shubham, then the orchestrator)

1. Shubham: `/export sessions/orchestrator_v2.txt` from the orchestrator session, plus `sessions/A-readers_v2.txt` and
   `sessions/C-grader_v2.txt` from the track sessions (`sessions/B-spine_v2.txt` is in). Scrub:
   `grep -nE 'github_pat_|sk-or-v1-[A-Za-z0-9]{20,}|OPENROUTER_API_KEY=' sessions/*`.
2. Push `main`. The three worktrees (`../lookup-digest-v2-{a-readers,b-spine,c-eval}`) are merged; once their sessions
   are closed: `git worktree remove <path>` and `git branch -d v2-a-readers v2-b-spine v2-c-eval`.
3. Optional, cents: the API judge for comparison with the in-session scores:
   `uv run digest eval --world dev --customize-suite --baseline --judge` (DeepSeek V4.1 Flash, configured).
4. Fix-first candidates, in order of value (each is a known issue in `DESIGN.md`): `profile_update` actions from the
   notes sweep; decide-card drafts marked as presupposing the choice; the "Message them" render fallback; the P0 floor
   during the raise (11 vs 8 on dev Thursday). Held-out is never tuned on: re-measure dev, then report held-out once.

## Tools

- `uv run digest run --world dev --as-of 2026-09-24T06:00` (~$0.15 cold, a cent warm); `uv run digest eval --world dev`;
  `uv run digest eval --matrix --world dev --keep-going` (~$2, ~2 h); `python -m digest.compute.sweeps --world dev --as-of …`.
- `uv run digest ui` for any run; `.claude/skills/debug-trap/SKILL.md` for a failing assertion (stages are now
  spine → read → sweep → net → merge → compose → materialize → verify).
- Never run two pipelines in one checkout (store lock). Never edit `digest/`, `prompts/`, `config/`, `eval/` while a
  matrix runs.

## Budget

OpenRouter key: limit $25, about $8.5 left after the final matrices ($4.7 for both worlds).

## How a track session works (if the build is ever split again)

One session per track in its own git worktree, started with one line ("Track A, v2"); it reads `CLAUDE.md`, then a
handoff doc (ownership, read list, no-touch list, deliverables, acceptance), then its read list. Questions go in
`OPEN_QUESTIONS.md`; progress in `STATUS.md`; the session ends by writing its report and stopping; the orchestrator
merges. The v2 handoffs are in the transcripts (`sessions/*_v2.txt`) and summarized in `MIGRATION_PLAN.md` §1.
