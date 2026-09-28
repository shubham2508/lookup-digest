"""Field-level diff of the compiled profile.yaml against eval/expected/profile.yaml (specs/prompts.md P1 eval).

Structured fields are compared exactly (contacts by name or role, facts by subject, thresholds, blocks, windows,
hard rules). Rule tags are compared only for the machine-checkable ones. Prose lists (judgment_rules, digest_prefs,
tone) are scored by coverage: an expected snippet counts if some compiled snippet contains it (normalized).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .match import norm_text

CHECKED_RULES = {"never_draft", "same_day_reply", "email_means_intentional", "pattern_only"}
CONTACT_FIELDS = ("category", "subtype", "tier")


@dataclass
class ProfileDiff:
    checked: int = 0
    matched: int = 0
    diffs: list[str] = field(default_factory=list)
    coverage: dict[str, float] = field(default_factory=dict)

    @property
    def accuracy(self) -> float | None:
        return round(self.matched / self.checked, 3) if self.checked else None

    def check(self, where: str, expected: Any, got: Any) -> None:
        self.checked += 1
        if expected == got:
            self.matched += 1
        else:
            self.diffs.append(f"{where}: expected {expected!r}, got {got!r}")


def _contact_key(c: dict) -> str:
    if c.get("name"):
        return norm_text(c["name"])
    rao = c.get("role_at_org") or {}
    return "role:" + norm_text(rao.get("role", ""))


def diff_profile(expected: dict, actual: dict) -> ProfileDiff:
    d = ProfileDiff()
    for k in ("person", "timezone"):
        d.check(k, expected.get(k), actual.get(k))

    got_contacts = {_contact_key(c): c for c in actual.get("contacts", [])}
    for ec in expected.get("contacts", []):
        key = _contact_key(ec)
        gc = got_contacts.get(key)
        if gc is None and key.startswith("role:"):  # role wording varies ("procurement leads"): match on orgs
            orgs = {norm_text(o) for o in (ec.get("role_at_org") or {}).get("orgs", [])}
            gc = next((c for c in actual.get("contacts", []) if orgs and orgs == {norm_text(o) for o in
                       (c.get("role_at_org") or {}).get("orgs", [])}), None)
        if gc is None:
            d.check(f"contact {key}", "present", "missing")
            continue
        for f in CONTACT_FIELDS:
            d.check(f"contact {key}.{f}", ec.get(f), gc.get(f))
        d.check(f"contact {key}.rules", sorted(set(ec.get("rules", [])) & CHECKED_RULES),
                sorted(set(gc.get("rules", [])) & CHECKED_RULES))
        if ec.get("role_at_org"):
            d.check(f"contact {key}.orgs", sorted(map(norm_text, ec["role_at_org"].get("orgs", []))),
                    sorted(map(norm_text, (gc.get("role_at_org") or {}).get("orgs", []))))

    got_facts = {norm_text(f["subject"]): norm_text(f["value"]) for f in actual.get("facts", [])}
    for ef in expected.get("facts", []):
        s = norm_text(ef["subject"])
        got = got_facts.get(s)
        d.check(f"fact {ef['subject']}", True, got is not None and norm_text(ef["value"]) in got)

    et, gt = expected.get("thresholds", {}), actual.get("thresholds") or {}
    for k in ("investor_quiet_business_days", "hiring_stall_days", "recruiter_pattern"):
        d.check(f"thresholds.{k}", et.get(k), gt.get(k))
    norm_blocks = lambda bs: sorted((tuple(sorted(b["days"])), b["start"], b["end"]) for b in bs)  # noqa: E731
    d.check("blocks", norm_blocks(expected.get("blocks", [])), norm_blocks(actual.get("blocks", [])))
    d.check("read_windows", len(expected.get("read_windows", [])), len(actual.get("read_windows", [])))
    eh, gh = expected.get("hard_rules", {}), actual.get("hard_rules") or {}
    for k in ("no_newsletter_items", "recruiter_pattern_only", "cite_everything", "flag_stale_email_hours"):
        d.check(f"hard_rules.{k}", eh.get(k), gh.get(k))
    d.check("hard_rules.never_draft_for", sorted(map(norm_text, eh.get("never_draft_for", []))),
            sorted(map(norm_text, gh.get("never_draft_for", []))))

    for k in ("judgment_rules", "digest_prefs", "tone"):
        exp = [norm_text(x) for x in expected.get(k, [])]
        got = " || ".join(norm_text(x) for x in actual.get(k, []))
        hit = sum(1 for x in exp if x in got)
        d.coverage[k] = round(hit / len(exp), 3) if exp else 1.0
    topics_e = {norm_text(t) for t in expected.get("standing_topics", [])}
    topics_g = {norm_text(t) for t in actual.get("standing_topics", [])}
    d.coverage["standing_topics"] = round(len(topics_e & topics_g) / len(topics_e), 3) if topics_e else 1.0
    return d
