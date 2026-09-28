# Daily Digest

A one-page 6:00am PT triage digest for "Avery Chen", built from synthetic email, calendar, notes and tasks. A fixed pipeline: code for rules and date math, small structured LLM calls for judgment, scored against a human-reviewed answer key. Design in `DESIGN.md`; the frozen spec in `CLAUDE.md` and `specs/`.

*Draft of 2026-09-28; finalized at submission. Commands marked (lands with …) are still being built.*

## Install

```
uv sync --all-groups          # Python 3.12, dependencies, editable install
cp .env.example .env          # paste OPENROUTER_API_KEY
uv run pytest                 # tests
uv run digest llm-check       # one live structured call through OpenRouter, cached and costed
```

## Run it against the dataset

```
uv run digest run --world dev --as-of 2026-09-24T06:00          # (lands with Track A, M5)
```

Writes `runs/dev/2026-09-24T06-00/digest.md` plus every stage's artifacts (`extractions.jsonl`, `candidates.jsonl`, `triage.jsonl`, `compose.json`, `actions.jsonl`, `verify.json`) and `cost.json`. The dev world's run days are Sun 2026-09-20 to Thu 2026-09-24; `--as-of` picks the morning. Options: `--customize profile/customize/board_prep.md`, `--variant stale_inbox|no_notes|corrupt_ics`. A tiny hand-made world runs with `--world tests/fixtures/mini`.

## Evaluate

```
uv run digest eval --world dev                                  # (lands with Track C, M6)
```

Scores the run artifacts against `eval/manifests/dev.yaml` and writes `eval/reports/dev_<date>.md`: P0 recall (the gate), trap assertions, must-not rate, one-thing accuracy, per-stage metrics, and every miss attributed to the stage that lost it.

## Regenerate the data

```
uv run digest generate --world dev --anchor 2026-09-24          # (lands with Track B, M2)
```

Renders `world/dev/` (storylines, people, prose) into `data/dev/` and the answer key; refuses to run on storylines that have not been reviewed.

## Layout

| Path | What |
|---|---|
| `digest/` | the product; never reads `world/` or `eval/` (a test enforces it) |
| `prompts/` | one file per LLM prompt, versioned |
| `config/models.yaml`, `config/settings.yaml` | model per role and reasoning effort; thresholds not in the profile |
| `profile/profile.md` | Avery's profile, verbatim from the assignment |
| `world/`, `generator/` | the synthetic world's script and the code that renders it |
| `data/<world>/` | the rendered inbox, calendars, notes, tasks: the only data the digest reads |
| `eval/` | manifests (answer keys), scorer, judge, reports, `history.md` |
| `runs/` | per-run artifacts and cost (examples committed under `runs/examples/`) |
| `sessions/` | exported Claude Code transcripts |
| `docs/` | the assignment, the design log, track handoffs |
