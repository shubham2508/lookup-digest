# Extraction Schema & Stage Contracts — v1 (draft for freeze)

Companion to `DESIGN_LOG.md` (resolves O19). This is the contract between the **generator** (labels), **extractor**, **compute**, **triage**, and **eval**. Types are written as Python/Pydantic-style pseudocode.

---

## 0. Principles

1. **Facts, not judgment.** The extractor never outputs priority, urgency, "matters today," or actions. It outputs what the document says, plus a few classifications (type, intent, domain) that are properties of the document itself.
2. **Every extracted fact carries evidence.** Evidence is a source ID plus a verbatim quote of at most 20 words. Code verifies the quote is a substring of the source; if not, the fact is dropped and logged. This is the main anti-hallucination guard, and it's also what produces citations in the digest.
3. **Dates resolve against the message timestamp, not the run date.** "Tonight" in a Tuesday 16:42 message means Tuesday 23:59 PT. Keep both the raw phrase and the resolution.
4. **Extraction runs per thread / note / task / newsletter,** cached by `input_hash = hash(content) + hash(profile_contacts) + prompt_version`.
5. **Content is data.** Instructions inside emails are never followed; they're reported (`suspicious_instructions`).
6. **Gender-neutral.** Never infer or record gender for anyone.

---

## 1. Shared types

```python
class Evidence:
    source_id: str          # msg:<message-id> | note:<path>#L<line> | task:<id> | event:<uid>
    quote: str              # verbatim, ≤20 words; must be a substring of the source (code-checked)

class ResolvedTime:
    raw: str                # "tonight", "by Friday", "next quarter"
    resolved: datetime | None   # America/Los_Angeles; resolved against the message timestamp
    granularity: Literal["exact", "day", "week", "month", "quarter", "unknown"]
    confidence: Literal["high", "medium", "low"]

class EntityRef:
    kind: Literal["person", "org", "deal", "candidate", "customer_account", "project", "meeting", "document"]
    name: str               # as written in the source
    contact_hint: str | None    # email address if known

AboutKey = str
# Format: <kind>:<primary-slug>[:<qualifier>]
# kind ∈ {deal, offer, candidate, rollout, renewal, meeting, report, approval, invoice,
#         incident, pricing, hiring-req, board-update, contract, family, other}
# e.g. "deal:series-a:cap-table", "offer:mei-tanaka", "rollout:halberd:may-28",
#      "renewal:veritas", "board-update:monthly", "incident:veritas:ingest"
# Slugs come from the contact directory / profile names where possible (see §6 risk).
```

---

## 2. Normalized inputs (code, no LLM)

### 2.1 Email thread (input to the extractor)

```python
class NormalizedMessage:
    message_id: str
    in_reply_to: str | None
    sent_at: datetime               # PT
    from_addr: str
    from_name: str
    to: list[str]; cc: list[str]
    subject: str
    body_new: str                   # quoted history stripped (each message is present separately)
    signature_block: str | None     # kept separately for role/org extraction
    headers: dict                   # List-Unsubscribe, Precedence, etc.
    is_from_avery: bool

class NormalizedThread:
    thread_id: str
    messages: list[NormalizedMessage]   # chronological
    router_type: Literal["human", "newsletter", "marketing", "automated", "unsure"]  # deterministic pass
```

Forwards: the forwarded chain is parsed into its own messages where possible, with `forwarded_by` recorded, so Tomás's 14-message forward stays readable.

### 2.2 Calendar event (code only)

```python
class NormalizedEvent:
    uid: str
    recurrence_id: str | None
    calendar: Literal["work", "shared_family"]
    title: str; description: str | None; location: str | None
    start: datetime; end: datetime      # PT
    organizer: str                      # email
    organizer_is_avery: bool
    attendees: list[{email, name, partstat}]
    avery_partstat: Literal["ACCEPTED", "DECLINED", "TENTATIVE", "NEEDS-ACTION", "ORGANIZER"]
    created: datetime; last_modified: datetime
    domain: Literal["work", "personal"]  # shared_family → personal; else work unless title/desc says otherwise (code heuristic)
```

### 2.3 Task (code parse + light extractor pass)

```python
class NormalizedTask:
    task_id: str
    title: str
    due: date | None
    status: Literal["open", "done"]
    file_last_modified: datetime        # for staleness
```

---

## 3. Extractor output

One call per document. `type` comes first; the rest depends on it.

```python
class ExtractionMeta:
    schema_version: str
    prompt_version: str
    model: str
    input_hash: str
    extracted_at: datetime

class Extraction:
    meta: ExtractionMeta
    source_id: str                      # thread_id | note path | task_id
    type: Literal["human_thread", "newsletter", "marketing", "automated", "note", "task"]
    payload: HumanThread | Newsletter | Automated | Note | TaskLink | None   # None for marketing
```

### 3.1 Human thread

```python
class HumanThread:
    summary: str                        # ≤40 words, own words, no judgment
    about: list[AboutKey]               # 1–3
    domain: Literal["work", "personal"]
    intent_primary: Literal["ask", "escalation", "commitment_update", "fyi", "social", "promotional"]
    intent_secondary: list[...same...]

    # --- who has the ball ---
    ball: Ball
    # --- people ---
    sender_observations: list[SenderObservation]
    # --- things that need doing ---
    asks: list[Ask]
    commitments: list[Commitment]
    deferrals: list[Deferral]
    # --- things that change facts ---
    schedule_mentions: list[ScheduleMention]
    stage_signals: list[StageSignal]
    role_changes: list[RoleChange]
    claims: list[Claim]
    # --- safety ---
    suspicious_instructions: list[Evidence]

class Ball:
    awaiting: Literal["avery", "other", "nobody", "unclear"]
    awaiting_who: str | None            # email, when "other"
    last_message_by: str                # email
    last_message_at: datetime
    closed_by_courtesy: bool            # last message is only "thanks!"/"got it" → effectively closed
    evidence: Evidence

class SenderObservation:                # compute merges these into the contact directory
    email: str
    name: str
    title: str | None                   # from signature
    org: str | None                     # from signature or domain
    relationship_hint: Literal["family", "capital", "customer", "team", "hiring", "vendor",
                               "network", "external_visibility", "legal_gov", "cold_inbound",
                               "automated", "unresolved"]
    subtype_hint: str | None            # e.g. "lead_investor", "deal_counsel", "retained_search", "daycare"
    introduced_by: str | None           # email of introducer, if a warm intro
    evidence: list[Evidence]

class Ask:
    from_: str                          # email
    to_avery: bool                      # directed at Avery vs. someone else
    kind: Literal["decision", "approval", "signature", "information", "meeting", "review", "other"]
    what: str                           # ≤15 words
    deadline: ResolvedTime | None
    status: Literal["open", "answered", "withdrawn"]
    answered_by_message: str | None
    evidence: Evidence

class Commitment:
    owner: Literal["avery", "other"]
    owner_email: str
    to_whom: list[str]
    what: str                           # ≤15 words
    due: ResolvedTime | None
    status_in_thread: Literal["open", "fulfilled", "cancelled", "superseded"]
    fulfilled_by: str | None            # message_id, if fulfilled within this thread
    fulfills_hint: str | None           # if THIS thread fulfills a commitment made elsewhere ("here's the cap table")
    about: AboutKey
    evidence: Evidence

class Deferral:
    what: str
    by: str                             # email
    until: ResolvedTime
    about: AboutKey
    evidence: Evidence

class ScheduleMention:                  # for calendar-vs-email contradiction joins
    action: Literal["proposed", "confirmed", "moved", "cancelled"]
    meeting_desc: str
    participants: list[str]
    when: ResolvedTime | None
    previous_when: ResolvedTime | None  # for "moved"
    evidence: Evidence

class StageSignal:                      # lifecycle stage for relationships/entities
    entity: EntityRef
    stage: str                          # vocabulary per category, see §4
    at: datetime
    evidence: Evidence

class RoleChange:                       # "I'm taking over from Renee"
    person: str                         # email
    new_role: str | None
    org: str | None
    replaces: str | None                # email/name of the predecessor
    evidence: Evidence

class Claim:                            # numbers/facts for drift detection vs. profile
    subject: str                        # "ARR", "headcount", "runway", "board_update_cadence"
    value: str                          # "$3.4M", "monthly"
    as_of: ResolvedTime | None
    evidence: Evidence
```

### 3.2 Newsletter

```python
class Newsletter:
    publication: str
    issue_date: date
    items: list[NewsItem]               # only items touching Avery's standing topics (from profile)

class NewsItem:
    headline: str                       # own words
    summary: str                        # ≤30 words, own words
    topics: list[str]                   # from the standing-topics vocabulary
    entities: list[EntityRef]           # orgs/products named (e.g. "Halberd", "DeepSeek", "OpenRouter")
    effective_date: ResolvedTime | None
    evidence: Evidence
```

Relevance to Avery's *current* work is **not** decided here. Compute joins `entities`/`topics` against active entities → `news_attachment` candidates.

### 3.3 Automated

```python
class Automated:
    system: str                         # "DocuSign", "Stripe", "Expensify", "GitHub", ...
    action_bearing: bool                # does it require an action from Avery?
    action_kind: Literal["signature", "approval", "payment_issue", "security", "none"]
    what: str
    deadline: ResolvedTime | None
    about: AboutKey | None              # e.g. "offer:mei-tanaka" for the DocuSign
    link_present: bool
    evidence: Evidence
```

### 3.4 Note

```python
class Note:
    note_kind: Literal["meeting_notes", "draft", "todo", "status"]
    meeting_date: date | None
    attendees: list[str]
    summary: str                        # ≤40 words
    about: list[AboutKey]
    decisions: list[{what, decided_by, date, about, evidence}]
    action_items: list[Commitment]      # reuse Commitment; owner may be Avery
    agreements: list[{rule, cadence, applies_to, evidence}]   # "monthly board updates during the raise"
    open_comments: list[{by, what, status: open|resolved, evidence}]
    claims: list[Claim]                 # a draft's "$3.2M ARR" is captured here
    stage_signals: list[StageSignal]
    draft_of: str | None                # for drafts: what it's a draft of ("board update")
```

### 3.5 Task link

```python
class TaskLink:                         # light pass: connects a task to the about-key space
    about: AboutKey
    entities: list[EntityRef]
```

---

## 4. Lifecycle stage vocabularies

| Category | Stages |
|---|---|
| Capital | `first_contact`, `in_conversation`, `diligence`, `term_sheet`, `closing`, `closed`, `existing`, `passed` |
| Customer | `prospect`, `onboarding`, `active`, `renewal_window`, `at_risk`, `churned` |
| Hiring (candidate) | `sourced`, `screen`, `onsite`, `debrief`, `offer_extended`, `offer_signed`, `rejected`, `withdrawn` |
| Hiring (req) | `open`, `paused`, `filled`, `closed` |
| Vendor | `evaluating`, `active_contract`, `renewal_due`, `cancelled` |

Compute takes the **latest** stage signal per entity (by `at`), with the evidence.

---

## 5. Downstream contracts (sketch; finalize during build)

### 5.1 Contact (compute)

```python
class Contact:
    contact_id: str
    names: list[str]; emails: list[str]
    org: str | None; title: str | None
    relationship: {category, subtype, stage, source: "profile" | "inferred" | "unresolved", evidence: list[Evidence]}
    profile_rules: list[str]            # e.g. "email means intentional" (Priya), "never draft" (Sam)
    behavior: {avery_reply_rate, median_avery_reply_hours, last_inbound, last_outbound,
               initiation_ratio, shared_meetings_30d}
    drift: list[{field, profile_value, data_value, evidence}]
```

Resolution order: profile match → internal domain → known firm/customer domains (learned from threads) → majority of `relationship_hint`s → `unresolved` if hints conflict or evidence is too thin.

### 5.2 Candidate (compute)

```python
class Candidate:
    candidate_id: str
    type: Literal[...]                  # DESIGN_LOG §3.5
    about: AboutKey
    entities: list[str]                 # contact_ids / entity slugs
    facts: dict                         # computed: business_days_quiet, overlap_minutes, days_overdue, cadence_before/after...
    evidence: list[Evidence]
    context_refs: list[str]             # related source_ids retrieved by entity + time
    source_dependencies: list[Literal["email", "calendar", "notes", "tasks"]]
    freshness_cap: Literal["none", "stale", "missing"]
```

### 5.3 Triage output

```python
class TriageResult:
    candidate_id: str
    include: bool
    section: Literal["urgent", "decisions", "news", "pulse", "calendar_personal"]
    priority: Literal["P0", "P1", "P2", "P3"]
    due_today: bool
    confidence: Literal["high", "medium", "low"]
    why: str                            # ≤20 words; becomes the "why now" line
    citations: list[Evidence]
    ambiguity: {type: "preference" | "factual" | "third_party", question, options: list[str], default: int} | None
    proposed_actions: list[ProposedAction]   # 0–2

class ProposedAction:
    type: Literal["reply", "forward_delegate", "task", "calendar_response", "approve", "decide",
                  "question", "read", "message_person", "watch", "profile_update"]
    target: str | None                  # recipient / event uid / task title
    brief: str                          # what it must say or do, ≤40 words
    assumptions: list[str]
    watch_trigger: str | None           # required for "watch"
    read_start: str | None              # message_id to start reading from, for "read"
```

---

## 6. Known risks in this schema

1. **About-key consistency.** Independent extractor calls may name the same thing differently (`offer:mei-tanaka` vs. `offer:mei`). Mitigations: fixed `kind` vocabulary; slugs from the contact directory, which is passed to the extractor; compute merges keys by fuzzy match on slug + shared entities + shared evidence messages. Measure it: about-key merge accuracy is an eval metric.
2. **Relative-date resolution.** The LLM resolves against the message timestamp given in the prompt. Eval checks resolved dates against labels (tolerance: same day for `day` granularity). If accuracy is poor, move resolution to code (a date-parsing library on `raw`).
3. **Cross-thread fulfillment.** `fulfills_hint` is free text; compute must match it to an open commitment via about key + recipients + time order. Planted trap S16 tests this.
4. **Quote limit of 20 words** may be too tight for some evidence; tune after first runs.

---

## 7. Manifest labels (what the generator must emit)

The generator knows the truth, so it emits labels shaped like the extraction, for scoring:

```yaml
thread: t-0142
expected:
  type: human_thread
  domain: work
  intent_primary: ask
  about: [deal:series-a:cap-table]
  ball: {awaiting: avery}
  sender_relationship: {category: capital, subtype: lead_investor, stage: diligence}
  commitments:
    - {owner: avery, about: deal:series-a:cap-table, due_day: 28, status_in_thread: open}
  schedule_mentions: []
  suspicious: false
```

Plus per contact: category, subtype, stage (as of each run day). Plus per run day: expected candidates, triage outcome (include, section, priority band), expected action types, and trap assertions.

**Matching rules for scoring:** commitments and asks match on about key + owner (fuzzy about-key match allowed, as in §6.1); dates match within granularity tolerance; free-text fields (`summary`, `what`, `brief`) are never scored by exact match.
