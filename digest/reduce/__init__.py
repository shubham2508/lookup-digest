"""Reduce (architecture §7, code): drop include=false, merge by about key, sort, cap at K, every P0 survives."""
from __future__ import annotations

from datetime import datetime

from ..compute import ComputeResult
from ..schemas import (
    AboutMerge,
    Ambiguity,
    Candidate,
    Evidence,
    ProposedAction,
    ReduceItem,
    ReduceResult,
    TriageResult,
)

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
CATEGORY_PRIOR = {"family": 0, "capital": 1, "customer": 2, "team": 3, "hiring": 4, "legal_gov": 4, "vendor": 5,
                  "network": 5, "external_visibility": 6, "automated": 7, "unresolved": 7, "cold_inbound": 8}
TIER_PRIOR = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, None: 4}
FRESH_ORDER = {"none": 0, "stale": 1, "missing": 2}


def _deadline(c: Candidate, tzinfo) -> datetime | None:
    for k in ("deadline", "due", "start", "answer_was_due"):
        v = c.facts.get(k)
        if isinstance(v, str):
            try:
                d = datetime.fromisoformat(v)
            except ValueError:
                continue
            return d if d.tzinfo else d.replace(tzinfo=tzinfo)
    return None


def _tier_prior(item_entities: list[str], compute: ComputeResult) -> tuple[int, int]:
    tiers, cats = [], []
    for e in item_entities:
        c = compute.directory.by_slug.get(e)
        if c:
            tiers.append(TIER_PRIOR.get(c.tier, 4))
            cats.append(CATEGORY_PRIOR.get(c.relationship.category, 7))
    return (min(tiers) if tiers else 4, min(cats) if cats else 7)


def _cap_confidence(conf: str, cap: str) -> str:
    """DESIGN_LOG §4.4: a conclusion resting on a stale or missing source is at most medium confidence."""
    return "medium" if cap != "none" and conf == "high" else conf


def join_keys(c: Candidate) -> list[tuple]:
    """Two candidates are one item when a key matches. A qualified about key (deal:series-a:cap-table) joins across
    threads; a shared citation (same message, same quote) joins within one. v1 rule candidates (no `origin`) and safety
    nets still join by thread (reply owed + gone quiet on one email are one item); reader findings do not, because a
    reader splits one thread into separate issues on purpose (PIVOT_SPEC §5.4)."""
    keys: list[tuple] = []
    if c.about.count(":") >= 2:
        keys.append(("about", c.about))
    for e in c.evidence:
        keys.append(("cite", e.source_id, e.quote))
    if c.facts.get("thread_id") and c.facts.get("origin") in (None, "safety_net"):
        keys.append(("thread", str(c.facts["thread_id"])))
    if not keys:
        keys.append(("about", c.about))
    return keys


def reduce_items(results: list[TriageResult], cands: list[Candidate], compute: ComputeResult, k_cap: int,
                 about_merges: list[AboutMerge] | None = None) -> ReduceResult:
    by_id = {c.candidate_id: c for c in cands}
    kept = [r for r in results if r.include and r.candidate_id in by_id]
    dropped = [r.candidate_id for r in results if not r.include]
    # One item per underlying thing (architecture §7 merges by about key). Two candidates are the same thing when
    # they share a qualified about key (deal:series-a:cap-table, across threads) or come from the same source thread
    # (reply owed + gone quiet + promise overdue on one email thread are one item, not three). A coarse key
    # (deal:series-a) names a whole area, so it alone never joins different threads.
    parent = {r.candidate_id: r.candidate_id for r in kept}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # the linker's about merges (compute) join whatever keys they name, coarse or not (OPEN_QUESTIONS #22h)
    merge_group: dict[str, int] = {}
    for n, m in enumerate(about_merges or []):
        for k in (m.canonical, *m.merged):
            merge_group[k] = n
    first_by: dict[tuple, str] = {}
    for r in kept:
        c = by_id[r.candidate_id]
        keys = join_keys(c)
        if c.facts.get("origin"):   # v2 finding: the same tag on two threads that share a person is one thing (#22h)
            keys += [("about-entity", c.about, e) for e in c.entities if e]
        if c.about in merge_group:
            keys.append(("merge", merge_group[c.about]))
        for k in keys:
            if k in first_by:
                join(first_by[k], r.candidate_id)
            else:
                first_by[k] = r.candidate_id
    groups_by_root: dict[str, list[TriageResult]] = {}
    for r in kept:
        groups_by_root.setdefault(find(r.candidate_id), []).append(r)

    def _item_about(rs: list[TriageResult]) -> str:
        cs = [by_id[r.candidate_id] for r in rs]
        top = min(rs, key=lambda r: (PRIORITY_ORDER[r.priority], not r.due_today))
        # the most specific key among the merged candidates, preferring the top-priority one's
        return max((c.about for c in cs), key=lambda a: (a == by_id[top.candidate_id].about, a.count(":"), len(a)))

    groups = {(_item_about(rs), root): rs for root, rs in groups_by_root.items()}
    items: list[tuple[ReduceItem, tuple]] = []
    for (about, _root), rs in groups.items():
        rs.sort(key=lambda r: (PRIORITY_ORDER[r.priority], not r.due_today, CONFIDENCE_ORDER[r.confidence]))
        top = rs[0]
        cs = [by_id[r.candidate_id] for r in rs]
        cits: list[Evidence] = []
        acts: list[ProposedAction] = []
        seen_acts: set[tuple] = set()
        amb: Ambiguity | None = None
        for r in rs:
            for e in r.citations:
                if e not in cits:
                    cits.append(e)
            for a in r.proposed_actions:
                key = (a.type, (a.target or "").lower())
                if key not in seen_acts:
                    seen_acts.add(key)
                    acts.append(a)
            if amb is None and r.ambiguity is not None:
                amb = r.ambiguity
        ents: list[str] = []
        for c in cs:
            for e in c.entities:
                if e and e not in ents:
                    ents.append(e)
        deadlines = [d for d in (_deadline(c, compute.context.as_of.tzinfo) for c in cs) if d]
        item = ReduceItem(
            id="", about=about, candidate_ids=[r.candidate_id for r in rs], candidate_types=[by_id[r.candidate_id].type for r in rs],
            priority=top.priority, section=top.section, due_today=any(r.due_today for r in rs),
            confidence=_cap_confidence(min((r.confidence for r in rs), key=lambda x: CONFIDENCE_ORDER[x]),
                                       max((c.freshness_cap for c in cs), key=lambda x: FRESH_ORDER[x])), why=top.why, citations=cits[:6],
            proposed_actions=acts, ambiguity=amb, entities=ents, times_surfaced=max(c.times_surfaced for c in cs),
            freshness_cap=max((c.freshness_cap for c in cs), key=lambda x: FRESH_ORDER[x]),
        )
        tier, cat = _tier_prior(ents, compute)
        key = (PRIORITY_ORDER[item.priority], not item.due_today, tier, cat, min(deadlines) if deadlines else datetime.max.replace(tzinfo=compute.context.as_of.tzinfo),
               CONFIDENCE_ORDER[item.confidence], about)
        items.append((item, key))
    items.sort(key=lambda x: x[1])
    ordered = [it for it, _ in items]
    for i, it in enumerate(ordered, 1):
        it.id = f"i{i}"
    survivors = ordered[:k_cap]
    overflow = ordered[k_cap:]
    for it in list(overflow):            # every P0 survives the cap
        if it.priority == "P0":
            overflow.remove(it)
            bump = next((s for s in reversed(survivors) if s.priority != "P0"), None)
            if bump is not None:
                survivors.remove(bump)
                overflow.insert(0, bump)
            survivors.append(it)
    survivors.sort(key=lambda it: int(it.id[1:]))
    return ReduceResult(items=survivors, overflow=[it.id for it in overflow], about_merges=list(about_merges or []), dropped=dropped,
                        ) if not overflow else ReduceResult(items=survivors + overflow, overflow=[it.id for it in overflow],
                                                            about_merges=list(about_merges or []), dropped=dropped)


__all__ = ["PRIORITY_ORDER", "CATEGORY_PRIOR", "reduce_items"]
