# Daily Digest

A one-page 6:00am PT triage digest for "Avery Chen", built from a synthetic month of email, calendar, notes and tasks. LLM readers judge the raw threads; code does the math, the hard rules and a recall floor; the page is scored against a human-reviewed answer key.

**Results** (five mornings per world; P0 recall is the gate): P0 recall 100% on dev and 92.3% on held-out (a second world, run once, never tuned on); the one thing right on every morning that has one; noise 5.5% / 6.1%. The one-call baseline gets 50% / 0% P0. About $0.40 a cold morning. After submission, keyword routing was replaced by header facts plus Jev (`OPEN_QUESTIONS.md` #26, #27), verified on dev Thursday only (124/175 traps, P0 8/8).

## For reviewers

| To see | Open |
|---|---|
| The design, results and what was rejected, on one page | `DESIGN.md` |
| What a morning looks like | `runs/examples/dev/2026-09-24T06-00/digest.md` (every artifact and LLM call beside it) |
| Scores, and every miss traced to the stage that lost it | `eval/reports/dev_2026-09-29.md`, `heldout_2026-09-29.md`, `review_fixes_2026-09-29.md` |
| What it does and how each capability is tested | `docs/CAPABILITIES.md` |
| Why each decision was made, and what was rejected | `docs/DESIGN_LOG.md`, `OPEN_QUESTIONS.md` → Decided |
| How Claude Code was used | `sessions/` (every session's transcript), `CLAUDE.md` (the agents' standing rules), `docs/handoffs/` |
| The spec | `specs/PIVOT_SPEC.md` |

## Install

Needs [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 itself).

```
uv sync --all-groups          # every dependency into .venv
cp .env.example .env          # paste an OPENROUTER_API_KEY with a few dollars of credit
uv run pytest                 # ~400 tests, no network, no key
```

Everything else is in the repo: both worlds' data (`data/dev`, `data/heldout`), the answer keys, the profile, the prompts, the config, finished example runs under `runs/examples/` (digests, every artifact, one full LLM trace) and the final reports under `eval/reports/`. Without a key you can read those; with one, a morning takes about 8 minutes and $0.40 cold (readers are cached per thread and date; a rerun is a cent) and the full eval matrix about $2 per world. Models are in `config/models.yaml`: the pipeline on `openai/gpt-6-luna`, TypeSafe's Jev for "same thing?" decisions (the LLM if unavailable), `deepseek/deepseek-v4.1-flash` as judge.

## Run

```
uv run digest run --world dev --as-of 2026-09-24T06:00                    # Thursday, the dense morning
uv run digest run --world dev --as-of 2026-09-24T06:00 --customize profile/customize/weekend.md
uv run digest run --world dev --as-of 2026-09-24T06:00 --variant stale_inbox   # or no_notes | corrupt_ics
uv run digest baseline --world dev --as-of 2026-09-24T06:00               # naive one-call digest, for comparison
uv run digest ui                                                          # http://127.0.0.1:8765
```

A run writes `runs/dev/<as_of>/digest.md` and every stage's artifact: `contacts.json`, `findings.jsonl`, `links.jsonl`, `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`, `cost.json`, `trace.jsonl` (every LLM call with its prompt and answer). Run days: dev Sun 2026-09-20 to Thu 2026-09-24, held-out Sun 2026-03-22 to Thu 2026-03-26 (`--world heldout`). Without a key, `run` stops and says so. `--customize` takes any sentence (nine examples in `profile/customize/`); the UI runs a morning and shows the digest, why each item is there, and every LLM call by phase.

## Memory

```
uv run digest run --world dev --as-of 2026-09-21T06:00      # Monday: a question card Q1
uv run digest answer Q1 2 --world dev                        # answer it → runs/dev/rulings.yaml
uv run digest run --world dev --as-of 2026-09-22T06:00      # Tuesday: "applied 1 learned rule"; the card is gone
uv run digest simulate --world dev --days 5 --fresh          # the whole loop with a simulated Avery (~$1)
```

Answers are kept in `runs/<world>/rulings.yaml` and apply to every later run of that world; `--fresh` and the eval matrix set it and the history store aside first (renamed, never deleted).

## Evaluate

```
uv run digest eval --matrix --world dev --keep-going          # every run (5 mornings, variants, customize, baseline, simulate), then the report
uv run digest eval --world dev --customize-suite --baseline   # rescore the runs on disk → eval/reports/dev_<date>.md
uv run digest eval --world dev --judge                        # + the API judge (cents); --judge-export f / --judge-scores f for in-session grading
```

A fresh clone has no runs to score: start with the matrix (cold, about $2 and 1.5–2 h per world; dev and held-out can run at the same time, each has its own store). The submitted reports are `eval/reports/{dev,heldout}_2026-09-29.md`, with the in-session judge scores in `eval/judge/in_session/`.

The report: §1 v1 / v2 / baseline on dev and held-out (P0 recall is the only gate; trap assertions, noise, the one thing, judge, cost), §2 diagnostics per morning with every miss attributed to the stage that lost it, then variants, customize and the simulation checks. Credit is decided by exact keys and cited sources, the product's decider for the ambiguous cases; every decision is listed. `eval/history.md` logs prompt changes; v1 is tag `v1-extraction-centric`.

## Data

```
uv run digest generate --world dev --anchor 2026-09-24      # world/dev/ (storylines, prose) → data/dev/ + the answer key
```

Refuses unreviewed storylines; validates planted phrases, threading, time zones and pronoun rules. Held-out: `--world heldout --anchor 2026-03-26`.

## Layout

`digest/` the product (never reads `world/` or `eval/`; a test enforces it) · `prompts/` one versioned file per LLM prompt · `config/` models and thresholds · `profile/` Avery's profile and the customize examples · `world/`, `generator/` the synthetic world and its renderer · `data/` the rendered inbox, calendars, notes, tasks · `eval/` answer keys, scorer, judge, reports · `runs/examples/` committed runs · `sessions/` Claude Code transcripts · `docs/` the assignment, `DESIGN_LOG.md`, `CAPABILITIES.md`, handoffs.
