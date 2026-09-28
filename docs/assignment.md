# "Daily Digest" — A Personal Triage Tool

Assignment text from the myRico work-trial PDF (`docs/myrico.pdf`, pages 1–2), lightly reformatted as markdown. Avery's profile is in `profile/profile.md` and the sample digest in `docs/sample_digest.md`, both extracted verbatim from the same PDF.

## What you're building

A tool that produces a personalized morning digest for one person, "Avery Chen" — a founder of a 12-person startup. Avery has three information sources.

You should create these synthetic data sources with diverse distribution.

1. Inbox — ~500 synthetic emails over 30 days
2. Calendar — a synthetic .ics file with 30 days of meetings, declines, blocks
3. Notes — a directory of 10 markdown notes (meeting notes, drafts, todos) from the company meetings
4. Tasks – a list of 5 tasks Avery has to undertake

The system has a default format of the daily digest given below.

Given in the appendix is profile.md describing who Avery is, what they care about, who matters to them.

Create a tool that produces a one-page digest that:

1. Highlights what genuinely matters today
2. Surfaces what Avery might be missing (forgotten threads, declined meetings, stale follow-ups, contradictions between sources)
3. Drafts replies or task items for anything dispatchable in under a minute
4. Is honest when sources are stale, missing, or contradictory — no fabricated certainty
5. Takes an option of –customize=prompt.md where it customizes the digest if the prompt is provided. If the option is not provided, the default format is produced.
6. Provide a design for running this tool on a schedule of choice. You do not have to implement it, but explain your options on design and recommended approach.

## The bounds

- You can use any AI tool you want, we will love to see your sessions.
- You can choose the interface for request/response (CLI, web, Slack, email).
- You choose the LLM, harness, prompting strategy, persistence, architecture, and language. You can use claude/codex/gemini CLI to simulate the work. If you want to do programmatic work, need we can give you a OpenRouter API key with a small budget.

## What you show us

1. A private repo with working code and synthetic data sets, shared with us
2. A 1-page README — how to install and run it against the dataset
3. A 1-page design doc explaining: what you built, what you considered and rejected, and what you'd do with a second week
4. A walkthrough meeting after you are done.

## What we're not looking for

- A finished product
- A beautiful UI
- A 12-screen architecture diagram

We want to see how you think, build, and use AI under a real constraint.

## Anti-patterns to avoid (these will hurt your grade)

- Letting the AI pick your architecture without you having an opinion
- No way to tell whether your digest is actually good
- Spending the week on the UI while the engine stays thin
- Not being able to defend your choices against pushback
