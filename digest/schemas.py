"""Shared contracts: specs/extraction_schema.md §1–§5, architecture §5 (compilers) and §7 (compose).

Owned by the orchestrator. Every LLM output is validated against one of these models (CLAUDE.md rule 5).
The generator and the eval import from here, so all three tracks build against one contract. Changes go
through OPEN_QUESTIONS.md, never silently.

Conventions
- `extra="forbid"` on every model: an unexpected key is a validation error (which triggers the LLM retry).
- Datetimes are timezone-aware (`AwareDatetime`), America/Los_Angeles in practice.
- Models that an LLM emits must not use free-form dicts (strict JSON schema forbids them); use lists.
- `from_email` replaces the spec's `from_` (same meaning; avoids a keyword-shaped JSON key).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0"
EVIDENCE_MAX_WORDS = 20  # extraction_schema §0.2; §6.4 says tune after first runs

# ----------------------------------------------------------------------------- vocabularies
Priority = Literal["P0", "P1", "P2", "P3"]
Section = Literal["urgent", "decisions", "news", "pulse", "calendar_personal"]
Domain = Literal["work", "personal"]
Intent = Literal["ask", "escalation", "commitment_update", "fyi", "social", "promotional"]
DocType = Literal["human_thread", "newsletter", "marketing", "automated", "note", "task"]
RouterType = Literal["human", "bulk", "automated"]
Partstat = Literal["ACCEPTED", "DECLINED", "TENTATIVE", "NEEDS-ACTION", "ORGANIZER"]
Granularity = Literal["exact", "day", "week", "month", "quarter", "unknown"]
Confidence = Literal["high", "medium", "low"]
RelationshipHint = Literal[
    "family", "capital", "customer", "team", "hiring", "vendor", "network",
    "external_visibility", "legal_gov", "cold_inbound", "automated", "unresolved",
]
EntityKind = Literal["person", "org", "deal", "candidate", "customer_account", "project", "meeting", "document"]
ActionType = Literal[
    "reply", "forward_delegate", "task", "calendar_response", "approve", "decide",
    "question", "read", "message_person", "watch", "profile_update",
]
CandidateType = Literal[
    "reply_owed", "quiet_thread", "commitment_due", "commitment_overdue", "commitment_not_in_tasks",
    "calendar_conflict:deep_work", "calendar_conflict:family", "calendar_conflict:double_book",
    "declined_meeting", "contradiction", "hiring_stall", "recruiter_pattern", "cadence_drop",
    "approval_pending", "obligation_cadence", "task_due", "news_attachment", "stale_source",
    "suspicious_content", "profile_drift",
]
SourceKind = Literal["email", "calendar", "notes", "tasks"]
FreshnessCap = Literal["none", "stale", "missing"]
AskKind = Literal["decision", "approval", "signature", "information", "meeting", "review", "other"]
AmbiguityType = Literal["preference", "factual", "third_party"]
NoteKind = Literal["meeting_notes", "draft", "todo", "status"]
AutomatedActionKind = Literal["signature", "approval", "payment_issue", "security", "none"]
Weekday = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# extraction_schema §4: lifecycle stage vocabularies, per relationship category
STAGE_VOCAB: dict[str, tuple[str, ...]] = {
    "capital": ("first_contact", "in_conversation", "diligence", "term_sheet", "closing", "closed", "existing", "passed"),
    "customer": ("prospect", "onboarding", "active", "renewal_window", "at_risk", "churned"),
    "candidate": ("sourced", "screen", "onsite", "debrief", "offer_extended", "offer_signed", "rejected", "withdrawn"),
    "hiring_req": ("open", "paused", "filled", "closed"),
    "vendor": ("evaluating", "active_contract", "renewal_due", "cancelled"),
}

ABOUT_KINDS = (
    "deal", "offer", "candidate", "rollout", "renewal", "meeting", "report", "approval", "invoice",
    "incident", "pricing", "hiring-req", "board-update", "contract", "family", "other",
)
_ABOUT_RE = re.compile(r"^([a-z-]+):([a-z0-9][a-z0-9-]*)(?::([a-z0-9][a-z0-9-]*))?$")


def validate_about_key(v: str) -> str:
    m = _ABOUT_RE.match(v)
    if not m:
        raise ValueError(f"about key {v!r} must look like <kind>:<slug>[:<qualifier>], lowercase, hyphenated")
    if m.group(1) not in ABOUT_KINDS:
        raise ValueError(f"about key kind {m.group(1)!r} is not one of {ABOUT_KINDS}")
    return v


AboutKey = Annotated[
    str,
    AfterValidator(validate_about_key),
    Field(description="<kind>:<slug>[:<qualifier>], kind in " + ", ".join(ABOUT_KINDS)
          + "; e.g. deal:series-a:cap-table, offer:mei-tanaka, renewal:veritas"),
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ----------------------------------------------------------------------------- §1 shared types
class Evidence(Model):
    source_id: str = Field(description="msg:<message-id> | note:<path>#L<line> | task:<id> | event:<uid>")
    quote: str = Field(description=f"verbatim, at most {EVIDENCE_MAX_WORDS} words, copied exactly from the source")

    @field_validator("quote")
    @classmethod
    def _quote_ok(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("evidence quote is empty")
        if len(v.split()) > EVIDENCE_MAX_WORDS:
            raise ValueError(f"evidence quote has more than {EVIDENCE_MAX_WORDS} words")
        return v


class ResolvedTime(Model):
    raw: str = Field(description='the phrase as written: "tonight", "by Friday", "next quarter"')
    resolved: AwareDatetime | None = Field(description="ISO 8601 with offset, resolved against the message timestamp in the owner's time zone")
    granularity: Granularity
    confidence: Confidence


class EntityRef(Model):
    kind: EntityKind
    name: str = Field(description="as written in the source")
    contact_hint: str | None = Field(description="email address if known")


# ----------------------------------------------------------------------------- §2 normalized inputs (code only)
class NormalizedMessage(Model):
    message_id: str
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    sent_at: AwareDatetime
    from_addr: str
    from_name: str = ""
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = ""
    body_new: str = ""
    signature_block: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    is_from_avery: bool = False
    forwarded_by: str | None = None


class NormalizedThread(Model):
    thread_id: str
    messages: list[NormalizedMessage]
    router_type: RouterType


class Attendee(Model):
    email: str
    name: str = ""
    partstat: Partstat = "NEEDS-ACTION"


class NormalizedEvent(Model):
    uid: str
    recurrence_id: str | None = None
    calendar: Literal["work", "shared_family"]
    title: str
    description: str | None = None
    location: str | None = None
    start: AwareDatetime
    end: AwareDatetime
    organizer: str
    organizer_is_avery: bool
    attendees: list[Attendee] = Field(default_factory=list)
    avery_partstat: Partstat
    created: AwareDatetime | None = None
    last_modified: AwareDatetime | None = None
    domain: Domain = "work"
    all_day: bool = False


class NormalizedTask(Model):
    task_id: str
    title: str
    due: date | None = None
    status: Literal["open", "done"] = "open"
    file_last_modified: AwareDatetime | None = None


# ----------------------------------------------------------------------------- §3 extractor output
class ExtractionMeta(Model):
    schema_version: str = SCHEMA_VERSION
    prompt_version: str
    model: str
    input_hash: str
    extracted_at: AwareDatetime


class Ball(Model):
    awaiting: Literal["avery", "other", "nobody", "unclear"]
    awaiting_who: str | None = Field(description="email, when awaiting is 'other'")
    last_message_by: str = Field(description="email")
    last_message_at: AwareDatetime
    closed_by_courtesy: bool = Field(description='true if the last message is only "thanks!" / "got it"')
    evidence: Evidence


class SenderObservation(Model):
    email: str
    name: str
    title: str | None = Field(description="from the signature")
    org: str | None = Field(description="from the signature or the domain")
    relationship_hint: RelationshipHint
    subtype_hint: str | None = Field(description='e.g. "lead_investor", "deal_counsel", "retained_search", "daycare"')
    introduced_by: str | None = Field(description="email of the introducer, if a warm intro")
    evidence: list[Evidence]


class Ask(Model):
    from_email: str
    to_avery: bool = Field(description="directed at the owner rather than someone else")
    kind: AskKind
    what: str = Field(description="at most 15 words")
    deadline: ResolvedTime | None
    status: Literal["open", "answered", "withdrawn"]
    answered_by_message: str | None = Field(description="message id, if answered in this thread")
    evidence: Evidence


class Commitment(Model):
    owner: Literal["avery", "other"]
    owner_email: str
    to_whom: list[str]
    what: str = Field(description="at most 15 words")
    due: ResolvedTime | None
    status_in_thread: Literal["open", "fulfilled", "cancelled", "superseded"]
    fulfilled_by: str | None = Field(description="message id, if fulfilled within this thread")
    fulfills_hint: str | None = Field(description='set when THIS thread delivers something promised elsewhere ("here is the cap table")')
    about: AboutKey
    evidence: Evidence


class Deferral(Model):
    what: str
    by: str = Field(description="email")
    until: ResolvedTime
    about: AboutKey
    evidence: Evidence


class ScheduleMention(Model):
    action: Literal["proposed", "confirmed", "moved", "cancelled"]
    meeting_desc: str
    participants: list[str]
    when: ResolvedTime | None
    previous_when: ResolvedTime | None = Field(description='for "moved"')
    evidence: Evidence


class StageSignal(Model):
    entity: EntityRef
    stage: str = Field(description="vocabulary per category, see STAGE_VOCAB")
    at: AwareDatetime
    evidence: Evidence


class RoleChange(Model):
    person: str = Field(description="email")
    new_role: str | None
    org: str | None
    replaces: str | None = Field(description="email or name of the predecessor")
    evidence: Evidence


class Claim(Model):
    subject: str = Field(description='"ARR", "headcount", "runway", "board_update_cadence", ...')
    value: str = Field(description='"$3.4M", "monthly", ...')
    as_of: ResolvedTime | None
    evidence: Evidence


class HumanThread(Model):
    summary: str = Field(description="at most 40 words, own words, no judgment")
    about: list[AboutKey] = Field(description="1 to 3 keys")
    domain: Domain
    intent_primary: Intent
    intent_secondary: list[Intent]
    ball: Ball
    sender_observations: list[SenderObservation]
    asks: list[Ask]
    commitments: list[Commitment]
    deferrals: list[Deferral]
    schedule_mentions: list[ScheduleMention]
    stage_signals: list[StageSignal]
    role_changes: list[RoleChange]
    claims: list[Claim]
    suspicious_instructions: list[Evidence]


class NewsItem(Model):
    headline: str = Field(description="own words")
    summary: str = Field(description="at most 30 words, own words")
    topics: list[str] = Field(description="from the standing-topics vocabulary")
    entities: list[EntityRef]
    effective_date: ResolvedTime | None
    evidence: Evidence


class Newsletter(Model):
    publication: str
    issue_date: date
    items: list[NewsItem] = Field(description="only items touching the owner's standing topics")


class Automated(Model):
    system: str = Field(description='"DocuSign", "Stripe", "Expensify", "GitHub", ...')
    action_bearing: bool
    action_kind: AutomatedActionKind
    what: str
    deadline: ResolvedTime | None
    about: AboutKey | None
    link_present: bool
    evidence: Evidence


class Decision(Model):
    what: str
    decided_by: str
    date: date | None
    about: AboutKey
    evidence: Evidence


class Agreement(Model):
    rule: str = Field(description='"monthly board updates during the raise"')
    cadence: str | None = Field(description='"monthly", "weekly", "quarterly", or null')
    applies_to: str | None
    evidence: Evidence


class OpenComment(Model):
    by: str
    what: str
    status: Literal["open", "resolved"]
    evidence: Evidence


class Note(Model):
    note_kind: NoteKind
    meeting_date: date | None
    attendees: list[str]
    summary: str = Field(description="at most 40 words")
    about: list[AboutKey]
    decisions: list[Decision]
    action_items: list[Commitment]
    agreements: list[Agreement]
    open_comments: list[OpenComment]
    claims: list[Claim]
    stage_signals: list[StageSignal]
    draft_of: str | None = Field(description='for drafts: what it is a draft of ("board update")')


class TaskLink(Model):
    about: AboutKey
    entities: list[EntityRef]


class ExtractorOutput(Model):
    """What the extractor LLM returns for one document; code wraps it into an Extraction with meta."""
    type: DocType
    human_thread: HumanThread | None = Field(description="set when type == human_thread")
    newsletter: Newsletter | None = Field(description="set when type == newsletter")
    automated: Automated | None = Field(description="set when type == automated")
    note: Note | None = Field(description="set when type == note")
    task: TaskLink | None = Field(description="set when type == task")

    @property
    def payload(self) -> HumanThread | Newsletter | Automated | Note | TaskLink | None:
        return self.human_thread or self.newsletter or self.automated or self.note or self.task


class Extraction(Model):
    meta: ExtractionMeta
    source_id: str = Field(description="thread_id | note path | task_id")
    type: DocType
    payload: HumanThread | Newsletter | Automated | Note | TaskLink | None = None


# ----------------------------------------------------------------------------- §5.1 contacts (compute)
class Relationship(Model):
    category: RelationshipHint = "unresolved"
    subtype: str | None = None
    stage: str | None = None
    source: Literal["profile", "inferred", "unresolved"] = "unresolved"
    evidence: list[Evidence] = Field(default_factory=list)


class Behavior(Model):
    avery_reply_rate: float | None = None
    median_avery_reply_hours: float | None = None
    last_inbound: AwareDatetime | None = None
    last_outbound: AwareDatetime | None = None
    initiation_ratio: float | None = None
    shared_meetings_30d: int = 0


class Drift(Model):
    field: str
    profile_value: str | None
    data_value: str | None
    evidence: list[Evidence] = Field(default_factory=list)


class Contact(Model):
    contact_id: str
    names: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    org: str | None = None
    title: str | None = None
    relationship: Relationship = Field(default_factory=Relationship)
    tier: Priority | None = None
    profile_rules: list[str] = Field(default_factory=list)
    behavior: Behavior = Field(default_factory=Behavior)
    drift: list[Drift] = Field(default_factory=list)


# ----------------------------------------------------------------------------- §5.2 candidates (compute)
class Candidate(Model):
    candidate_id: str
    type: str = Field(description="a v1 rule name (safety nets, CandidateType) or a reader's free-text kind (v2 Finding)")
    about: AboutKey
    entities: list[str] = Field(default_factory=list, description="contact_ids / entity slugs")
    facts: dict[str, Any] = Field(default_factory=dict, description="computed: business_days_quiet, overlap_minutes, days_overdue, ...")
    evidence: list[Evidence] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    source_dependencies: list[SourceKind] = Field(default_factory=list)
    freshness_cap: FreshnessCap = "none"
    times_surfaced: int = Field(default=0, description="from digest history; ≥2 means escalate the framing")


# ----------------------------------------------------------------------------- §5.3 triage (LLM)
class Ambiguity(Model):
    type: AmbiguityType
    question: str
    options: list[str] = Field(description="2 to 3 options with consequences")
    default: int = Field(description="1-based index of the default option")


class ProposedAction(Model):
    type: ActionType
    target: str | None = Field(description="recipient email / event uid / task title")
    brief: str = Field(description="what it must say or do, at most 40 words")
    assumptions: list[str]
    watch_trigger: str | None = Field(description='required for "watch"')
    read_start: str | None = Field(description='message_id to start reading from, for "read"')


class TriageResult(Model):
    candidate_id: str
    include: bool
    section: Section
    priority: Priority
    due_today: bool
    confidence: Confidence
    why: str = Field(description="at most 20 words; becomes the why-now line")
    citations: list[Evidence]
    ambiguity: Ambiguity | None
    proposed_actions: list[ProposedAction] = Field(description="0 to 2")


# ----------------------------------------------------------------------------- v2 findings (specs/PIVOT_SPEC.md §4)
# Readers, sweeps and safety nets all emit Findings. digest/findings.py maps each one onto Candidate + TriageResult so
# reduce → compose → materialize → verify → render and every artifact keep their v1 shapes. LLM output models here
# have no defaults: strict JSON mode requires every field.
FindingOrigin = Literal["thread_reader", "calendar_sweep", "notes_tasks_sweep", "news_sweep", "safety_net"]
NeedsAvery = Literal["yes", "no", "unsure"]
Urgency = Literal["today", "this_week", "later", "none"]
Stakes = Literal["low", "medium", "high"]


class FindingDeadline(Model):
    raw: str = Field(description="the phrase as written")
    resolved: AwareDatetime | None = Field(description="ISO 8601 with offset, resolved against the message timestamp; null if unknown")


class Finding(Model):
    finding_id: str = Field(description="local id: f1, f2, …; code makes it unique per run")
    origin: FindingOrigin
    needs_avery: NeedsAvery
    title: str = Field(description="verb-first, at most 12 words")
    kind: str = Field(description='free text, e.g. "overdue promise to lead investor", "family calendar collision"')
    why: str = Field(description="at most 30 words, concrete, cites the deciding evidence")
    priority: Priority
    urgency: Urgency
    deadline: FindingDeadline | None
    stakes: Stakes
    confidence: Confidence
    section: Section
    entities: list[str] = Field(description="contact_ids / org slugs from the contact records given")
    about: list[str] = Field(description='light tags for linking, kind:slug, e.g. "deal:series-a", "offer:jun-park"')
    citations: list[Evidence] = Field(description="at least one; code drops the finding if none survives the substring check")
    proposed_actions: list[ProposedAction] = Field(description="0 to 2")
    ambiguity: Ambiguity | None
    contradictions: list[str] = Field(description='e.g. "calendar says Fri; this thread moves it to Mon"')
    freshness_caveat: str | None
    suspicious_instructions: list[Evidence]


class ReaderOutput(Model):
    """One thread reader call."""
    thread_summary: str = Field(description="at most 40 words, own words; kept for context and history")
    findings: list[Finding]


class SweepOutput(Model):
    findings: list[Finding]


class SignatureFacts(Model):
    """Signature parser: one cached call per new contact."""
    name: str | None
    title: str | None
    org: str | None
    evidence: Evidence | None


class ContactClassification(Model):
    """Contact classifier: one cached call per contact (DESIGN_LOG §3.8 dimensions)."""
    category: RelationshipHint
    subtype: str | None = Field(description="lead_investor, board, deal_counsel, procurement_lead, retained_search, recruiter, daycare, cofounder, …")
    stage: str | None = Field(description="lifecycle stage from the vocabulary for that category, or null")
    confidence: Confidence
    reason: str = Field(description="at most 30 words")
    evidence: list[Evidence]


# ----------------------------------------------------------------------------- architecture §7 compose (LLM)
class ComposeItem(Model):
    id: str = Field(description="an item id from the reduced list; never invent")
    what: str = Field(description="verb-first, bold in the render")
    why: str = Field(description="why now, at most 20 words, with the evidence that ranked it")
    final_actions: list[ProposedAction]


class SectionBlock(Model):
    name: Section
    item_ids: list[str]


class ComposeResult(Model):
    one_thing_id: str | None
    sections: list[SectionBlock]
    items: list[ComposeItem]
    header_notes: list[str]
    cut_ids: list[str] = Field(description="ids demoted to also-pending one-liners")


# ----------------------------------------------------------------------------- materializer (LLM)
class DraftOutput(Model):
    text: str = Field(description="at most 3 sentences; lowercase greeting or none; sign-off the owner's first name or nothing")
    assumptions: list[str]


class DecideOption(Model):
    label: str
    consequence: str


class DecideOutput(Model):
    options: list[DecideOption]
    recommendation: int = Field(description="1-based index of the recommended option")
    rationale: str = Field(description="one line")
    draft: str | None = Field(description="optional draft for the recommended option")
    assumptions: list[str]


# ----------------------------------------------------------------------------- architecture §5.1 profile.yaml (LLM compiler)
class RoleAtOrg(Model):
    role: str
    orgs: list[str]


class ProfileContact(Model):
    name: str | None = Field(description="null for role-at-org rules")
    emails: list[str]
    role_at_org: RoleAtOrg | None
    category: RelationshipHint
    subtype: str | None
    tier: Priority | None
    tier_condition: str | None = Field(description='e.g. "during the raise", else null')
    rules: list[str] = Field(description='machine-checkable tags: never_draft, same_day_reply, email_means_intentional, ...')
    notes: str | None = Field(description="the profile's prose about this person, verbatim")


class RecruiterRule(Model):
    count: int
    window_days: int


class Thresholds(Model):
    investor_quiet_business_days: int | None
    hiring_stall_days: int | None
    recruiter_pattern: RecruiterRule | None


class DeepWorkBlock(Model):
    days: list[Weekday]
    start: str = Field(description="HH:MM")
    end: str = Field(description="HH:MM")


class ProfileFact(Model):
    subject: str = Field(description='"ARR", "seed_raised", "headcount", "board_update_cadence", "open_reqs", ...')
    value: str


class HardRules(Model):
    never_draft_for: list[str] = Field(description="contact names")
    no_newsletter_items: bool
    recruiter_pattern_only: bool
    cite_everything: bool
    flag_stale_email_hours: int | None


class ProfileConfig(Model):
    person: str
    company: str | None
    timezone: str
    contacts: list[ProfileContact]
    facts: list[ProfileFact]
    thresholds: Thresholds
    blocks: list[DeepWorkBlock]
    read_windows: list[str]
    standing_topics: list[str]
    judgment_rules: list[str] = Field(description="prose snippets, verbatim, for triage")
    digest_prefs: list[str] = Field(description="prose snippets, verbatim, for compose")
    tone: list[str] = Field(description="prose snippets, verbatim, for the materializer")
    hard_rules: HardRules


# ----------------------------------------------------------------------------- architecture §5.2 customize overrides (LLM compiler)
class Focus(Model):
    entities: list[str]
    categories: list[str]
    mode: Literal["boost", "only"]


class ToneOverride(Model):
    formality: Literal["default", "formal", "casual"]


class RejectedInstruction(Model):
    instruction: str
    reason: str


class CustomizeOverrides(Model):
    sections_order: list[Section]
    sections_exclude: list[Section]
    length_words: int | None
    focus: Focus
    include_newsletters: bool
    calendar_full_schedule: bool
    tone: ToneOverride
    horizon_days: int
    compose_instructions: str | None
    materializer_instructions: str | None
    rejected: list[RejectedInstruction]
    not_understood: bool


# ----------------------------------------------------------------------------- reduce / materialize / verify artifacts (code-produced; OPEN_QUESTIONS #7a)
class ReduceItem(Model):
    """One surviving item after reduce (architecture §7): merged by about key, sorted, capped."""
    id: str = Field(description="stable item id; compose refers to items by this id")
    about: AboutKey
    candidate_ids: list[str]
    candidate_types: list[str] = Field(default_factory=list)
    priority: Priority
    section: Section
    due_today: bool = False
    confidence: Confidence = "medium"
    why: str = Field(default="", description="the why-now line of the highest-priority triage result")
    citations: list[Evidence] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    ambiguity: Ambiguity | None = None
    entities: list[str] = Field(default_factory=list)
    times_surfaced: int = 0
    freshness_cap: FreshnessCap = "none"


class AboutMerge(Model):
    canonical: str
    merged: list[str]
    reason: str = Field(default="", description="fuzzy-ratio | shared-entity-and-evidence")


class ReduceResult(Model):
    items: list[ReduceItem]
    overflow: list[str] = Field(default_factory=list, description="item ids beyond K, rendered as 'Also pending'")
    about_merges: list[AboutMerge] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list, description="candidate ids with include == false")


class MaterializedAction(Model):
    """One rendered action block (architecture §9.3), one line of actions.jsonl."""
    item_id: str
    type: ActionType
    target: str | None = None
    recipient_name: str | None = None
    recipient_category: RelationshipHint | None = None
    brief: str = ""
    brief_assumptions: list[str] = Field(default_factory=list)
    text: str = Field(default="", description="the rendered action block as it appears in the digest")
    draft: str | None = Field(default=None, description="draft body for reply / forward_delegate / decide, else null")
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    llm: bool = Field(default=False, description="true when the materializer LLM wrote the text")


class VerifyViolation(Model):
    rule: int = Field(description="architecture §8 rule number, 1–11")
    item_id: str | None = None
    detail: str
    fix: Literal["fixed", "dropped", "unresolved"]


class VerifyStats(Model):
    words: int = 0
    budget: int = 0
    header_present: bool = False
    items: int = 0
    items_cited: int = 0
    citations_total: int = 0
    citations_resolved: int = 0


class VerifyResult(Model):
    violations: list[VerifyViolation] = Field(default_factory=list)
    stats: VerifyStats = Field(default_factory=VerifyStats)


class TriageBatch(Model):
    """Triage packs 5–10 candidates per call (architecture §7); one TriageResult per candidate id in the pack."""
    results: list[TriageResult]


class BaselineDigest(Model):
    """The naive one-call baseline (eval.md §8) returns the whole digest as markdown."""
    markdown: str = Field(description="the complete digest in the default format, with citations")


LLM_OUTPUT_MODELS: dict[str, type[Model]] = {
    "ExtractorOutput": ExtractorOutput,
    "TriageResult": TriageResult,
    "TriageBatch": TriageBatch,
    "ReaderOutput": ReaderOutput,
    "SweepOutput": SweepOutput,
    "SignatureFacts": SignatureFacts,
    "ContactClassification": ContactClassification,
    "BaselineDigest": BaselineDigest,
    "ComposeResult": ComposeResult,
    "DraftOutput": DraftOutput,
    "DecideOutput": DecideOutput,
    "ProfileConfig": ProfileConfig,
    "CustomizeOverrides": CustomizeOverrides,
}
