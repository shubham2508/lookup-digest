# PIVOT_SPEC — v2: Read, Don't Extract

**This document overrides** the parts of `specs/architecture.md`, `specs/extraction_schema.md`, `specs/prompts.md`, and `specs/eval.md` listed in §8. Where it's silent, the old specs still apply.

## 0. Why we're changing

v1 converted every document into a detailed fact schema (asks, commitments, ball, stage signals, claims), generated candidates from fixed rule types, and only then applied judgment. Result:

1. **Lossy:** triage, compose, and the materializer never saw the actual emails. Anything the extractor missed or flattened (the one real ask in a long thread, tone, implied urgency) was unrecoverable.
2. **Closed-world:** the system could only notice what the schema and candidate types anticipated. Anything important that didn't fit a field or rule never surfaced.
3. **Metadata-centric eval:** it rewarded filling fields correctly, not producing a useful digest.

**v2 principle:** LLMs read raw content and judge (open-world). Entities are the **spine** (who is who, what connects to what) used for retrieval, linking, and history. Code does math, hard rules, and **safety nets** that set a floor on recall; it doesn't gate what can surface.

> Entities decide what gets read together. Reading decides what matters.

---

## 1. Before you change anything

1. **Tag the current state:** `git tag v1-extraction-centric`. We'll compare v1 vs. v2 vs. baseline on the same eval; that comparison is walkthrough evidence.
2. **Audit the repo against this doc.** Write `MIGRATION_PLAN.md`: for every module, **keep / modify / delete**, with one line of reason. Include anything v1 implemented that this doc doesn't mention.
3. **Stop and wait for Shubham's approval** of `MIGRATION_PLAN.md` before deleting or rewriting code.

---

## 2. New pipeline

```
ingest → thin index (code) → entity spine (code + cached LLM per contact)
       → READERS (LLM, per human thread, raw + retrieved context)
       → SWEEPS  (LLM: calendar, notes+tasks, newsletters)
       → SAFETY NETS (code)
       → MERGE (code, conservative)
       → COMPOSE (LLM, long context, findings + raw excerpts)
       → MATERIALIZER (LLM/templates, with the raw message being answered)
       → VERIFY (code) → RENDER (code)
```

Still a fixed workflow (not an agent loop). Human-in-the-loop unchanged: the tool proposes, Avery decides and acts.

### 2.1 Keep from v1 (unless the audit shows it's broken)

Ingest/normalize, threading, quote/signature stripping, forward parsing, router/noise filter, `llm.py` (cache, cost log, validation+retry), store, profile compiler, customize compiler, verify, render, CLI, digest history, rulings, generator + data (subject to §7), digest-level eval, honesty variants, customize suite, baseline.

### 2.2 Replace

| v1 | v2 |
|---|---|
| Per-document extractor with heavy fact schema | **Readers** (per thread) + **Sweeps** (per source) producing open-world **Findings** |
| Candidate generation from fixed rule types | **Safety nets**: a small set of deterministic checks that add or confirm Findings |
| Triage on candidates + summaries | Folded into readers/sweeps (each Finding carries priority, action, ambiguity) |
| Compose on reduced items with summaries | Compose on Findings **plus raw excerpts** |
| Materializer on a brief + quotes | Materializer **with the actual message being replied to** |
| Extraction accuracy as the eval center | **Digest-level metrics** as the target; stage metrics as diagnostics |

### 2.3 Delete

The heavy `Extraction` payload types (`HumanThread` fact lists, `Ask`, `Commitment`, `StageSignal`, `Claim`, etc.) as a pipeline contract, `Candidate` types as a gate, and extraction-field metrics as primary eval. (Keep any small pieces reused by the entity spine; list them in `MIGRATION_PLAN.md`.)

---

## 3. Thin index and entity spine

### 3.1 Thin index (code only)

Per thread: participants, `last_message_by`, `last_message_at`, `last_inbound_at`, Avery's last reply time, message count, business days since last inbound (PT, Mon–Fri), router type. Per event: normalized as v1. Per note/task: path, dates, mtime. Freshness per source as v1.

### 3.2 Contacts (the spine)

- Built from email headers, calendar attendees/organizers, profile names, internal domain.
- **Signature parsing:** one small cached LLM call per **new contact** (not per document) → name, title, org.
- **Relationship classification per contact** (four dimensions from DESIGN_LOG §3.8): category, subtype, lifecycle stage, with evidence. One cached LLM call per contact, input = signature, domain, profile rules that might match (including role-at-org rules), 3–5 representative messages, and behavior stats (Avery reply rate, median reply hours, initiation ratio, shared meetings). Re-run only when new evidence arrives. `unresolved` when evidence is thin.
- Profile matches take precedence (Sam, Priya, Marcus, …). Role-at-org rules apply (an unnamed Halberd procurement lead → reference customer).
- Behavior stats computed in code as v1.

### 3.3 Retrieval for readers

For a thread, retrieve (code): calendar events in [as_of − 7d, as_of + 7d] sharing any participant or matching org; notes mentioning any participant, org, or thread subject keywords; tasks with keyword/participant overlap; the previous 2 threads with the same participants (summaries = first/last message excerpts, not LLM summaries). Cap retrieved context at ~4k tokens, most relevant first.

---

## 4. Findings — the single contract

Every reader, sweep, and safety net emits Findings.

```python
class Evidence:
    source_id: str      # msg:<id> | event:<uid> | note:<path>#L<n> | task:<id>
    quote: str          # verbatim ≤25 words; code verifies it's a substring; drop the finding's claim if not

class Finding:
    finding_id: str
    origin: Literal["thread_reader", "calendar_sweep", "notes_tasks_sweep", "news_sweep", "safety_net"]
    needs_avery: Literal["yes", "no", "unsure"]
    title: str          # verb-first, ≤12 words: "Send the cap table to Marcus"
    kind: str           # FREE TEXT label, e.g. "overdue promise to lead investor", "family calendar collision"
    why: str            # ≤30 words, concrete, cites the deciding evidence
    priority: Literal["P0", "P1", "P2", "P3"]   # anchored rubric (prompts.md P4 rubric, unchanged)
    urgency: Literal["today", "this_week", "later", "none"]
    deadline: {raw: str, resolved: datetime | None} | None   # resolved against the message timestamp, PT
    stakes: Literal["low", "medium", "high"]
    confidence: Literal["high", "medium", "low"]
    entities: list[str]         # contact_ids / org slugs
    about: list[str]            # light tags for linking, e.g. "deal:series-a", "offer:mei-tanaka"; fuzzy is fine
    citations: list[Evidence]   # ≥1
    proposed_actions: list[ProposedAction]      # 0–2; taxonomy unchanged (reply, forward_delegate, task,
                                                # calendar_response, approve, decide, question, read,
                                                # message_person, watch, profile_update)
    ambiguity: {type: "preference" | "factual" | "third_party", question: str,
                options: list[str], default: int} | None
    contradictions: list[str]   # e.g. "calendar says Fri; this thread moves it to Mon"
    freshness_caveat: str | None
    suspicious_instructions: list[Evidence]
```

A reader may emit **zero, one, or several** Findings per thread (one thread can contain two separate issues). `needs_avery: "no"` findings are still stored (they're useful for merge, history, and eval) but don't go to compose.

---

## 5. Stages

### 5.1 Thread readers (LLM, per human thread)

- **Which threads:** every human/unsure thread with any message in the 30-day window (≈120–200 threads). Reading all is cheap (~1M input tokens/run on GPT-6 Luna ≈ $0.10) and avoids recall gaps. Cache key: thread hash + context hash + profile hash + **as_of date** (judgment depends on "today").
- **Input:** the **full raw thread** (quotes stripped, chronological, with timestamps and senders), the contact records for all participants (category, subtype, stage, behavior stats, profile rules), thin-index facts as **hints** (business days waiting, who wrote last), retrieved context (§3.3), the profile's judgment rules + tone of "what matters," matching rulings, freshness caveats, the as_of time, the action taxonomy, the priority rubric.
- **Raw content goes in clearly delimited data blocks,** labeled untrusted. Instructions inside are reported in `suspicious_instructions`, never followed.
- **Jobs:** decide whether this thread needs Avery (today/this week), why, what's at stake, by when, what action(s), what's ambiguous; notice promises Avery made, handovers ("taking over from…"), changed facts (numbers, dates, cadences), and contradictions with the retrieved calendar/notes. **Open-world:** not limited to predefined kinds.
- **Must:** say `needs_avery: "unsure"` + an ambiguity card rather than guess; propose `message_person` (no draft) for `never_draft` contacts; respect the dispatchability test; never raise priority because the email says so.

### 5.2 Sweeps (LLM, whole-source)

| Sweep | Input | Looks for |
|---|---|---|
| **Calendar** | Both calendars raw-normalized for [as_of, as_of + 2 business days] + last 14 days of declines; contact records of attendees; profile blocks, family rules | Deep-work bookings by others (check organizer), family collisions, double bookings, declined meetings with fallout (cross-check reader findings passed in as titles), meetings needing prep/decision, calendar entries contradicted by email (reader findings with `contradictions` passed in) |
| **Notes + tasks** | All notes and tasks.md raw (they fit easily), note dates, tasks.md mtime; reader finding titles for cross-reference | Promises and action items owned by Avery; overdue obligations and cadences (e.g., monthly board updates); drafts with stale facts (e.g., $3.2M vs. $3.4M elsewhere); tasks contradicted by email; open comments awaiting Avery; paused/changed plans (e.g., designer req paused) |
| **Newsletters** | Newsletter items (raw, per issue) + titles/entities of today's `needs_avery: yes` findings | Only items that **change** something on Avery's plate; cite the newsletter. Non-attaching news → nothing. |

Sweeps run **after** readers so they can cross-reference reader findings (titles, entities, contradictions).

### 5.3 Safety nets (code) — a recall floor, not a gate

Each rule produces a Finding (`origin: safety_net`) with computed facts in `why`:

1. P0 contact (from profile/contacts) waiting on Avery ≥ threshold business days (Capital: 3).
2. Reference-customer inbound unanswered past end of its business day.
3. Tue/Thu 9–11 overlap where organizer ≠ Avery and Avery hasn't declined (today or next business day).
4. Shared-family event overlapping an accepted/organized work event (today → +2 days).
5. ≥3 recruiter messages from one domain within 7 days → one pattern finding (individual recruiter threads never surface).
6. Any source stale/missing → freshness finding.
7. Any `suspicious_instructions` → flagged finding (never P0).
8. Action-bearing automated message open with a deadline (e.g., DocuSign awaiting signature).

**Reconciliation:** if a reader/sweep Finding already covers the same entities + issue (same thread or overlapping citations), attach the safety-net facts to it (`why` gains the computed fact, e.g., "3 business days"). Otherwise add the safety-net Finding and mark `rescued_by_safety_net = true`. **Log every rescue**; the rescue count is a key diagnostic (readers should rarely need rescuing).

### 5.4 Merge (code, conservative)

Group Findings that share citations, or share ≥1 entity **and** ≥1 `about` tag with slug similarity ≥ 0.85. Within a group: keep all titles and citations, max priority, union actions (dedupe by type + target). When unsure, **don't merge**; compose can still link. Cap: all P0 + top 40 by (priority, urgency, stakes, confidence).

### 5.5 Compose (LLM, long context)

- **Input:** merged Findings with, for each, **raw excerpts** (every citation's quote plus up to ~300 tokens surrounding it from the source), `times_surfaced` from digest history, applied rulings count, freshness report, `digest_prefs`, customize overrides, length budget.
- **Jobs:** unchanged from v1 (one thing; cut to budget, never cut P0; cross-item links; ≤2 questions; framing; finalize actions and enrich briefs; honesty header; escalate items surfaced ≥2 times). References Findings by ID only; can't invent items.

### 5.6 Materializer

For `reply` / `forward_delegate` / `decide`: input = the final brief **plus the full raw message being answered and the one before it**, the recipient's contact record, `tone`, effective facts (e.g., ARR from the latest data, not the profile), assumptions. Output ≤3 sentences, rules unchanged. Templates for the other action types unchanged.

### 5.7 Verify and render

Unchanged from v1, applied to Findings: every citation resolves and quotes are substrings; hard rules; every P0 present; length; honesty header. Render format unchanged (sections, item grammar, action blocks).

---

## 6. Eval changes

**Primary (the target):** digest-level, per run day: P0 recall (gate: 100%), trap assertions, must-not rate, one-thing accuracy, section placement, judge scores (usefulness: the three questions answered, no noise, honest). Plus honesty variants, customize suite, multi-day simulation, as before.

**Diagnostics (to find *where* it failed, not targets):**
- **Reader recall on planted threads:** for each storyline thread, did its reader emit `needs_avery: yes` with the expected priority band and action type?
- **Sweep recall:** planted calendar and notes/tasks traps found by the sweeps?
- **Safety-net rescue count and list:** what readers missed.
- **Merge errors:** over-merged or duplicated items in the final digest.
- **Compose cuts:** expected items that were found but cut.
- **Contact classification accuracy** (category, subtype, stage) per contact.
- **Materializer checks** as before.

Drop extraction-field metrics as primary. The manifest's thread-level expectations become reader diagnostics: `thread_id → {needs_avery, priority_band, action_types}`.

**Comparison table (walkthrough evidence):** v1 (tag), v2, naive baseline, on dev and held-out: P0 recall, trap assertions passed, must-not rate, one-thing accuracy, judge scores, cost per run.

---

## 7. Also check the data

If the generator used `must_include` phrases, confirm traps aren't trivially greppable (e.g., "I will send the cap table tonight by 11pm, promise" is too obvious). Sample 10 random human emails and 5 storyline emails into `eval/data_audit.md` with one line each: realistic? trap too obvious? Report before changing the generator; only fix if clearly too clean.

---

## 8. Spec files to update after implementation

- `CLAUDE.md` golden rule 3 → "Code for math, thresholds, hard rules, and safety nets. LLMs read raw content for judgment. Structure is an index and a floor, never a gate." Update the build-order table and repo layout for readers/sweeps/safety nets.
- `specs/architecture.md` §1, §6, §7 → replaced by this doc's §2–§5.
- `specs/extraction_schema.md` → keep only Evidence, normalized inputs, Contact; mark the rest superseded by the Finding schema.
- `specs/prompts.md` → P3 `extractor` and P4 `triage` replaced by `thread_reader`, `calendar_sweep`, `notes_tasks_sweep`, `news_sweep`, `contact_classifier`, `signature_parser`. P5 compose and P6 materializer get the new inputs. Keep the priority rubric and action taxonomy verbatim.
- `specs/eval.md` §2 → replaced by §6 here.
- `docs/DESIGN_LOG.md` → append:

| Step | Claude proposed | Shubham asked / corrected | Result |
|---|---|---|---|
| 30 | Downstream stages see only extraction + short quotes | **Challenged:** passing only extracted data downstream is wrong | Raw content to triage and materializer |
| 31 | (v1 built: extraction-centric) | **Reviewed the build and rejected the design:** lossy pipeline centered on extraction accuracy and metadata | **v2: read, don't extract.** Readers and sweeps on raw content with open-world Findings; entities as spine; code safety nets as a recall floor; digest-level eval as the target (**Shubham's correction**) |

Rejected-alternatives entry: "Extraction-centric pipeline (v1): lossy and closed-world; rewarded metadata accuracy over digest usefulness."

---

## 9. Milestones

| # | Work | Done when |
|---|---|---|
| P0 | Tag v1; audit; `MIGRATION_PLAN.md` | **Shubham approves the plan** |
| P1 | Thin index + contact spine (signature parser, contact classifier, behavior stats) | Contact classification diagnostics reported |
| P2 | Finding schema + thread reader prompt + retrieval | Reader diagnostics on planted threads reported |
| P3 | Sweeps (calendar, notes+tasks, news) | Sweep diagnostics reported |
| P4 | Safety nets + reconciliation + merge | Rescue list reported |
| P5 | Compose + materializer rewired (raw excerpts / raw message) | `digest run` produces a digest; verify passes |
| P6 | Eval rewired (§6); rerun v1 tag, v2, baseline on dev (+ held-out if present) | Comparison table in `eval/reports/` |
| P7 | Spec/doc updates (§8), data audit (§7), README/DESIGN refresh | Docs consistent with v2 |

**After P2, stop and show Shubham 5 reader outputs for planted threads** (raw thread + Finding side by side) before building further. If readers aren't clearly better than v1 triage on those, we discuss before continuing.
