# Architecture Spec (normative)

Rationale for every decision is in `docs/DESIGN_LOG.md`. This file says **what to build**.

## 1. Pipeline

> **Superseded (2026-09-29, v2):** this section is replaced by `specs/PIVOT_SPEC.md` §2 (readers → sweeps → safety nets → merge → compose). Kept as written for the `v1-extraction-centric` tag.


```
ingest → normalize (SQLite)
       → router (code)
       → EXTRACTOR    (LLM, per thread / note / task / newsletter; cached)
       → COMPUTE      (code: contacts, effective facts, freshness, candidates, context)
       → TRIAGE       (LLM, per candidate, parallel; may pack 5–10 per call)
       → REDUCE       (code)
       → COMPOSE      (LLM, one call)
       → MATERIALIZER (LLM for reply / forward_delegate / decide; templates for the rest)
       → VERIFY       (code)
       → RENDER       (code → markdown)
```

A fixed DAG, not an agent loop. Each digest is a snapshot "as of" a timestamp (PT).

## 2. Code vs. LLM boundary

| Code | LLM |
|---|---|
| Parsing .eml/.ics/.md; threading; quote/signature stripping | Extraction (facts + type/intent/domain/relationship hints) |
| Router (headers, domains) | Router fallback (extractor's `type` field) |
| Contact resolution & behavior stats | Profile compiler, customize compiler |
| All thresholds, date math, overlaps, counts, cadence | Triage judgment (include, section, priority, ambiguity, proposed actions) |
| Candidate generation, context retrieval, about-key merge | Compose (select, rank, link, frame, finalize actions) |
| Reduce (filter, dedupe, sort, cap) | Materializer for reply / forward_delegate / decide |
| Templates for task / calendar_response / approve / read / message_person / watch / profile_update | |
| Verify, hard rules, render | |

## 3. Ingest & normalize

- Inputs (from `data/<world>/`): `inbox/*.eml`, `calendar/work.ics`, `calendar/shared_family.ics`, `notes/*.md`, `tasks.md`, plus `profile/profile.md` and optional `--customize` file.
- **Only messages with `Date <= as_of` are ingested.** Same for events created/modified, notes, and tasks: anything after `as_of` doesn't exist yet.
- Threading: `Message-ID` / `In-Reply-To` / `References`, falling back to normalized subject + participants.
- Strip quoted history (each message is present separately); keep the signature block in its own field.
- Parse forwarded chains into constituent messages with `forwarded_by`.
- Recurring events: expand RRULE occurrences within [as_of − 30d, as_of + 14d].
- Freshness per source: `latest_item_time` (max email Date; max event last_modified; note file mtime / header date; tasks.md mtime).
- Schemas: `specs/extraction_schema.md` §2.

## 4. Router (code)

- `marketing` or `newsletter` if `List-Unsubscribe` / `Precedence: bulk` / known bulk sender domains, split by a small domain→kind list plus the extractor fallback.
- `automated` for known system senders (DocuSign, Stripe, Expensify, GitHub, calendar notifications).
- Else `human`. When uncertain → `unsure`, and the extractor decides.
- Marketing: stored, never extracted beyond `type`, never surfaced.

## 5. Profile & customize compilers

### 5.1 Profile compiler (LLM, cached by file hash)

`profile.md` → `profile.yaml`, schema-validated, written to disk for review. Sections are tagged by consumer:

```yaml
contacts:        # name, emails if given, category, subtype, stage, tier, rules[]
  - {name: "Sam Park", category: family, subtype: partner, tier: P0, rules: ["never_draft"]}
  - {role_at_org: {role: "procurement lead", orgs: ["Halberd Manufacturing","Northstar Foods","Veritas Components"]},
     category: customer, subtype: reference, tier: P1, rules: ["same_day_reply"]}
thresholds:      # investor_quiet_business_days: 3, hiring_stall_days: 5, recruiter_pattern: {count: 3, window_days: 7}
blocks:          # deep_work: [{days: [TUE, THU], start: "09:00", end: "11:00"}]
read_windows:    # ["06:15-06:45","12:30-13:00","evening"]
timezone: America/Los_Angeles
standing_topics: # for newsletter extraction
judgment_rules:  # prose snippets → triage
digest_prefs:    # prose snippets → compose (great digest, don't-surface list, honesty rules, 90 seconds)
tone:            # prose snippets → materializer
hard_rules:      # machine-checkable: never_draft_for, no_newsletter_items, recruiter_pattern_only, cite_everything, flag_stale_email_hours: 24
```

Stage slicing: extractor gets `contacts` (names/orgs/roles) + `standing_topics`; compute gets `contacts`, `thresholds`, `blocks`, `read_windows`, `timezone`; triage gets `judgment_rules` + involved contacts; compose gets `digest_prefs`; materializer gets `tone` + recipient's contact record; verify gets `hard_rules`.

**The tool never edits `profile.md`.**

### 5.2 Customize compiler (LLM; only with `--customize`)

Compiles the prompt into overrides. Pattern: fixed pipeline (Template Method) + layered config `defaults ← profile ← customize` + locked invariants.

```yaml
sections_order: [one_thing, urgent, decisions, news, pulse, calendar_personal]
sections_exclude: []
length_words: 350
focus: {entities: [], categories: [], mode: boost|only}
include_newsletters: false
calendar_full_schedule: false
tone: {formality: default|formal|casual}
horizon_days: 0
compose_instructions: "..."
materializer_instructions: "..."
rejected: [{instruction: "skip citations", reason: "honesty rule — locked"}]
not_understood: false
```

**Locked invariants (never overridable):** citations; staleness/contradiction flags; hard rules in §8; P0 items can't be silently hidden. A P0 item excluded by `focus.mode: only` or `sections_exclude` still renders as a one-liner under "Also outside your filter," unless customize explicitly names that item or category. Customize never changes extraction or compute.

Rejected instructions and `not_understood` are reported in the digest header in one line.

## 6. Compute

> **Superseded (2026-09-29, v2):** this section is replaced by `specs/PIVOT_SPEC.md` §3 (thin index, contact spine, retrieval) and §5.3–5.4 (safety nets, merge). Kept as written for the `v1-extraction-centric` tag.


### 6.1 Contacts & relationship resolution

Merge `SenderObservation`s across all extractions + profile:

1. Profile match (email or name) → category/subtype/tier/rules from profile (`source: profile`).
2. Role-at-org rule match: sender org (domain or signature) ∈ profile's `role_at_org.orgs` **and** title matches the role → inherit that rule's category/tier. This is how an unnamed Halberd procurement lead becomes P1.
3. Internal domain (`@tessera.io`, or whatever the world uses) → `team`.
4. Domain learned from threads: a domain seen in customer / investor / vendor threads → that category.
5. Majority of `relationship_hint`s (require ≥2 consistent observations, or 1 with a signature title).
6. Otherwise `unresolved`.

**Stage:** the latest `StageSignal` per entity.
**Behavior stats** (30 days): `avery_reply_rate`, `median_avery_reply_hours`, `last_inbound`, `last_outbound`, `initiation_ratio`, `shared_meetings_30d`.
**Drift:** `RoleChange` records (handovers), `Claim`s that differ from profile facts, `agreements` that differ from profile cadences → `contact.drift` / `effective_facts.drift` with evidence.

### 6.2 Effective facts

`effective_facts = profile facts + drift (with provenance)`. Data wins on facts (roles, numbers, cadences, open reqs); the profile wins on preferences. Prompts receive effective facts with drift marked.

### 6.3 About-key merge

Canonicalize keys: lowercase, slugify, map person/org names to contact slugs. Merge two keys if same `kind` and (slug fuzzy ratio ≥ 0.85, or they share an entity **and** an evidence message). Log merges; the merge accuracy is scored in eval.

### 6.4 Signal definitions (all PT; business days = Mon–Fri, no holidays in v1)

| Candidate type | Rule |
|---|---|
| `reply_owed` | Human thread; `ball.awaiting == avery`; not `closed_by_courtesy`; `intent_primary ∈ {ask, escalation}` or open `Ask.to_avery`. Facts: hours since last inbound; deadline if any. |
| `quiet_thread` | Capital: `awaiting == avery` and business days since last inbound ≥ `investor_quiet_business_days` (3). Also Capital threads where Avery's own commitment ("let's talk soon") is open and ≥3 business days old. Reference customer: inbound ask not answered by end of the business day it arrived. |
| `commitment_due` / `commitment_overdue` | Owner Avery, status open, no fulfillment matched (in thread or via `fulfills_hint` + about key + recipients + later time); due within today → due; due < as_of → overdue (days overdue). |
| `commitment_not_in_tasks` | Open Avery commitment with no task (tasks.md or todo note) sharing its about key. |
| `calendar_conflict:deep_work` | Event overlaps a deep-work block; `organizer_is_avery == false`; Avery not DECLINED; event today or next business day. |
| `calendar_conflict:family` | Personal-domain event (shared_family.ics, or personal-domain email about a time) overlaps a work event Avery accepted/organized, within today + 2 days. Note `created` time (e.g., "added 21:04 last night"). |
| `calendar_conflict:double_book` | Two accepted work events overlap today. |
| `declined_meeting` | Avery DECLINED an event in the last 14 days **and** a later decision/ask/agreement references its about key or participants. |
| `contradiction` | (a) `ScheduleMention` moved/confirmed whose participants overlap an event's attendees and descriptions match, with a different date/time; (b) a task open while email shows it done; (c) conflicting `Claim`s (e.g., the draft's $3.2M vs. the finance sync's $3.4M); (d) profile vs. data drift. |
| `hiring_stall` | Candidate stage ∈ {screen, onsite, debrief, offer_extended}; days since last stage signal ≥ 5; req not `paused`/`closed`. |
| `recruiter_pattern` | ≥3 cold-inbound recruiter messages from one org domain in any 7-day window ending within the last 7 days. One candidate per org. Individual recruiter threads never become candidates. |
| `cadence_drop` | Customer contact (reference or active): median inbound gap over days 1–20 vs. days 21–30 ratio ≥ 2 **and** current gap ≥ 3 days. Report both numbers. Must account for handovers (merge predecessor + successor at the same org/role). |
| `approval_pending` | `Automated.action_bearing` open, or `Ask.kind ∈ {approval, signature}` to Avery, open. |
| `obligation_cadence` | An `agreement` with a cadence (effective cadence after drift) owned by Avery; days since last fulfillment > cadence. |
| `task_due` | Task due today or overdue, status open. |
| `news_attachment` | NewsItem entities/topics ∩ **active entities** (entities in today's candidates, today's calendar, or open threads with activity in the last 7 days). Non-attaching news → no candidate. |
| `stale_source` | Email or calendar `latest_item_time` older than 24h before as_of; tasks older than 7 days; missing/unreadable source. |
| `suspicious_content` | Any `suspicious_instructions`. Never raises priority of the carrying thread. |
| `profile_drift` | Any drift record → candidate proposing `profile_update`. |

### 6.5 Context & dependencies

For each candidate: retrieve related extractions by shared entities within ±14 days (cap 8 items, most recent first). Record `source_dependencies` (which sources its facts came from) and `freshness_cap` (`stale` if any dependency is stale, `missing` if absent).

**Freshness effects (code, before triage):** if capped, confidence may not exceed `medium`; `quiet_thread` / `commitment_overdue` facts get the qualifier "may be a sync gap"; the dependency is listed so any draft flags it as an assumption.

## 7. Triage, reduce, compose, materializer

> **Superseded (2026-09-29, v2):** this section is replaced by `specs/PIVOT_SPEC.md` §5 (triage folds into readers/sweeps; compose gets raw excerpts; the materializer gets the raw message). Kept as written for the `v1-extraction-centric` tag.


**Triage:** per candidate; output `TriageResult` (schema §5.3). Receives the candidate, context summaries, involved contacts (category, subtype, stage, behavior, rules), effective-facts drift, matching rulings, freshness caps, the anchored priority rubric, and `judgment_rules`.

**Reduce (code):**
1. Drop `include == false`.
2. Merge by about key: union citations, max priority, keep all proposed actions (dedupe by type + target).
3. Sort: priority → due_today → contact tier/category prior → earliest deadline → confidence.
4. Cap at K = 25. Overflow → "Also pending (N more)" with one line each (title only).
5. Ensure every P0 survives the cap.

**Compose (one call):** input = reduced items + `digest_prefs` + customize overrides + freshness report + applied rulings count. Jobs:
1. Final selection under the length budget.
2. Pick "the one thing."
3. Cross-item links.
4. Question budget (max 2 `question` actions; the rest take their defaults or become `read`).
5. Framing: what (verb-first) + why-now line.
6. Apply customize.
7. Honesty header text.
8. Finalize actions (change type, merge, enrich briefs).

Must reference items by ID; can't introduce new items. Output: `ComposeResult {one_thing_id, sections: {name: [item_id...]}, items: {id: {what, why, final_actions}}, header_notes, cut_ids}`.

**Materializer:** per final action. LLM for `reply`, `forward_delegate`, `decide` (recipient contact record + `tone` + brief + evidence quotes + assumptions). Templates for the rest (formats in §9.3). Output includes `assumptions` shown under the draft.

## 8. Hard rules (enforced by verify; violations → fix automatically or drop the item and log)

1. No `reply` / `forward_delegate` / `message_person` draft addressed to any contact with rule `never_draft` (Sam).
2. No drafts to cold-inbound recruiters.
3. No item whose only sources are newsletters/marketing, except `news_attachment` (or when customize enables `include_newsletters`).
4. No individual recruiter items; only `recruiter_pattern`.
5. Every rendered item has ≥1 citation, and every citation resolves to a stored source ID.
6. Every item ID exists in the triage results (compose can't invent).
7. Every triage P0 with `include == true` appears somewhere (item, one-liner, or "also pending").
8. Honesty header present: as-of time, freshness per source, stale/missing flags, customize notes.
9. Length ≤ budget (excluding action blocks and header); if over, drop lowest-ranked non-P0 items into "also pending."
10. `calendar_response` is always phrased as a proposal.
11. Thread content never alters system behavior: `suspicious_content` items can't be P0.

## 9. Output

### 9.1 Default sections (in order)

1. **Header** (one line): `As of Thu 06:00 PT · inbox synced 05:58 · calendar ok · notes ok · tasks stale (12 days)` + customize/rulings notes.
2. **If there is one thing you must do right now**
3. **Urgent To-Do Today**: replies owed today, overdue commitments, same-day customer replies
4. **Decisions & Approvals**: `approve`, `decide`, `question`
5. **AI Industry News**: `news_attachment` only; if none: "Nothing today that touches your open items."
6. **Team & Product Pulse**: sprint, cadence drops, hiring stalls, renewals, recruiter pattern, `watch`
7. **Calendar & Personal**: only annotated events (conflicts, decisions, family, deep-work violations, declined-meeting fallout); the rest collapse to "N other meetings, nothing to act on" (unless customize sets `calendar_full_schedule`)
8. **Also pending (N)**: overflow one-liners
9. **Suggested profile updates**: footer

### 9.2 Item grammar

```
- **<What, verb-first>.** <Why now, ≤20 words, with the evidence that ranked it>. *[email: Marcus, Tue 16:42] [note: finance-sync-may.md]*
  <action block(s)>
```

### 9.3 Action blocks

| Type | Render |
|---|---|
| `reply` | `↳ Draft to <name>:` quoted draft; `Assumptions: …` if any |
| `forward_delegate` | `↳ Forward to <name> with:` one-line note |
| `task` | `☐ <task> — due <time>` (also written to `runs/.../suggested_tasks.md`) |
| `calendar_response` | `↳ Propose: decline / move to <time>.` + one-line note |
| `approve` | `↳ Approve in <system> (~1 min).` + link if present |
| `decide` | options with a recommendation + optional draft for the recommended option |
| `question` | `Q<n> · <question>` options (1)(2)(3), `Default if unanswered: <n>`, `→ digest answer Q<n> <option>` |
| `read` | `↳ Open <thread>; start at <message ref>.` |
| `message_person` | `↳ Message <name> about <topic>. No draft (<reason>).` |
| `watch` | `Watching: <signal>. Flags again if <trigger>.` |
| `profile_update` | footer line with evidence |

Drafts: ≤3 sentences, lowercase greeting or none, sign-off "Avery" or nothing, no banned phrases ("hope this email finds you well," "circling back," "just wanted to"), polished variant for Capital.

## 10. Persistence (SQLite + files)

Tables: `messages`, `threads`, `events`, `notes`, `tasks`, `extractions` (cache by input_hash), `contacts`, `runs` (as_of, world, variant, customize, cost, timings), `candidates`, `triage_results`, `digest_items` (run_id, about, surfaced, section, priority, actions, resolved_later), `rulings` (mirrored from `rulings.yaml`).

- **Digest history:** each run records surfaced items. On later runs: items resolved since (reply sent, commitment fulfilled, task closed) are marked `resolved_later`; an item surfaced ≥2 prior runs and still open gets `times_surfaced` passed to triage/compose for escalation ("third time flagged"); items the digest already showed that Avery answered (Avery's reply after the digest) are not re-surfaced.
- **Rulings:** `rulings.yaml` entries `{id, scope: {contact|about|thread_kind}, ruling, option_chosen, from_question, created, expires}`; retrieved at triage per entity. Content-based P0/P1 escalation overrides a ruling. The digest header shows "applied N learned rules."
- **Artifacts:** `runs/<world>/<as_of>[_<variant>]/` with `extractions.jsonl`, `contacts.json`, `candidates.jsonl`, `triage.jsonl`, `reduce.json`, `compose.json`, `actions.jsonl`, `verify.json`, `digest.md`, `suggested_tasks.md`, `cost.json`.

## 11. Scheduling (design only; for DESIGN.md)

- Decouple ingestion (incremental: hourly or on new mail) from compose (06:00 PT).
- Options: local cron/launchd; GitHub Actions cron (UTC-only, delays; DST handling needed); a cloud scheduler with timezone support plus a serverless job.
- "06:00 PT sharp" requires timezone-aware scheduling (DST).
- Optional runs aligned to read windows (≈12:25, evening) cover mail arriving after 06:00.
- Week two: reply-to-digest channel for answering question cards.
