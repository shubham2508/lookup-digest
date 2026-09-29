# Daily Digest — Design

*One page: what we built, why it changed shape on the last night, what was rejected, how it would run on a schedule, week two.*
*Submitted 2026-09-29. Numbers from `eval/reports/{dev,heldout}_2026-09-29.md`; v1's from the `*_v1.md` reports (tag `v1-extraction-centric`).*

## What we built

A fixed pipeline, not an agent loop: ingest → normalize (SQLite) → **contact spine** (code, one cached LLM call per contact) → **thread readers** (LLM, one call per human thread, on the raw thread plus retrieved calendar, notes and related threads) → **sweeps** (LLM: calendar, notes+tasks, newsletters) → **safety nets** (code) → reconcile and merge (code narrows, the linker decides) → **compose** (LLM, one call, with raw excerpts) → materialize (LLM drafts read the message they answer; templates for the rest) → verify (code) → render.

- **Read, don't extract.** Judgment stages read the source. A reader sees the whole thread as written, the people on it (category, tier, the profile's own words), facts code computed (business days waiting, who wrote last) and what code retrieved because it might matter. It emits open-world **Findings**: what Avery should do, why, priority, deadline, actions, ambiguity, contradictions, each with verbatim citations that code checks exist. Nothing is limited to a schema of asks and commitments.
- **Entities are the spine, code is the floor.** Code does the math, enforces the hard rules (no drafts to Sam, recruiters only as a pattern, every claim cited, P0 only for a profile-tier contact, an incident or a family matter, suspicious content never P0) and runs eight **safety nets** under recall; a net a reader already covered attaches to that finding, the rest are logged as rescues. "Is this the same thing?" is never string similarity: TypeSafe's Jev (calibrated probabilities) answers first, the LLM when Jev is unsure.
- **Actions are a judgment.** Eleven action types; a draft only when Avery can finish it in under a minute. Honesty changes conclusions: a stale inbox caps confidence and says "may be a sync gap"; contradictions show both sides; drift becomes a proposed profile update, never an edit.
- **The eval is the product's mirror.** A 30-day world authored as storylines whose `expectations:` are the answer key, reviewed by a human before any data existed. The target is digest-level: P0 recall (the gate), trap assertions, noise, the one thing. Stage metrics (reader recall on planted threads, sweep recall, rescues, merge errors, contact classification) are diagnostics, each miss attributed to the first stage that lost it. Credit is decided by sources, never by string similarity.

## Results (five mornings per world)

| | v1 dev | **v2 dev** | baseline dev | v1 held-out | **v2 held-out** | baseline held-out |
|---|---|---|---|---|---|---|
| P0 recall (gate 100%) | 100% | 100% | 50% | 84.6% | 84.6% | 0% |
| Trap checks | 115/175 | 127/175 | 40/74 | 129/207 | 149/207 | 37/83 |
| Noise (must-not rate) | 6.6% | 5.5% | 1.2% | 6.6% | 6.1% | 0% |
| One thing right | 2/2 | 2/2 | 0/2 | 1/2 | 2/2 | 0/2 |
| Judge, digest / drafts (1–5) | — | 4.4 / 3.4 / 4.4 · 4.7 / 4.3 / 3.5 | 4.0 / 4.0 / 2.0 | — | 4.4 / 3.2 / 4.4 · 4.2 / 4.5 / 3.2 | 1.0 / 3.0 / 4.0 |
| Memory checks (5-day simulation) | 20/21 | 11/11 | — | 12/13 | 14/15 | — |
| Cost per morning | $0.05 cached | $0.18 cold | $0.03 | $0.19 cold | $0.29 cold | $0.04 |

v1 is as its own reports scored it (its runs are not on disk to rescore; the tag rebuilds them). Matching in the grader uses no string similarity: an item is credited by an exact key or a citation of a source unique to the expected item, and the shared-source cases go to the same decider the product uses, every decision listed in the report (`OPEN_QUESTIONS.md` #23). Held-out is a second world with new people and disguised traps, run once on the final code and never tuned on; the dev/held-out gap is the honest measure of fit. Judge criteria: digest = answers the three questions / no noise / honest about gaps; drafts = factual / tone / assumptions flagged. The judge is this Claude Code session applying `prompts/judge.md` (scores in `eval/judge/in_session/`, read back by `--judge-scores`); the DeepSeek judge stays configured for an API run.

## Why the design changed on the last night

v1 was extraction-centric: an LLM turned every document into a fact schema, code generated candidates from twenty fixed rule types, and only then did an LLM judge, seeing extracted facts and 160-character summaries. It reached 100% P0 recall on dev, and every late fix was a patch for a fact the extractor had missed. Shubham reviewed the build and rejected the design as lossy and closed-world (`docs/DESIGN_LOG.md` 30–31, `specs/PIVOT_SPEC.md`). v2 was built in one night by three parallel sessions on one shared contract, `digest/findings.py`, which maps every Finding onto the shapes the unchanged tail of the pipeline, the artifacts, the UI and most of the scorer already consume.

## Considered and rejected

| Rejected | Why |
|---|---|
| Extraction-centric pipeline (v1) | Lossy and closed-world; rewarded metadata accuracy over digest usefulness |
| One long-context call over the whole inbox | Misses can't be attributed; kept only as the baseline to beat |
| String similarity for "same thing?", in the product or the grader | Misfired on real data; hard-fact narrowing plus a classifier and an LLM instead |
| Rulings as prompt edits | Opaque; a rulings store with exact scope, provenance and expiry instead |
| Customize as a runtime plugin | Untrusted per-run text must not add capabilities |

## Running it on a schedule

Ingest incrementally (hourly), compose at 06:00 PT from the delta. Local launchd for a demo; a timezone-aware cloud scheduler (Cloud Scheduler or EventBridge with an explicit zone) for production, so 06:00 does not drift twice a year. About $0.20 a cold morning; a midday rerun reuses every cached reading whose thread did not change.

## Known issues (from the final reports)

| Issue | Where | Cause |
|---|---|---|
| Held-out misses one P0 on two of five mornings | read, merge | Day 29: the reader took the moved diligence call as the coordinator's move while the calendar still disagreed (it surfaced on day 30). Day 30: the early-dismissal notice merged into the ENT item (both cite Sam's message) and the page does not cite the dismissal email, so the merge loses it |
| P0 generous during the raise | read, floors | Dev Thursday: 11 P0 items vs the key's 8; every IPV and WSGR thread is P0-eligible by profile tier |
| Decide-card drafts already commit | materialize | Judge `assumptions_flagged` 3.5 / 3.2: the draft for the recommended option is not marked as presupposing it; one internal remark ("the profile figure is stale") reached a reply to Marcus |
| No `profile_update` actions | read, sweep | Drift is reported but the profile line is never proposed; six assertions in each world |
| Weekend mode over 100 words; board prep does not lead with the board update | compose | P0s are never hidden and eight fill the page |
| "Message them about …" | render | Pronoun fallback when the contact behind a message_person action is unresolved |
| Held-out baseline invalid | baseline | Its JSON failed validation twice; scored as an empty digest |

## Week two

Fix the known issues above, in that order. Then: a closed loop (an accepted draft becomes Avery's sent mail, so the next morning sees it resolved); answering cards by replying to the digest email; midday runs; Slack and Gmail behind the same normalize layer; the API judge calibrated against this session's scores; reader tags carried across mornings by showing each reader the tags earlier digests used on its thread.
