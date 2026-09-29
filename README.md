# Daily Digest

A one-page 6:00am PT triage digest for "Avery Chen", built from a synthetic month of email, calendar, notes and tasks. LLM readers judge the raw threads; code does the math, the hard rules and a recall floor; the page is scored against a human-reviewed answer key. Design and results: `DESIGN.md`. What it does and how each part is tested: `docs/CAPABILITIES.md`. The spec: `specs/PIVOT_SPEC.md`, `CLAUDE.md`.

## Install

```
uv sync --all-groups          # installs Python 3.12 and every dependency into .venv
cp .env.example .env          # paste an OPENROUTER_API_KEY with a few dollars of credit
uv run pytest                 # ~400 tests, no network
```

Everything else is in the repo: both worlds' data (`data/dev`, `data/heldout`), the answer keys, the profile, the prompts, the config, finished example runs under `runs/examples/` (digests, every artifact, one full LLM trace) and the final reports under `eval/reports/`. Without a key you can read those; with one, a morning takes about 8 minutes and $0.30 cold (readers are cached per thread and date; a rerun is a cent) and the full eval matrix about $2 per world. Models are in `config/models.yaml`: the pipeline on `openai/gpt-6-luna`, TypeSafe's Jev for "same thing?" decisions (the LLM if unavailable), `deepseek/deepseek-v4.1-flash` as judge.

## Run

```
uv run digest run --world dev --as-of 2026-09-24T06:00                    # Thursday, the dense morning
uv run digest run --world dev --as-of 2026-09-24T06:00 --customize profile/customize/weekend.md
uv run digest run --world dev --as-of 2026-09-24T06:00 --variant stale_inbox   # or no_notes | corrupt_ics
uv run digest baseline --world dev --as-of 2026-09-24T06:00               # naive one-call digest, for comparison
uv run digest ui                                                          # http://127.0.0.1:8765
```

A run writes `runs/dev/<as_of>/digest.md` and every stage's artifact: `contacts.json`, `findings.jsonl`, `links.jsonl`, `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`, `cost.json`, `trace.jsonl` (every LLM call with its prompt and answer). Dev run days are Sun 2026-09-20 to Thu 2026-09-24. `--customize` takes any sentence (nine examples in `profile/customize/`); the UI runs a morning and shows the digest, why each item is there, and every LLM call by phase.

## Memory

```
uv run digest run --world dev --as-of 2026-09-21T06:00      # Monday: a question card Q1
uv run digest answer Q1 2 --world dev                        # answer it → runs/dev/rulings.yaml
uv run digest run --world dev --as-of 2026-09-22T06:00      # Tuesday: "applied 1 learned rule"; the card is gone
uv run digest simulate --world dev --days 5 --fresh          # the whole loop with a simulated Avery (~$1)
```

## Evaluate

```
uv run digest eval --world dev --customize-suite --baseline   # score the runs on disk → eval/reports/dev_<date>.md
uv run digest eval --matrix --world dev --keep-going          # every run (5 mornings, variants, customize, baseline, simulate), then the report
uv run digest eval --world dev --judge-export items.jsonl     # judge items for in-session grading; --judge-scores f reads them back; --judge runs the API judge
```

The report: §1 v1 / v2 / baseline on dev and held-out (P0 recall is the only gate; trap assertions, noise, the one thing, judge, cost), §2 diagnostics per morning with every miss attributed to the stage that lost it, then variants, customize and the simulation checks. Credit is decided by exact keys and cited sources, the product's decider for the ambiguous cases; every decision is listed. `eval/history.md` logs prompt changes; v1 is tag `v1-extraction-centric`.

## Data

```
uv run digest generate --world dev --anchor 2026-09-24      # world/dev/ (storylines, prose) → data/dev/ + the answer key
```

Refuses unreviewed storylines; validates planted phrases, threading, time zones and pronoun rules. Held-out: `--world heldout --anchor 2026-03-26`.

## Layout

`digest/` the product (never reads `world/` or `eval/`; a test enforces it) · `prompts/` one versioned file per LLM prompt · `config/` models and thresholds · `profile/` Avery's profile and the customize examples · `world/`, `generator/` the synthetic world and its renderer · `data/` the rendered inbox, calendars, notes, tasks · `eval/` answer keys, scorer, judge, reports · `runs/examples/` committed runs · `sessions/` Claude Code transcripts · `docs/` the assignment, `DESIGN_LOG.md`, `CAPABILITIES.md`, handoffs.
