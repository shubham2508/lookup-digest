# Daily Digest

A one-page 6:00am PT triage digest for "Avery Chen", built from a synthetic month of email, calendar, notes and tasks. A fixed pipeline: code for rules and date math, small structured LLM calls for judgment, scored against a human-reviewed answer key. Design and results in `DESIGN.md`; the frozen spec in `CLAUDE.md` and `specs/`.

## Install

```
uv sync --all-groups          # Python 3.12, dependencies, editable install
cp .env.example .env          # paste OPENROUTER_API_KEY
uv run pytest                 # ~330 tests
uv run digest llm-check       # one live structured call through OpenRouter, cached and costed
```

Models are in `config/models.yaml`: the pipeline runs on `openai/gpt-6-luna` with reasoning effort per stage. The synthetic world's prose was written by a Claude session, not an API call. The judge is a third model family and is set only after a calibration round.

## Run it against the dataset

```
uv run digest run --world dev --as-of 2026-09-24T06:00
```

Writes `runs/dev/2026-09-24T06-00/digest.md` plus every stage's artifacts (`extractions.jsonl`, `contacts.json`, `candidates.jsonl`, `triage.jsonl`, `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`), `suggested_tasks.md`, `cost.json` and `run.json`. The dev world's run days are Sun 2026-09-20 to Thu 2026-09-24; day 30 (Thursday) is the dense one. A cold run costs about a cent; reruns hit the LLM cache.

Options:

```
--customize profile/customize/board_prep.md     # writes to …_customize-board_prep/
--variant stale_inbox|no_notes|corrupt_ics      # honesty variants, run conditions on the same data
uv run digest baseline --world dev --as-of …    # naive one-call baseline → …_baseline/digest.md
uv run digest answer Q1 2 --world dev           # answer a question card → runs/dev/rulings.yaml
uv run digest run --world tests/fixtures/mini … # a tiny hand-made world for development
```

## Evaluate

```
uv run digest eval --world dev --customize-suite --baseline
uv run digest simulate --world dev --days 5 --fresh    # multi-day loop, simulated Avery answers the cards
uv run digest eval --matrix --world dev                 # everything above in one command, then the report
```

Scores every run against `eval/manifests/dev.yaml` and writes `eval/reports/dev_<date>.md`: P0 recall (the only gate), trap assertions, must-not rate, one-thing accuracy, per-stage metrics, honesty variants, the customize suite, the baseline, the simulation checks, and every miss attributed to the stage that lost it. `eval/history.md` logs prompt changes with before and after numbers.

## Debug UI

```
uv run digest ui                                        # http://127.0.0.1:8765
```

A local page over `runs/`, and the only launch config in `.vscode/launch.json` ("Digest"). Pick a world and a morning and run it, or score the world, run the full matrix, simulate five days, or regenerate the data from buttons; then read the digest, every stage's table (candidates → triage → reduce → compose → actions → verify), the trace of every LLM call with its full prompt and output, degradations, cost, and the eval reports. Each run writes `trace.jsonl` next to its other artifacts, so a run is fully reconstructible after the fact. One pipeline at a time: the page refuses a second launch while one is running.

## Regenerate the data

```
uv run digest generate --world dev --anchor 2026-09-24
```

Renders `world/dev/` (people, storylines, prose) into `data/dev/` and the answer key in about two seconds. It refuses to run on a storyline that has not been reviewed (`reviewed: true`), and its validator checks every planted phrase is verbatim, threading resolves, offsets are correct Pacific time, and no prose gendered Avery or Sam. The held-out world uses `--world heldout --anchor 2026-03-26`.

## Layout

| Path | What |
|---|---|
| `digest/` | the product; never reads `world/` or `eval/` (a test enforces it) |
| `prompts/` | one versioned file per LLM prompt |
| `config/` | `models.yaml` (model per role, reasoning effort) and `settings.yaml` (thresholds not in the profile) |
| `profile/profile.md` | Avery's profile, verbatim from the assignment; `profile.yaml` is compiled from it |
| `world/`, `generator/` | the synthetic world's script and prose, and the code that renders it |
| `data/<world>/` | the rendered inbox, calendars, notes, tasks: the only data the digest reads |
| `eval/` | manifests (answer keys), scorer, judge, sim_avery, reports, `history.md` |
| `runs/` | per-run artifacts and cost |
| `sessions/` | exported Claude Code transcripts, one per track and milestone |
| `docs/` | the assignment, the design log, the track handoffs and status board |
