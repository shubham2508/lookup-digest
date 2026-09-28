"""The answer key: eval/manifests/<world>.yaml (extraction_schema §7, data_generation §4, eval.md §2–§7).

Owned by the orchestrator. Track B emits it, Track C scores against it. The digest never reads it.

Shape
- meta:        world, anchor (date of day 30), run days, as-of time.
- items:       one per source document (thread / note / task / newsletter / automated / marketing) with its
               background category, must-not flag, storyline tag, and the expected extraction (§7).
- contacts:    truth per person: category, subtype, tier, stage timeline.
- about_keys:  pairs that should / should not merge (architecture §6.3 accuracy metric).
- run_days:    per run day: expected candidates (compute), expected digest items (triage + compose), absent
               keys, the one thing, and labeled noise that must not appear.
- assertions:  trap assertions (eval.md §3, §5, §6, §7), each a kind + args the scorer knows how to check.
- variants:    storyline variants (data_dir) and honesty variants (run conditions) with their own expectations.
- sim_avery:   intended answers to question cards, by scope.
- label_audit: Shubham's hand-check record (eval.md §9.5).

Days are world-relative (1..30); the scorer converts with meta.anchor. Times are "HH:MM" in PT.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digest.schemas import (
    AboutKey,
    ActionType,
    AmbiguityType,
    AskKind,
    AutomatedActionKind,
    CandidateType,
    DocType,
    Domain,
    Intent,
    NoteKind,
    Priority,
    RelationshipHint,
    Section,
)

ItemKind = Literal["thread", "note", "task", "newsletter", "automated", "marketing"]
BackgroundCategory = Literal[
    "internal_routine", "notifications", "newsletters", "customers", "saas_marketing", "investors_board",
    "recruiters", "vendors_misc", "hiring", "lawyer", "personal",
]
VariantKind = Literal["storyline", "honesty"]

# eval.md §3, §5, §6, §7 — what the scorer must be able to check. `args` documents each kind.
AssertionKind = Literal[
    "item_present",            # about (+ priority?, section?, actions_any?, storyline?)
    "item_absent",             # about | source_id
    "one_thing",               # about, cites_any: [source ids]
    "priority_is",             # about, priority
    "priority_not",            # about, priority
    "section_is",              # about, section
    "action_present",          # about, action
    "action_absent",           # about, action
    "item_mentions_all",       # about, phrases: [..]   (S2: both dates)
    "draft_contains",          # about | recipient, phrases
    "draft_not_contains",      # about | recipient, phrases
    "no_draft_to",             # contact (email or name)   (S11, recruiters)
    "contact_category_is",     # email, category (+ subtype?)
    "contact_tier_is",         # email, tier
    "candidate_present",       # type, about?
    "candidate_absent",        # type, about?
    "count_items_of_type",     # type, equals | max
    "header_contains",         # phrases
    "confidence_max",          # type | about, max: low|medium
    "item_qualified_with",     # type | about, phrase ("may be a sync gap")
    "no_candidates_of_type",   # type
    "word_count_max",          # max (excl. header and action blocks)
    "sections_only",           # sections: [..]  (weekend mode: only P0/family)
    "priorities_only",         # priorities: [..]
    "citations_present",       # every rendered item has ≥1 citation
    "customize_rejected_noted",# instruction substring
    "customize_not_understood",# header says so
    "ruling_applied",          # question_id | scope, expected change (next run)
    "escalation_framing",      # about, min_times_surfaced
    "resolved_disappears",     # about, after_run_day
    "content_overrides_ruling",# about
    "injection_not_acted",     # source_id, forbidden_actions: [..]
]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(M):
    world: str
    anchor: date = Field(description="date of day 30 (a Thursday)")
    timezone: str = "America/Los_Angeles"
    run_days: list[int] = Field(default_factory=lambda: [26, 27, 28, 29, 30])
    as_of_time: str = "06:00"
    seed: int = 7
    generator: str = "claude-code-session"
    generated_at: str | None = None
    counts: dict[str, int] = Field(default_factory=dict, description="emails per category, notes, tasks, events")

    def day_to_date(self, day: int) -> date:
        return self.anchor - timedelta(days=30 - day)


class MessageLabel(M):
    message_id: str
    day: int
    time: str = Field(description="HH:MM PT")
    from_email: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    beat_ref: str | None = Field(default=None, description="storyline beat this message renders, e.g. S1.b3")
    must_include: list[str] = Field(default_factory=list)
    is_from_avery: bool = False


class ExpectedCommitment(M):
    owner: Literal["avery", "other"]
    about: AboutKey
    due_day: int | None = None
    due_time: str | None = None
    status_in_thread: Literal["open", "fulfilled", "cancelled", "superseded"] = "open"
    fulfilled_by_source: str | None = Field(default=None, description="source id that fulfils it (cross-thread, S16)")


class ExpectedAsk(M):
    to_avery: bool = True
    kind: AskKind
    deadline_day: int | None = None
    status: Literal["open", "answered", "withdrawn"] = "open"


class ExpectedScheduleMention(M):
    action: Literal["proposed", "confirmed", "moved", "cancelled"]
    participants: list[str] = Field(default_factory=list)
    when_day: int | None = None
    when_time: str | None = None
    previous_when_day: int | None = None


class ExpectedStageSignal(M):
    entity: str
    stage: str
    day: int


class ExpectedRoleChange(M):
    person: str
    replaces: str | None = None
    org: str | None = None
    day: int


class ExpectedClaim(M):
    subject: str
    value: str


class ExpectedNewsItem(M):
    headline_hint: str
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    attaches_to: list[AboutKey] = Field(default_factory=list, description="empty = decoy, must not attach")


class ExpectedAgreement(M):
    rule: str
    cadence: str | None = None


class ExpectedAutomated(M):
    system: str
    action_bearing: bool
    action_kind: AutomatedActionKind
    about: AboutKey | None = None


class ExpectedSenderRelationship(M):
    category: RelationshipHint
    subtype: str | None = None
    stage: str | None = None


class ExpectedExtraction(M):
    """Shaped like the extraction (extraction_schema §7) so the scorer can match field by field."""
    type: DocType
    domain: Domain | None = None
    intent_primary: Intent | None = None
    about: list[AboutKey] = Field(default_factory=list)
    ball_awaiting: Literal["avery", "other", "nobody", "unclear"] | None = None
    closed_by_courtesy: bool | None = None
    sender_relationship: ExpectedSenderRelationship | None = None
    commitments: list[ExpectedCommitment] = Field(default_factory=list)
    asks: list[ExpectedAsk] = Field(default_factory=list)
    schedule_mentions: list[ExpectedScheduleMention] = Field(default_factory=list)
    stage_signals: list[ExpectedStageSignal] = Field(default_factory=list)
    role_changes: list[ExpectedRoleChange] = Field(default_factory=list)
    claims: list[ExpectedClaim] = Field(default_factory=list)
    suspicious: bool = False
    news_items: list[ExpectedNewsItem] = Field(default_factory=list)
    note_kind: NoteKind | None = None
    agreements: list[ExpectedAgreement] = Field(default_factory=list)
    draft_of: str | None = None
    automated: ExpectedAutomated | None = None


class ItemLabel(M):
    source_id: str = Field(description="thread id | note path | task id — what the digest will cite")
    kind: ItemKind
    category: BackgroundCategory | None = Field(default=None, description="background category; null for notes/tasks")
    storyline: str | None = Field(default=None, description="S1..S16 or a background mini-arc id")
    must_not_surface: bool = False
    must_not_reason: str | None = Field(default=None, description="why it is noise: fyi, last_word_avery, marketing, ...")
    classification_case: str | None = Field(default=None, description="data_generation §6 classification case tag")
    expected: ExpectedExtraction | None = None
    messages: list[MessageLabel] = Field(default_factory=list)


class StageAt(M):
    from_day: int
    stage: str


class ContactLabel(M):
    email: str
    name: str
    org: str | None = None
    title: str | None = None
    category: RelationshipHint
    subtype: str | None = None
    tier: Priority | None = Field(default=None, description="effective tier; None for noise senders")
    rules: list[str] = Field(default_factory=list)
    stages: list[StageAt] = Field(default_factory=list)
    replaces: str | None = Field(default=None, description="email of the predecessor (handover, S7)")
    in_profile: bool = False


class AboutKeyMerges(M):
    should_merge: list[tuple[str, str]] = Field(default_factory=list)
    should_not_merge: list[tuple[str, str]] = Field(default_factory=list)


class ExpectedCandidate(M):
    type: CandidateType
    about: AboutKey
    storyline: str | None = None
    facts_hint: dict[str, str | int | float | bool] = Field(default_factory=dict, description="e.g. business_days_quiet: 3")


class ExpectedItem(M):
    about: AboutKey
    include: bool = True
    priority: Priority | None = None
    priority_band: list[Priority] = Field(default_factory=list, description="acceptable priorities if not exact")
    section: Section | None = None
    actions: list[ActionType] = Field(default_factory=list, description="expected action types (any order)")
    cites_any: list[str] = Field(default_factory=list, description="source ids; at least one must be cited")
    one_thing: bool = False
    ambiguity: AmbiguityType | None = None
    storyline: str | None = None
    notes: str | None = None


class OneThing(M):
    about: AboutKey
    cites_any: list[str] = Field(default_factory=list)


class RunDayExpectation(M):
    run_day: int
    candidates: list[ExpectedCandidate] = Field(default_factory=list)
    items: list[ExpectedItem] = Field(default_factory=list)
    absent: list[AboutKey] = Field(default_factory=list)
    one_thing: OneThing | None = None
    noise_source_ids: list[str] = Field(default_factory=list, description="labeled must-not items that must not appear")


class Assertion(M):
    id: str
    kind: AssertionKind
    run_day: int | None = None
    variant: str | None = None
    customize: str | None = None
    storyline: str | None = None
    args: dict[str, object] = Field(default_factory=dict)
    description: str | None = None


class SimAveryAnswer(M):
    scope_about: AboutKey | None = None
    scope_contact: str | None = None
    scope_thread_kind: str | None = None
    intended_option: int = Field(description="1-based")
    rationale: str | None = None


class Variant(M):
    id: str
    kind: VariantKind
    data_dir: str | None = Field(default=None, description="storyline variants render to data/<world>__<id>/")
    condition: dict[str, object] = Field(default_factory=dict, description="honesty variants: e.g. {inbox_cutoff_hours: 30}")
    run_days: list[RunDayExpectation] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)


class LabelAudit(M):
    sample_size: int = 0
    checked_by: str | None = None
    checked_on: date | None = None
    corrections: list[str] = Field(default_factory=list)


class Manifest(M):
    meta: Meta
    items: list[ItemLabel] = Field(default_factory=list)
    contacts: list[ContactLabel] = Field(default_factory=list)
    about_keys: AboutKeyMerges = Field(default_factory=AboutKeyMerges)
    run_days: list[RunDayExpectation] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)
    variants: list[Variant] = Field(default_factory=list)
    sim_avery: list[SimAveryAnswer] = Field(default_factory=list)
    label_audit: LabelAudit = Field(default_factory=LabelAudit)

    @model_validator(mode="after")
    def _consistent(self) -> Manifest:
        ids = [i.source_id for i in self.items]
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        if dupes:
            raise ValueError(f"duplicate item source_ids: {dupes}")
        known = set(ids)
        for rd in self.run_days:
            for sid in rd.noise_source_ids:
                if sid not in known:
                    raise ValueError(f"run_day {rd.run_day}: noise_source_id {sid!r} is not an item")
        aids = [a.id for a in self.assertions]
        if len(aids) != len(set(aids)):
            raise ValueError("duplicate assertion ids")
        return self

    def item(self, source_id: str) -> ItemLabel:
        for i in self.items:
            if i.source_id == source_id:
                return i
        raise KeyError(source_id)

    def run_day(self, day: int) -> RunDayExpectation:
        for rd in self.run_days:
            if rd.run_day == day:
                return rd
        raise KeyError(day)


def load_manifest(path) -> Manifest:
    import yaml

    with open(path, encoding="utf-8") as f:
        return Manifest.model_validate(yaml.safe_load(f))
