"""Which rendered items (or findings) cover an expected item (OPEN_QUESTIONS #23; replaces the fuzzy key match and
the #18 "claimed key" guard).

Sources first, exactly: an expected item is covered by a rendered item that cites a source *unique* to it that day
(a source no other expected item lists). When two expected items share every source (Sam's one email backs both the
pediatrician conflict and the daycare ask), the shared-source items are ambiguous and a decider settles them: the same
linker the product uses (Jev first, the LLM when Jev is unsure), asked once per expected item per day with the
ambiguous rendered items as options. An exact key match (kind and slug equal) also counts. No string similarity.
Every decision is logged on the view (`view.coverage_log`) and summarized in the report."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from eval.manifest_schema import Manifest

from .match import about_match

_UNDECIDED = "undecided (no decider configured)"


@dataclass
class Coverage:
    linker: object | None = None          # digest.compute.linker.Linker, built lazily from config/models.yaml
    tried: bool = False
    memo: dict = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)

    def _linker(self):
        if self.tried:
            return self.linker
        self.tried = True
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DIGEST_EVAL_NO_DECIDER"):
            return None   # tests inject a stub or run strict; never a live model call from the suite
        try:
            from digest.compute.jev import JevDecider
            from digest.compute.linker import Linker
            from digest.config import load_models, load_settings
            from digest.paths import ROOT
            from digest.llm import LLM, load_api_key

            models, settings = load_models(), load_settings()
            key = load_api_key(models.provider.api_key_env)
            if not key:
                return None
            role = models.roles.get("decider")
            decider = (JevDecider(api_key=key, model=role.model, cache_dir=ROOT / settings.llm.cache_dir)
                       if role is not None and role.model and role.model.startswith("typesafe/") else None)
            self.linker = Linker(LLM(models), None, decider=decider, jev_min_p=settings.llm.jev_min_probability)
        except Exception:  # noqa: BLE001 - the grader degrades to "undecided", never crashes
            self.linker = None
        return self.linker

    def decide(self, day: int | None, about: str, expected_text: str, options: list[tuple[str, str]]) -> set[str]:
        """→ the option ids the decider says cover the expected item (at most one)."""
        key = (day, about, tuple(o[0] for o in options))
        if key in self.memo:
            return self.memo[key]
        linker = self._linker()
        if linker is None or not options:
            self.log.append({"day": day, "about": about, "options": [o[0] for o in options], "matches": [], "by": _UNDECIDED})
            self.memo[key] = set()
            return set()
        from digest.compute.linker import LinkOption, LinkQuestion

        q = LinkQuestion(id=f"x{day}", item=expected_text[:600], options=[LinkOption(id=i, text=t[:300]) for i, t in options])
        before = len(linker.log)
        ans = linker.match("covers_expected", [q]).get(q.id, [])
        by = next((e.get("by") or "llm" for e in linker.log[before:]), "llm")
        self.log.append({"day": day, "about": about, "options": [o[0] for o in options], "matches": list(ans), "by": by})
        self.memo[key] = set(ans)
        return self.memo[key]


def coverage_of(view) -> Coverage:
    cov = getattr(view, "coverage", None)
    if cov is None:
        cov = Coverage()
        view.coverage = cov
    return cov


# ----------------------------------------------------------------------------- the answer key's sources
def _day_items(manifest: Manifest, day: int | None) -> list:
    if day is None:
        return []
    try:
        rd = manifest.run_day(day)
    except KeyError:
        return []
    return list(rd.items) + ([rd.one_thing] if rd.one_thing else [])


def sources_for(manifest: Manifest, day: int | None, about: str) -> set[str]:
    return {s for ei in _day_items(manifest, day) if about_match(ei.about, about) for s in ei.cites_any}


def other_sources(manifest: Manifest, day: int | None, about: str) -> set[str]:
    return {s for ei in _day_items(manifest, day) if not about_match(ei.about, about) for s in ei.cites_any}


def other_keys(manifest: Manifest, day: int | None, about: str) -> list[str]:
    """The other expected items' keys that day. An item labeled with one of them, exactly, is that item and is never
    credited here (the old #18 guard, without the string ratio)."""
    return [ei.about for ei in _day_items(manifest, day) if not about_match(ei.about, about)]


def expected_text(manifest: Manifest, day: int | None, about: str, ctype: str | None = None) -> str:
    parts = [about] + ([f"({ctype})"] if ctype else [])
    for ei in _day_items(manifest, day):
        if about_match(ei.about, about):
            if getattr(ei, "notes", None):
                parts.append(str(ei.notes))
            acts = getattr(ei, "actions", None)
            if acts:
                parts.append("actions: " + ", ".join(acts))
    return " · ".join(parts)


# ----------------------------------------------------------------------------- items and signals
def covered_items(view, manifest: Manifest, about: str, cites_any: list[str] | None, day: int | None) -> set[str]:
    """Ids of the rendered items that cover the expected item `about` that day."""
    cov = coverage_of(view)
    cites = set(cites_any or []) or sources_for(manifest, day, about)
    unique = cites - other_sources(manifest, day, about)
    others = other_keys(manifest, day, about)
    sure: set[str] = set()
    ambiguous: list[tuple[str, str]] = []
    for it in view.rendered:
        keys = [it.about] + [a for s in view.item_signals(it) for a in s.abouts]
        if any(about_match(k, about) for k in keys):
            sure.add(it.id)
            continue
        if any(about_match(it.about, o) for o in others):
            continue
        if it.source_ids & unique:
            sure.add(it.id)
        elif it.source_ids & cites:
            ambiguous.append((it.id, f"{it.what or it.about} — {it.why or ''} [{it.section or it.placement}]"))
    if ambiguous:
        sure |= cov.decide(day, about, expected_text(manifest, day, about), ambiguous)
    return sure


def covered_signals(view, about: str, cites_any: list[str] | None, ctype: str | None = None) -> set[int]:
    """`id()`s of the findings/candidates that cover the expected item `about` (the day is the view's)."""
    manifest, day = view.index.manifest, view.day
    cov = coverage_of(view)
    cites = set(cites_any or []) or sources_for(manifest, day, about)
    unique = cites - other_sources(manifest, day, about)
    others = other_keys(manifest, day, about)
    sure: set[int] = set()
    ambiguous: list[tuple[str, str]] = []
    by_key: dict[str, int] = {}
    for s in view.signals:
        if any(about_match(a, about) for a in s.abouts):
            sure.add(id(s))
            continue
        if any(about_match(a, o) for a in s.abouts for o in others):
            continue
        if s.sources & unique:
            sure.add(id(s))
        elif s.sources & cites:
            k = f"s{id(s)}"
            by_key[k] = id(s)
            ambiguous.append((k, f"{s.title}: {s.type} [{s.origin or s.artifact}]"))
    if ambiguous:
        sure |= {by_key[k] for k in cov.decide(day, about, expected_text(manifest, day, about, ctype), ambiguous) if k in by_key}
    return sure


__all__ = ["Coverage", "coverage_of", "covered_items", "covered_signals", "expected_text", "other_keys", "other_sources", "sources_for"]
