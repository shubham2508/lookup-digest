# Daily Digest — Design

*What we built, how well it works, what we rejected, how it would run, what comes next. Numbers: `eval/reports/{dev,heldout}_2026-09-29.md`; v1's from `*_v1.md` (tag `v1-extraction-centric`).*

## What we built

A fixed pipeline, not an agent loop: ingest → normalize (SQLite) → **contact spine** (code, one cached LLM call per contact) → **routing** (headers where they prove it, then Jev picks person / system ask / system FYI / list mail for the rest; unsure → read) → **thread readers** (LLM, one call per thread from a person or a system that asks something, on the raw thread plus the events and threads with the same people, every note and the task list) → **sweeps** (LLM: calendar, notes+tasks, newsletters) → **safety nets** (code) → reconcile and merge (code narrows, the linker decides) → **compose** (LLM, one call, with raw excerpts) → materialize (drafts read the message they answer) → verify (code) → render.

- **Read, don't extract.** Every judgment reads the source. A reader sees the whole thread as written, who the people are (category, tier, the profile's own words), what code computed (business days waiting, who wrote last) and what code retrieved because it might matter. It returns open-world **Findings** (what to do, why, priority, deadline, actions, ambiguity, contradictions), each with verbatim citations that code checks exist.
- **Code is the floor, not the gate.** Code does the math and enforces the hard rules (no drafts to Sam, recruiters only as a pattern, every claim cited, P0 only for a profile-tier contact, an incident or a family matter, suspicious content never P0), and eight safety nets sit under recall. Nothing is decided by keywords, word lists or string similarity (routing is headers, then Jev): "is this the same thing?" goes to TypeSafe's Jev (calibrated probabilities), and to the LLM when Jev is below 0.7.
- **Actions are a judgment.** Eleven action types; a draft only when Avery can finish it in under a minute. A stale inbox caps confidence and says "may be a sync gap"; contradictions show both sides; drift becomes a proposed profile update, never an edit.
- **One profile, any owner.** The owner's name, time zone, contacts, tiers and rules come from `profile/profile.md`; the code and prompts name no one.
- **The eval mirrors the product.** A 30-day world written as storylines whose `expectations:` are the answer key, reviewed by a human before any data existed. P0 recall is the gate; trap assertions, noise and the one thing are reported; each miss is attributed to the first stage that lost it.

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

Credit is by exact key or a cited source unique to the expected item; shared-source cases go to the product's decider, and every decision is listed in the report. Held-out is a second world with new people and disguised traps, run once and never tuned on. The judge is this Claude Code session applying `prompts/judge.md` (scores in `eval/judge/in_session/`); the DeepSeek judge is configured for an API run. After a final code review, Thursday was rerun on both worlds on the submitted code (`eval/reports/review_fixes_2026-09-29.md`): dev day 30 is unchanged (P0 8/8, the one thing right); held-out day 30 now finds all 8 P0s, which puts held-out at 92.3% P0 recall and 151/207 traps over the five mornings (dev 126/175). After submission the last keyword decisions were removed and routing moved to Jev (headers where they prove it, then Jev: person, system ask, system FYI, list mail; no regex nets; reader context from shared people; `OPEN_QUESTIONS.md` #26, #27): dev Thursday scores 124/175 with P0 8/8 and the one thing right, against 120/175 for the submitted code rerun cold, so the 126 was a good draw; held-out has not been rerun.

## Why the design changed on the last night

v1 extracted every document into a fact schema, generated candidates from twenty fixed rule types, and only then let an LLM judge, on the extracted facts. It reached 100% P0 recall on dev, but every late fix patched a fact the extractor had missed. Shubham rejected it as lossy and closed-world (`docs/DESIGN_LOG.md` 30–31, `specs/PIVOT_SPEC.md`). v2 was built in one night by three parallel sessions on one shared contract, `digest/findings.py`, so the tail of the pipeline, the artifacts, the UI and most of the scorer carried over.

## Considered and rejected

| Rejected | Why |
|---|---|
| Extraction-centric pipeline (v1) | Lossy and closed-world; rewarded metadata accuracy over digest usefulness |
| One long-context call over the whole inbox | Misses can't be attributed; kept only as the baseline to beat |
| String similarity for "same thing?", in the product or the grader | Misfired on real data; hard-fact narrowing plus a classifier and an LLM instead |
| Rulings as prompt edits | Opaque; a rulings store with exact scope, provenance and expiry instead |
| Customize as a runtime plugin | Untrusted per-run text must not add capabilities |

## Running it on a schedule

Ingest incrementally (hourly), compose at 06:00 in the owner's time zone from the delta. Local launchd for a demo; a timezone-aware cloud scheduler (Cloud Scheduler or EventBridge with an explicit zone) in production, so 06:00 does not drift twice a year. About $0.30 a cold morning; a midday rerun reuses every cached reading whose thread did not change.

## Week two

A closed loop (an accepted draft becomes sent mail, so the next morning sees it resolved); answering cards by replying to the digest email; midday runs; Slack and Gmail behind the same normalize layer; the API judge calibrated against this session's scores; reader tags carried across mornings.
