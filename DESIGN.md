# Daily Digest — Design

*One page: what we built, what we considered and rejected, how it would run on a schedule, and week two.*
*Submitted 2026-09-29. Numbers are from `eval/reports/dev_2026-09-29_v1.md` and `heldout_2026-09-29_v1.md` (v1 tag).*

## What we built

A fixed pipeline, not an agent loop: ingest → normalize (SQLite) → router → **extract** (LLM, one call per thread, note or newsletter, cached) → **compute** (code) → **triage** (LLM, per candidate) → reduce (code) → **compose** (LLM, one call) → materialize (LLM for replies, templates for everything else) → verify (code) → render.

- **Code where it must be right, LLMs where judgment is needed.** Business-day math, overlaps, thresholds, dedupe, the freshness report and every hard rule (no drafts to Sam, recruiters only as a pattern, every claim cited) are Python. The three LLM layers answer three different questions: *what is this?* (extractor: facts only, each with a verbatim quote of at most 20 words that code checks is a substring of the source), *does it matter today, and what action?* (triage, anchored P0 to P3 rubric), *what matters most and how does the page read?* (compose, which can cut and reframe but never add).
- **Actions are a judgment, not just drafts.** Eleven action types: reply, forward, task, calendar response, approve, decide, question card, read, message a person, watch, profile update. A draft is proposed only if Avery can finish it in under a minute with what the digest provides; otherwise the digest says where to start reading.
- **Honesty changes conclusions, not just the header.** Every candidate records the sources it depends on. A stale inbox caps confidence and qualifies "quiet for three days" with "may be a sync gap". Contradictions show both sides. The tool never edits `profile.md`: data wins on facts, the profile wins on preferences, and drift becomes a proposed profile update.
- **Customize is layered config, not a plugin.** `--customize` compiles into overrides (sections, length, focus, tone) over the profile over defaults, with locked invariants: citations, staleness flags, and P0 items that cannot be silently hidden.
- **The eval is the product's mirror.** A synthetic 30-day world is authored as storylines whose `expectations:` blocks *are* the answer key, reviewed by a human before any data exists, then rendered by code into emails with real threading, an `.ics` with recurrence and RSVP state, ten notes and five tasks, so every label is exact. Scoring is mostly exact matching per stage, with every miss attributed to the first stage that lost it. An LLM judge from a third model family scores only fuzzy qualities. The single gate is P0 recall of 100%. **Results (five mornings per world):** dev: P0 recall 100% versus 75% for a one-call baseline; the one thing right on both mornings that have one (baseline 0 of 2); 115 of 175 trap checks versus 34 of 74; 6.6% noise; 20 of 21 memory checks in the 5-day simulation; about $0.05–0.08 a morning once extraction is cached, about $0.50 cold. **Held-out** (a second world with new people and disguised traps, run once, never tuned on): P0 recall 84.6% (baseline 62.5%), the one thing right on 1 of 2 mornings, 129 of 207 trap checks versus 44 of 83, 6.6% noise, 12 of 13 memory checks. The dev/held-out gap is the honest measure of how much late tuning fitted dev.
- **Models.** One cheap model (GPT-6 Luna) runs the whole pipeline with reasoning effort dialled per stage; the world's prose was written by a Claude session; the judge is a third family so it grades neither its own writing nor the pipeline's. Cost per run is logged from the API response.

## Considered and rejected

| Rejected | Why |
|---|---|
| Event-driven instant replies | Avery batch-reads in three windows; a digest is triage, not a chatbot |
| One long-context call over the whole inbox | Misses can't be attributed, and there is no way to tell whether the digest is good. Kept only as the baseline to beat |
| Fully deterministic signals | Most signals need judgment; only "Avery had the last word" is deterministic |
| Drafting in parallel with composing | Wasted drafts for cut items; compose enriches the briefs first |
| Hard entity clustering | Entities overlap; candidates plus retrieved context instead |
| A flat default tier for unknown senders | Not intelligent; relationship, lifecycle stage, intent and context, inferred from evidence |
| Rulings as prompt edits | Opaque and irreversible; a rulings store with scope, provenance and expiry instead |
| Customize as a runtime plugin system | Untrusted per-run text must not add capabilities |
| Anchoring the world to the sample's date | Incidental; worlds are relative days with an anchor parameter |

## Running it on a schedule

Decouple ingestion from composition: ingest incrementally (hourly, or on new mail), compose at 06:00 PT from the delta. Options: (1) local cron or launchd, fine for a demo; (2) GitHub Actions cron, UTC-only with start delays, so "06:00 PT sharp" breaks twice a year at DST changes; (3) a timezone-aware cloud scheduler (Cloud Scheduler or EventBridge with an explicit timezone) triggering a container job, with the SQLite store on a mounted volume. Recommendation: (3) for production, (1) for the demo. Optional runs near 12:25 and in the evening cover mail that lands after 06:00, the known gap of a single morning run.

## What integration taught us

The first real run produced 124 candidates and 50 items for a Sunday whose answer key expected about ten. Every cause was in code, not in the model: recruiter pitches becoming reply candidates, newsletter items attaching to the word "Series A", one contradiction per occurrence of a recurring meeting, and topic keys that either failed to merge (five items for one board update) or over-merged (three job candidates into one). The fixes were rules and thresholds in compute, plus two prompt lines; the extraction prompt did not change. That is the argument for keeping judgment small and code large: when the digest was wrong, the artifacts said which rule, and the fix was a test away.

Two corrections came from review rather than scores. **Word similarity went out:** compute used string-similarity thresholds to decide whether two topic keys, an email meeting and a calendar event, or a promise and a task were the same thing; they misfired on real data, so code now only narrows the options by hard facts (same people, nearby dates, later in time) and the linker decides sameness: TypeSafe's Jev, a classifier model with calibrated probabilities (0.4 s, $0.00002 a question), answers first, and a batched LLM call decides the questions Jev is unsure of (top probability below 0.7; it had put an obvious meeting move at 0.49). Every link is logged with who decided it. **A prompt leak came out:** worked examples in six prompts had been copied from the dev storylines, answers included; they now use a made-up cast that appears in no mailbox, and every number reported here was measured after that change.

## Known issues (from the final reports)

| Issue | Where | Cause |
|---|---|---|
| Held-out misses one P0 on two mornings: a meeting whose email and calendar disagree | link, triage | The email↔event link and triage's reading did not generalize from dev |
| Held-out one thing: an incident beat the investor's overdue deliverable | compose | The same choice was fixed on dev through dev-specific facts; the rule itself did not change |
| Later stages never read the source | triage, compose, drafts | Only the extractor sees emails; the rest sees extracted facts and short summaries, so an extraction miss cannot be recovered (the week-two item below) |
| A promise fulfilled in a new thread still showed (S16) | extract, context | Fixed after the final runs (commit 2646f5b, with tests); the reports predate it |
| Weekend mode runs over 100 words | customize | Ten P0s are never hidden; the invariant wins over the length |
| Some items never get "third time flagged" | compute | Their topic key changes between mornings, so the count restarts |
| Background noise: many approval items, a duplicated recruiter-pattern line | compute | Candidate rules are broader than the answer key |

## Week two

**Let judgment read the source.** Extraction is lossy, and every late fix here patched a fact the extractor missed. Keep extraction as the index that finds candidates, but give triage and the drafter the candidate's own thread text (about $0.02 a run). The same review makes the evidence check less literal. Then: a closed loop (an accepted draft becomes Avery's sent mail, so the next morning sees it resolved), answering cards by replying to the digest email, midday runs, Slack and Gmail sources behind the same normalize layer, and the judge calibration round against a second model.
