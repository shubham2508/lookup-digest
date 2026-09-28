"""Effective facts (architecture §6.2): profile facts + drift discovered in the data, with provenance. Data wins on
facts (numbers, roles, cadences, open reqs); the profile wins on preferences."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from ..schemas import Agreement, Claim, Evidence, Extraction, Note, ProfileConfig
from ..util import fold

SUBJECT_ALIASES = {
    "arr": "ARR", "annual recurring revenue": "ARR", "revenue": "ARR", "mrr": "MRR",
    "headcount": "headcount", "team size": "headcount", "employees": "headcount",
    "runway": "runway", "burn": "burn",
    "board update cadence": "board_update_cadence", "board_update_cadence": "board_update_cadence",
    "board updates": "board_update_cadence", "board update": "board_update_cadence", "investor update cadence": "board_update_cadence",
    "open reqs": "open_reqs", "open_reqs": "open_reqs", "hiring plan": "open_reqs", "open roles": "open_reqs",
    "seed raised": "seed_raised", "seed_raised": "seed_raised", "seed round": "seed_raised",
}


def canonical_subject(subject: str) -> str:
    s = fold(subject).replace("_", " ").strip()
    s = re.sub(r"\s+", " ", s)
    for k, v in SUBJECT_ALIASES.items():
        if s == k or s.startswith(k + " ") or k in s and len(k) > 4:
            return v
    return subject.strip()


def _norm_value(v: str) -> str:
    return re.sub(r"[\s,$]", "", fold(v)).replace("~", "").replace("about", "").replace("approximately", "")


@dataclass
class DataClaim:
    subject: str
    value: str
    at: datetime | date | None
    source_id: str
    evidence: Evidence
    kind: str = "claim"           # claim | agreement
    note_kind: str | None = None  # meeting_notes | draft | ... for notes


@dataclass
class EffectiveFact:
    subject: str
    profile_value: str | None
    data_value: str | None
    effective: str | None
    drift: bool
    evidence: list[Evidence] = field(default_factory=list)
    conflicting_data: list[DataClaim] = field(default_factory=list)   # two data sources disagree (contradiction c)

    def as_drift(self) -> dict:
        return {"field": self.subject, "profile_value": self.profile_value, "data_value": self.data_value,
                "evidence": [e.model_dump(mode="json") for e in self.evidence]}


def collect_claims(extractions: list[Extraction], note_dates: dict[str, date | None]) -> list[DataClaim]:
    out: list[DataClaim] = []
    for x in extractions:
        p = x.payload
        if p is None:
            continue
        claims: list[Claim] = getattr(p, "claims", []) or []
        note_kind = p.note_kind if isinstance(p, Note) else None
        when: datetime | date | None = None
        if isinstance(p, Note):
            when = p.meeting_date or note_dates.get(x.source_id)
        elif hasattr(p, "ball"):
            when = p.ball.last_message_at
        for c in claims:
            at = c.as_of.resolved if c.as_of and c.as_of.resolved else when
            out.append(DataClaim(canonical_subject(c.subject), c.value, at, x.source_id, c.evidence, "claim", note_kind))
        agreements: list[Agreement] = getattr(p, "agreements", []) or []
        for a in agreements:
            if a.cadence and ("board" in fold(a.rule) or "investor" in fold(a.rule) or "update" in fold(a.rule)):
                out.append(DataClaim("board_update_cadence", a.cadence, when, x.source_id, a.evidence, "agreement", note_kind))
    return out


def _sort_key(c: DataClaim) -> tuple:
    when = c.at
    if isinstance(when, datetime):
        when = when.date()
    return (when or date.min, 0 if c.note_kind == "draft" else 1)


def effective_facts(profile: ProfileConfig, claims: list[DataClaim]) -> list[EffectiveFact]:
    prof = {canonical_subject(f.subject): f.value for f in profile.facts}
    by_subject: dict[str, list[DataClaim]] = {}
    for c in claims:
        by_subject.setdefault(c.subject, []).append(c)
    out: list[EffectiveFact] = []
    for subject in sorted(set(prof) | set(by_subject)):
        pv = prof.get(subject)
        data = sorted(by_subject.get(subject, []), key=_sort_key)
        if not data:
            out.append(EffectiveFact(subject, pv, None, pv, False))
            continue
        latest = data[-1]
        distinct = {}
        for c in data:
            distinct.setdefault(_norm_value(c.value), c)
        conflicting = list(distinct.values()) if len(distinct) > 1 else []
        drift = pv is not None and _norm_value(pv) != _norm_value(latest.value)
        out.append(EffectiveFact(subject, pv, latest.value, latest.value, drift, [latest.evidence], conflicting))
    return out
