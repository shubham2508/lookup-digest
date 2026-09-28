# Open Questions

Claude Code: add questions here instead of deciding silently. Format: what · where · options · suggestion.
Shubham reviews every addition (checkpoint 4). Answered items move to **Decided** at the bottom, with the date.

## Pending decisions for Shubham

### 1. Model IDs per role (`config/models.yaml`) — judge still open; needed to finish M0

Direction from Shubham (2026-09-28): small budget; GPT-6 Luna is the workhorse at per-stage reasoning effort; **generation is done by a Claude Code session (Fable 5.1), not by an API model** (decided, see bottom); a stronger model only for the judge, chosen after a short calibration. Family rule: judge ≠ OpenAI (pipeline) and ≠ Anthropic (generator). Prices are $ per 1M tokens, in / out, from the live OpenRouter catalogue; all support structured output, and Luna supports `reasoning_effort`.

| Role | Direction | Options |
|---|---|---|
| `extractor`, `triage`, `compose`, `materializer`, `compiler` | `openai/gpt-6-luna` (0.10 / 0.50), per-role `reasoning_effort`: extractor low · triage medium · compose high · materializer low · compiler low | `openai/gpt-6-luna-pro` (same price) for `compose` only |
| `generator` | **decided:** Claude Code session (Fable 5.1) writes the prose files; `generator/` code assembles, labels, validates | — |
| `judge` | third family; mid-tier is enough, because it applies one fixed rubric with the evidence attached, and everything with an expected output is scored by code | `google/gemini-3.8-flash` (0.75 / 3.75, ≈ $1 total) · `x-ai/grok-4.7` (1.6 / 4.8, ≈ $1.6) · stronger fallback `google/gemini-3.1-pro-preview` (2 / 12, ≈ $3) |
| `sim_avery` | cheapest; mostly code (matches a question card to the manifest's intended answer by about-key), LLM only as fallback | `openai/gpt-5-nano` (0.05 / 0.40) or reuse `gpt-6-luna` |

Judge calibration, one-time: on the first dev run's ~20 judged items, the Grader session scores the same items with the same rubric; if the cheap judge agrees within 1 point on ≥ 80% of them, keep it, else step up to the fallback. Recorded in DESIGN.md. Running Fable or Opus through OpenRouter as the judge of record would break the family rule now that the generator is Anthropic.

OpenRouter spend on this config ≈ $4–5 (pipeline ≈ $3, judge ≈ $1–1.6, sim_avery ≈ 0). Generation costs nothing on OpenRouter.

### 2. Anchor dates for `dev` and `heldout` — needed at M2 (dev) and M8 (heldout)

Day 30 must be a Thursday. Worlds are relative, so any Thursday works; the only real choice is whether the 30-day window crosses a DST change (PT offset flips −07:00 ↔ −08:00 mid-world, which exercises date parsing).

| Option | day 30 | day 1 | DST crossing | Note |
|---|---|---|---|---|
| dev A | Thu 2026-09-24 | Wed 2026-08-26 | none | "the last 30 days" as of setup; all PDT |
| dev B | Thu 2026-10-22 | Wed 2026-09-23 | none | recent at walkthrough time |
| heldout A | Thu 2026-03-26 | Wed 2026-02-25 | spring-forward on Mar 8 (day 12) | in the past |
| heldout B | Thu 2026-11-12 | Wed 2026-10-14 | fall-back on Nov 1 (day 19) | future-dated files |

**Suggestion:** dev A + heldout A. Dev stays clean so bugs are easy to isolate; held-out carries the DST flip in its history (not in its run days) as a fair extra stress; both are past dates, so file mtimes look normal.

### 3. Held-out world size — needed at M8

Options: full ~500 emails · minimum ~150. Cost is now session time, not API spend.
**Suggestion:** full. The assignment says "synthetic data sets", plural, and a small held-out world weakens the anti-overfitting story.

### 4. Storyline review — M1 gate (Data session)

Every `expectations:` block in `world/dev/storylines/*.yaml` needs `reviewed: true` from Shubham before `digest generate` will run. Nothing to decide yet; this is a reminder that it is the largest single block of Shubham's time (~1–2 h of careful reading).

### 5. OpenRouter key limit — needed before M2 (first large spend)

The key in `.env` works, but `GET /auth/key` reports **limit $3.00, remaining $3.00**. With generation moved into the Claude Code session, OpenRouter spend is ≈ $4–5 (question 1), so $3 is short only on headroom.
Options: raise this key's limit · create a new key without a limit.
**Suggestion:** raise the limit to ~$10. Claude Code stops and asks before any single step that would exceed the remaining limit.

### 6. Who commits on the shared branch — needed for the handoff docs

Three track sessions and the orchestrator all work on `main` in this directory.
Options: (a) each track session commits its own folders at milestone ends, orchestrator commits foundation, integration, docs · (b) only the orchestrator commits · (c) commit whenever.
**Suggestion:** (a), with commit messages prefixed `[A-product]`, `[B-data]`, `[C-grader]`, `[orchestrator]`; never `git add -A`; if two sessions run at the same moment, stagger commits (git's index lock is per repo).

### 7. Walkthrough date — sets the cut line

CLAUDE.md says: if time runs short, shrink the held-out world and M9 first, never eval. Knowing the date (or the day the repo must be shared) decides how much of M8/M9 is realistic.

## Decided

- **2026-09-28 · generator = Claude Code session (Fable 5.1), not an API model.** The Data track session writes every email body, note, and background item as prose files with labels under `world/<world>/prose/`; `generator/` code turns them into `.eml` / `.ics` / notes / tasks with real headers, threading, and DST-correct dates, emits the manifest, and runs the validator. Reproducible from world files + committed prose; a changed beat means rewriting its prose file. Zero OpenRouter spend for generation. `models.yaml` records `generator: claude-code-session`.
