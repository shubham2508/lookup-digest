# Daily Digest — Design

*One page: what we built, what we considered and rejected, how it would run on a schedule, and week two.*
*Draft of 2026-09-28; the results line is filled in at submission.*

## What we built

A fixed pipeline, not an agent loop: ingest → normalize (SQLite) → router → **extract** (LLM, one call per thread, note or newsletter, cached) → **compute** (code) → **triage** (LLM, per candidate) → reduce (code) → **compose** (LLM, one call) → materialize (LLM for replies, templates for everything else) → verify (code) → render.

- **Code where it must be right, LLMs where judgment is needed.** Business-day math, overlaps, thresholds, dedupe, the freshness report and every hard rule (no drafts to Sam, recruiters only as a pattern, every claim cited) are Python. The three LLM layers answer three different questions: *what is this?* (extractor: facts only, each with a verbatim quote of at most 20 words that code checks is a substring of the source), *does it matter today, and what action?* (triage, anchored P0 to P3 rubric), *what matters most and how does the page read?* (compose, which can cut and reframe but never add).
- **Actions are a judgment, not just drafts.** Eleven action types: reply, forward, task, calendar response, approve, decide, question card, read, message a person, watch, profile update. A draft is proposed only if Avery can finish it in under a minute with what the digest provides; otherwise the digest says where to start reading.
- **Honesty changes conclusions, not just the header.** Every candidate records the sources it depends on. A stale inbox caps confidence and qualifies "quiet for three days" with "may be a sync gap". Contradictions show both sides. The tool never edits `profile.md`: data wins on facts, the profile wins on preferences, and drift becomes a proposed profile update.
- **Customize is layered config, not a plugin.** `--customize` compiles into overrides (sections, length, focus, tone) over the profile over defaults, with locked invariants: citations, staleness flags, and P0 items that cannot be silently hidden.
- **The eval is the product's mirror.** A synthetic 30-day world is authored as storylines whose `expectations:` blocks *are* the answer key, reviewed by a human before any data exists, then rendered by code into emails with real threading, an `.ics` with recurrence and RSVP state, ten notes and five tasks, so every label is exact. Scoring is mostly exact matching per stage, with every miss attributed to the first stage that lost it. An LLM judge from a third model family scores only fuzzy qualities. The single gate is P0 recall of 100%. **Results:** [filled at submission].
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

## Week two

A reply channel: Avery answers question cards by replying to the digest email, and the answer becomes a ruling. Midday runs. Source plugins (Slack, Gmail) behind the same normalize layer, the one place a microkernel design fits. The held-out world and the multi-day simulation if they did not make the first cut. A judge-scored rubric for drafts, calibrated against a stronger model once.
