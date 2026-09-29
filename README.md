# Daily Digest

A one-page 6:00am PT triage digest for "Avery Chen", built from a synthetic month of email, calendar, notes and tasks. LLM readers judge the raw threads; code does the math, the hard rules and a recall floor; the result is scored against a human-reviewed answer key. Design and results in `DESIGN.md`; the spec in `CLAUDE.md`, `specs/PIVOT_SPEC.md` (v2) and `specs/`.

## Install

```
uv sync --all-groups          # Python 3.12, dependencies, editable install
cp .env.example .env          # paste OPENROUTER_API_KEY
uv run pytest                 # ~381 tests
uv run digest llm-check       # one live structured call through OpenRouter, cached and costed
```

Models are in `config/models.yaml`: the pipeline runs on `openai/gpt-6-luna` with reasoning effort per role; TypeSafe's Jev answers the linker's "same thing?" questions first. The synthetic world's prose was written by a Claude session, not an API call. The judge role is `deepseek/deepseek-v4.1-flash`; the submitted scores were produced in-session (see Evaluate).

## Fresh clone: what you need, what you get

| You need | Why |
|---|---|
| `uv` (it installs Python 3.12 into `.venv`) | `uv sync --all-groups` |
| An OpenRouter key with a few dollars of credit, in `.env` | one morning costs about $0.20 cold (readers are cached per thread and date; a rerun is a cent); the full eval matrix about $2 per world. TypeSafe's Jev is used through the same key when available; if it is not, the linker falls back to the LLM on its own |

Everything else is in the repo: both worlds' data (`data/dev`, `data/heldout`: inbox, calendars, notes, tasks), the answer keys, the profile, the prompts, the config, finished example runs under `runs/examples/` (digests, every artifact, one full LLM trace) and the final reports under `eval/reports/`. So without a key you can still read a digest and its trace; with one, your first `digest run` produces the same kind of page in 4–5 minutes. Local only, created on first use: `.env`, `runs/`, the LLM cache in `.cache/`, the SQLite store, the compiled `profile/profile.yaml`.

**Try the memory in two minutes of typing** (about $0.60, three cold mornings):

```
uv run digest run --world dev --as-of 2026-09-21T06:00      # Monday: a question card Q1 appears
uv run digest answer Q1 2 --world dev                        # answer it → runs/dev/rulings.yaml
uv run digest run --world dev --as-of 2026-09-22T06:00      # Tuesday: header says "applied 1 learned rule"; the card is gone
uv run digest run --world dev --as-of 2026-09-23T06:00      # Wednesday: an item shown three mornings running says "third time flagged"
```

Or let the harness do the whole loop with a simulated Avery answering the cards from the answer key, then score it (report §6 "Multi-day simulation"):

```
uv run digest simulate --world dev --days 5 --fresh          # ~$1, 15–20 min
uv run digest eval --world dev
```

## Run it against the dataset

```
uv run digest run --world dev --as-of 2026-09-24T06:00
```

Writes `runs/dev/2026-09-24T06-00/digest.md` plus every stage's artifacts: `contacts.json` (the spine), `findings.jsonl` (every reader, sweep and safety-net finding), `candidates.jsonl` and `triage.jsonl` (the same findings in the downstream shape), `links.jsonl` (every sameness decision and who made it), `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`, `suggested_tasks.md`, `cost.json`, `run.json` and `trace.jsonl` (every LLM call with its full input and output). The dev world's run days are Sun 2026-09-20 to Thu 2026-09-24; Thursday is the dense one. A cold morning costs about $0.15 (readers are cached per thread and date); a rerun of the same morning about a cent.

Options:

```
--customize profile/customize/board_prep.md     # writes to …_customize-board_prep/
--variant stale_inbox|no_notes|corrupt_ics      # honesty variants, run conditions on the same data
uv run digest baseline --world dev --as-of …    # naive one-call baseline → …_baseline/digest.md
uv run digest answer Q1 2 --world dev           # answer a question card → runs/dev/rulings.yaml
uv run digest run --world tests/fixtures/mini … # a tiny hand-made world for development
python -m digest.compute.sweeps --world dev --as-of 2026-09-24T06:00   # sweeps, nets and reconcile, printed
```

## Evaluate

```
uv run digest eval --world dev --customize-suite --baseline
uv run digest simulate --world dev --days 5 --fresh    # multi-day loop, simulated Avery answers the cards
uv run digest eval --matrix --world dev                 # everything above in one command, then the report
uv run digest eval --world dev --judge-export items.jsonl   # judge items with rendered rubric prompts, for in-session judging
uv run digest eval --world dev --judge-scores scores.yaml   # read the scores back into the report (--judge runs the API judge instead)
```

`docs/CAPABILITIES.md` lists every capability with the test that checks it and where the result appears. Scores every run against `eval/manifests/dev.yaml` and writes `eval/reports/dev_<date>.md`: §1 a v1 / v2 / baseline table (P0 recall, the only gate; trap assertions; must-not rate; one-thing accuracy; judge; cost), §2 diagnostics per morning (reader recall on planted threads, sweep and safety-net recall with the rescue list, merge errors, hard rules, contact classification), then the honesty variants, the customize suite and the simulation checks. Credit is decided by exact keys and by sources (a citation of a source unique to the expected item); the shared-source cases go to the product's decider and every such decision is listed in the report. `eval/history.md` logs prompt changes with before and after numbers. The v1 pipeline is tag `v1-extraction-centric`; its reports are `eval/reports/*_v1.md`.

## Debug UI

```
uv run digest ui                                        # http://127.0.0.1:8765
```

A local page over `runs/`, and the only launch config in `.vscode/launch.json` ("Digest"). Pick a world and a morning and run it, or score the world, run the full matrix, simulate five days, or regenerate the data; then read the digest, every stage's table, the trace of every LLM call with its full prompt and output, degradations, cost, and the eval reports. One pipeline at a time: the page refuses a second launch while one is running.

## Regenerate the data

```
uv run digest generate --world dev --anchor 2026-09-24
```

Renders `world/dev/` (people, storylines, prose) into `data/dev/` and the answer key in about two seconds. It refuses to run on a storyline that has not been reviewed (`reviewed: true`), and its validator checks every planted phrase is verbatim, threading resolves, offsets are Pacific time, and no prose gendered Avery or Sam. The held-out world uses `--world heldout --anchor 2026-03-26`. `eval/data_audit.md` samples the result for realism.

## Layout

| Path | What |
|---|---|
| `digest/` | the product; never reads `world/` or `eval/` (a test enforces it). `read/` readers, `compute/` spine, retrieval, sweeps, safety nets, linker, merge; `findings.py` the Finding → downstream mapping |
| `prompts/` | one versioned file per LLM prompt: thread_reader, the three sweeps, contact_classifier, signature_parser, linker, topic_grouper, compose, materializer, profile and customize compilers, baseline, judge, sim_avery |
| `config/` | `models.yaml` (model per role, reasoning effort, output caps) and `settings.yaml` (thresholds not in the profile) |
| `profile/profile.md` | Avery's profile, verbatim from the assignment; `profile.yaml` is compiled from it |
| `world/`, `generator/` | the synthetic world's script and prose, and the code that renders it |
| `data/<world>/` | the rendered inbox, calendars, notes, tasks: the only data the digest reads |
| `eval/` | manifests (answer keys), scorer, judge, sim_avery, reports, `history.md`, `v1_results.yaml` |
| `runs/` | per-run artifacts and cost; `runs/examples/` is committed |
| `sessions/` | exported Claude Code transcripts |
| `docs/` | the assignment, the design log, the handoffs (`docs/handoffs/v2-*`) and status board |
