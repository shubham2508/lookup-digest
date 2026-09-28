"""Run conditions (M7): honesty variants (eval.md §5), storyline variants, customize suite (§6).

Each condition is scored as its own row: the runs found for it, digest-level headline numbers (P0 recall stays
meaningful under every condition: P0 items may never be silently hidden, architecture §5.2), its assertions
(manifest + the built-in suites `eval/variant_suite.yaml` and `eval/customize_suite.yaml`), and condition checks:

- `formal` customize: drafts change tone vs the default run of the same day (paired by item about + action type).
  Code heuristic, reported next to the judge's tone score, never gated.
- every customize run: `p0_kept`: each expected P0 the default run rendered is still rendered (a P0 hidden by a
  filter is a failure); absolute P0 recall is reported too.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from digest.paths import PROFILE_DIR
from eval.manifest_schema import Assertion, Manifest

from .artifacts import RunView
from .assertions import AssertionResult, CheckContext, run_assertions
from .match import about_match

EVAL_DIR = Path(__file__).resolve().parents[1]
VARIANT_SUITE = EVAL_DIR / "variant_suite.yaml"
CUSTOMIZE_SUITE = EVAL_DIR / "customize_suite.yaml"
CUSTOMIZE_DIR = PROFILE_DIR / "customize"
BUILTIN_VARIANTS = {"tasks_stale", "tasks_stale_builtin"}  # conditions of the world itself, scored on the default runs
CONTRACTION_RE = re.compile(r"\b\w+(n't|'re|'ll|'ve|'m|'d)\b", re.I)
FORMAL_SIGNOFF_RE = re.compile(r"\b(best regards|kind regards|regards|sincerely|best|thank you)\b", re.I)


@dataclass
class ConditionScore:
    kind: str  # honesty | storyline | customize
    id: str
    suffix: str | None
    runs_root: str
    days: list[int]
    headline: dict
    assertions: list[AssertionResult]
    checks: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.days:
            return "not run"
        failed = [a for a in self.assertions if a.passed is False]
        # P0 recall is reported for every condition but gates only storyline variants (their own expectations).
        # Honesty variants withhold data on purpose (a corrupt calendar can't surface a calendar conflict), and
        # customize is gated by `p0_kept` (relative to the default run) in checks, so base misses aren't double-counted.
        gate = self.headline.get("p0_gate") if self.kind == "storyline" else None
        return "fail" if failed or gate is False or self.checks.get("passed") is False else "pass"


def _load_suite(path: Path) -> list[Assertion]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Assertion.model_validate(a) for a in data.get("assertions", [])]


def condition_assertions(manifest: Manifest, kind: str, cid: str, customize_suite: bool = True) -> list[Assertion]:
    if kind == "customize":
        out = [a for a in manifest.assertions if a.customize == cid]
        out += [a for a in _load_suite(CUSTOMIZE_SUITE) if a.customize == cid] if customize_suite else []
        return out
    out = [a for a in manifest.assertions if a.variant == cid]
    out += [a for v in manifest.variants if v.id == cid for a in v.assertions]
    if kind == "honesty":
        out += [a for a in _load_suite(VARIANT_SUITE) if a.variant == cid]
    return out


def honesty_ids(manifest: Manifest) -> list[str]:
    ids = [v.id for v in manifest.variants if v.kind == "honesty"]
    ids += [a.variant for a in _load_suite(VARIANT_SUITE) if a.variant]
    ids += [a.variant for a in manifest.assertions if a.variant and a.variant not in {v.id for v in manifest.variants if v.kind == "storyline"}]
    return list(dict.fromkeys(ids))


def customize_ids(manifest: Manifest, customize_suite: bool) -> list[str]:
    ids = [a.customize for a in manifest.assertions if a.customize]
    if customize_suite:
        ids += sorted(p.stem for p in CUSTOMIZE_DIR.glob("*.md"))
        ids += [a.customize for a in _load_suite(CUSTOMIZE_SUITE) if a.customize]
    return list(dict.fromkeys(ids))


# ----------------------------------------------------------------------------- tone (formal.md)
def formality(text: str) -> float:
    """0..1: capitalized opening, no contractions, a conventional sign-off. A crude, transparent proxy."""
    t = (text or "").strip()
    if not t:
        return 0.0
    tail = " ".join(t.splitlines()[-2:]) if "\n" in t else t[-40:]  # "Best regards,\nAvery"
    marks = [t[0].isupper(), not CONTRACTION_RE.search(t), bool(FORMAL_SIGNOFF_RE.search(tail))]
    return round(sum(marks) / len(marks), 3)


def tone_shift(default: RunView, custom: RunView) -> dict:
    pairs = []
    for d in custom.drafts():
        it = custom.rendered_by_id(d.get("item_id"))
        for b in default.drafts():
            bit = default.rendered_by_id(b.get("item_id"))
            if b.get("type") == d.get("type") and it and bit and about_match(it.about, bit.about):
                pairs.append((b.get("draft", ""), d.get("draft", "")))
                break
    if not pairs:
        return {"pairs": 0, "passed": None, "note": "no draft pairs to compare"}
    before = sum(formality(b) for b, _ in pairs) / len(pairs)
    after = sum(formality(a) for _, a in pairs) / len(pairs)
    changed = sum(1 for b, a in pairs if b.strip() != a.strip()) / len(pairs)
    return {"pairs": len(pairs), "formality_default": round(before, 3), "formality_customize": round(after, 3),
            "changed_rate": round(changed, 3), "passed": after > before and changed >= 0.5}


# ----------------------------------------------------------------------------- locked invariant: P0 never hidden
def p0_kept(manifest: Manifest, default_views: dict[int, RunView], views: dict[int, RunView]) -> dict:
    """Expected P0 items the default digest rendered must still appear (item, one-liner, 'Also outside your filter')
    under customize (architecture §5.2). Measured against the default run, so pipeline misses are not counted twice."""
    from .common import select_items
    from .digest_metrics import expected_p0

    kept = total = 0
    lost = []
    for day, v in views.items():
        dv = default_views.get(day)
        if dv is None:
            continue
        for ei in expected_p0(manifest, day):
            if select_items(dv, manifest, {"about": ei.about}, ei.cites_any):
                total += 1
                if select_items(v, manifest, {"about": ei.about}, ei.cites_any):
                    kept += 1
                else:
                    lost.append(f"d{day}:{ei.about}")
    if not total:
        return {"compared": 0, "passed": None}
    return {"kept": f"{kept}/{total}", "lost": lost or "none", "passed": kept == total}


# ----------------------------------------------------------------------------- scoring
def _score(manifest: Manifest, kind: str, cid: str, suffix: str | None, root: Path, default_views: dict[int, RunView],
           assertions: list[Assertion]) -> ConditionScore:
    from .runner import headline_of, load_views, score_run

    views = default_views if suffix is None and root is None else load_views(manifest, root, suffix)
    runs = {d: score_run(v, manifest, d, digest_only=True) for d, v in sorted(views.items())}
    results = run_assertions(assertions, CheckContext(manifest, views))
    cs = ConditionScore(kind=kind, id=cid, suffix=suffix, runs_root=str(root), days=sorted(views),
                        headline=headline_of(runs, results), assertions=results)
    if kind == "customize" and views:
        cs.checks["p0_kept"] = p0_kept(manifest, default_views, views)
        cs.checks["passed"] = cs.checks["p0_kept"].get("passed")
    if kind == "customize" and cid == "formal" and views:
        day = max(views)
        if day in default_views:
            cs.checks["tone_shift"] = tone_shift(default_views[day], views[day])
            if cs.checks.get("passed") is not False:
                cs.checks["passed"] = cs.checks["tone_shift"].get("passed")
        else:
            cs.notes.append(f"no default run on day {day} to compare tone against")
    if not views:
        cs.notes.append(f"no runs under {root} with suffix {suffix!r}")
    return cs


def variant_manifest(manifest: Manifest, vid: str) -> Manifest:
    """The manifest with a storyline variant's run-day expectations swapped in (e.g. S1 `fulfilled`: cap table absent)."""
    v = next(x for x in manifest.variants if x.id == vid)
    if not v.run_days:
        return manifest
    m = manifest.model_copy(deep=True)
    by_day = {rd.run_day: rd for rd in v.run_days}
    m.run_days = [by_day.pop(rd.run_day, rd) for rd in m.run_days] + list(by_day.values())
    return m


def score_conditions(manifest: Manifest, runs_root: Path, default_views: dict[int, RunView],
                     customize_suite: bool = False) -> list[ConditionScore]:
    declared = {v.id for v in manifest.variants}
    out: list[ConditionScore] = []
    for cid in honesty_ids(manifest):
        if cid in BUILTIN_VARIANTS:
            if cid not in declared:
                continue  # the world does not plant it (e.g. the mini fixture)
            out.append(_score(manifest, "honesty", cid, None, None, default_views,
                              condition_assertions(manifest, "honesty", cid)))
            out[-1].notes.append("built into the world: scored on the default runs")
            continue
        out.append(_score(manifest, "honesty", cid, cid, runs_root, default_views,
                          condition_assertions(manifest, "honesty", cid)))
    for v in manifest.variants:
        if v.kind == "storyline":
            root = runs_root.parent / f"{runs_root.name}__{v.id}"
            out.append(_score(variant_manifest(manifest, v.id), "storyline", v.id, None, root, default_views,
                              condition_assertions(manifest, "storyline", v.id)))
    for stem in customize_ids(manifest, customize_suite):
        out.append(_score(manifest, "customize", stem, f"customize-{stem}", runs_root, default_views,
                          condition_assertions(manifest, "customize", stem, customize_suite)))
    return out
