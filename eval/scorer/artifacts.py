"""Load one run's artifacts (digest/runs.py ARTIFACTS) and build the scorer's view of what the digest showed.

This is the only module that knows artifact shapes: `digest/schemas.py` pins them all (ReduceResult,
MaterializedAction, VerifyResult since OPEN_QUESTIONS #7a). The reader stays tolerant of missing files and keys, so
a run that crashed half-way is still scored (a missing artifact becomes a miss attributed to its stage).

Item ids in compose.json are reduce ids; if reduce.json is absent, they are looked up as candidate ids. A run with
a digest.md but no compose.json (the naive baseline, eval.md §8) is scored from the markdown alone
(`markdown_view.py`).

v2 (PIVOT_SPEC §4): `findings.jsonl` holds every Finding (readers, sweeps, safety nets, including `needs_avery: no`)
plus the code-set `candidate_id`, `thread_id`, `rescued_by_safety_net`. Each finding becomes a `Signal`, the unit
the diagnostics, the candidate-kind assertions and attribution match on; a candidate with no finding behind it (a
run without findings.jsonl) becomes a Signal too, so older fixtures still score.
"""
from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from digest.findings import about_key
from digest.runs import ARTIFACTS

from .digest_md import ParsedDigest, parse_digest
from .match import SourceIndex, evidence_refs, majority_source, max_priority

OPTIONAL_ARTIFACTS = {"trace", "links", "extractions"}  # trace: debug only; extractions: v1 only (gone in v2)
DRAFT_TYPES = ("reply", "forward_delegate", "decide", "message_person")
# the stage a finding's origin belongs to (attribution chain read → sweep → net → merge → compose → materialize → verify)
ORIGIN_STAGE = {"thread_reader": "read", "calendar_sweep": "sweep", "notes_tasks_sweep": "sweep", "news_sweep": "sweep",
                "safety_net": "net"}


@dataclass
class Row:
    data: dict
    line: int  # 1-based line in the JSONL file (0 for JSON files)


@dataclass
class RenderedItem:
    """One item as the digest showed it (placement: one_thing | section | also_pending)."""
    id: str
    about: str | None
    placement: str
    section: str | None
    priority: str | None
    confidence: str | None
    what: str
    why: str
    candidate_ids: list[str]
    candidate_types: list[str]
    citations: list[str]
    source_ids: set[str]
    actions: list[dict]
    position: int
    is_one_thing: bool = False
    entities: list[str] = field(default_factory=list)
    times_surfaced: int = 0

    @property
    def text(self) -> str:
        parts = [self.what, self.why] + [str(a.get("text") or "") + " " + str(a.get("draft") or "")
                                         + " " + str(a.get("brief") or "") for a in self.actions]
        return " ".join(p for p in parts if p)

    @property
    def action_types(self) -> list[str]:
        return [a.get("type") for a in self.actions if a.get("type")]


@dataclass
class Signal:
    """One thing the pipeline noticed: a Finding (v2), or a candidate that has no finding behind it."""
    artifact: str              # findings | candidates
    row: Row
    type: str                  # Finding.kind (safety nets keep the v1 rule name) or Candidate.type
    origin: str | None         # thread_reader | calendar_sweep | notes_tasks_sweep | news_sweep | safety_net
    title: str
    abouts: list[str]          # about keys (tags normalized as digest/findings.py does, plus the candidate's key)
    sources: set[str]          # manifest source ids its citations (and, for a reader, its thread) resolve to
    refs: list[str]            # the raw citation refs (msg:, event:, note:, task:)
    entities: list[str]
    needs_avery: str           # yes | unsure | no
    live: bool                 # reaches the digest: yes, or unsure with a question card (findings.to_triage)
    priority: str | None
    actions: list[str]
    candidate_id: str | None
    thread: str | None         # the manifest thread a reader read
    suspicious: bool
    contradiction: bool
    rescued: bool

    @property
    def stage(self) -> str:
        return ORIGIN_STAGE.get(self.origin or "", "read")

    def label(self) -> str:
        return f"{self.origin or self.artifact}:{self.type} '{self.title[:60]}' ({self.needs_avery}, {self.priority})"


class RunView:
    """Everything the scorer knows about one run directory."""

    def __init__(self, run_dir: Path, index: SourceIndex, repo_root: Path | None = None, day: int | None = None):
        self.dir = Path(run_dir)
        self.day = day
        self.index = index
        self.repo_root = repo_root
        self.missing: list[str] = [a for a, f in ARTIFACTS.items() if a not in OPTIONAL_ARTIFACTS and not (self.dir / f).exists()]
        self.findings = self._jsonl("findings")
        self.candidates = self._jsonl("candidates")
        self.triage = self._jsonl("triage")
        self.actions_rows = self._jsonl("actions")
        self.degradations = self._jsonl("degradations")
        self.cost_rows = self._jsonl("cost_log")
        self.malformed: list[str] = []
        raw_contacts = self._json("contacts", [])
        self.contacts: list[dict] = [c for c in raw_contacts if isinstance(c, dict)]
        if len(self.contacts) < len(raw_contacts):
            self.malformed.append(f"contacts.json: {len(raw_contacts) - len(self.contacts)} of {len(raw_contacts)} rows are "
                                  "not JSON objects (e.g. model reprs), so contact metrics read them as missing")
        self.reduce: dict = self._json("reduce", {})
        self.compose: dict = self._json("compose", {})
        self.verify: dict = self._json("verify", {})
        self.cost: dict = self._json("cost", {})
        self.run: dict = self._json("run", {})
        md_path = self.dir / ARTIFACTS["digest"]
        self.digest_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        self.digest: ParsedDigest = parse_digest(self.digest_text)
        self._cand_by_id = {r.data.get("candidate_id"): r for r in self.candidates}
        self._triage_by_cand: dict[str, list[Row]] = {}
        for r in self.triage:
            self._triage_by_cand.setdefault(r.data.get("candidate_id"), []).append(r)
        self._reduce_by_id = {it.get("id"): it for it in self.reduce.get("items", []) if isinstance(it, dict)}
        self.signals: list[Signal] = self._build_signals()
        self._signals_by_cand: dict[str, list[Signal]] = {}
        for s in self.signals:
            if s.candidate_id:
                self._signals_by_cand.setdefault(s.candidate_id, []).append(s)
        # baseline runs (and runs with no pipeline artifacts at all) are scored from digest.md; a pipeline run that
        # lost compose.json is not: its missing items stay misses attributed to compose
        is_baseline = bool(self.run.get("baseline")) or self.dir.name.endswith("baseline") or "+baseline" in self.dir.name
        self.markdown_only = bool(self.digest_text) and not self.compose and (
            is_baseline or not (self.candidates or self.triage or self.reduce))
        if self.markdown_only:
            from .markdown_view import rendered_from_markdown  # imports RenderedItem from here

            self.rendered: list[RenderedItem] = rendered_from_markdown(self.digest, index, index.manifest, day)
        else:
            self.rendered = self._build_rendered()

    # ------------------------------------------------------------------ loading
    def _jsonl(self, artifact: str) -> list[Row]:
        p = self.dir / ARTIFACTS[artifact]
        if not p.exists():
            return []
        rows = []
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                rows.append(Row(json.loads(line), n))
        return rows

    def _json(self, artifact: str, default: Any) -> Any:
        p = self.dir / ARTIFACTS[artifact]
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def link(self, artifact: str, line: int | None = None) -> str:
        p = self.dir / ARTIFACTS[artifact]
        if self.repo_root:
            with contextlib.suppress(ValueError):
                p = p.resolve().relative_to(self.repo_root.resolve())
        return f"{p}#L{line}" if line else str(p)

    # ------------------------------------------------------------------ lookups
    def candidate(self, cid: str) -> Row | None:
        return self._cand_by_id.get(cid)

    def triage_for(self, cid: str) -> list[Row]:
        return self._triage_by_cand.get(cid, [])

    def contact_by_email(self, email: str) -> dict | None:
        e = email.lower()
        for c in self.contacts:
            if e in [x.lower() for x in c.get("emails", [])]:
                return c
        return None

    def signals_for(self, cid: str) -> list[Signal]:
        return self._signals_by_cand.get(cid, [])

    def signal_link(self, s: Signal) -> str:
        return self.link(s.artifact, s.row.line)

    def item_signals(self, item: RenderedItem) -> list[Signal]:
        return [s for c in item.candidate_ids for s in self.signals_for(c)]

    # ------------------------------------------------------------------ findings → signals
    def _build_signals(self) -> list[Signal]:
        out: list[Signal] = []
        covered: set[str] = set()
        for r in self.findings:
            d = r.data
            cid = d.get("candidate_id")
            cand = self.candidate(cid) if cid else None
            refs = evidence_refs(d.get("citations") or [])
            thread = self.index.resolve(d.get("thread_id")) if d.get("thread_id") else None
            if thread is None and d.get("origin") == "thread_reader":
                thread = majority_source(self.index, refs, kind="thread")
            abouts = [about_key(t, d.get("title", "")) for t in d.get("about") or [] if t]
            if cand and cand.data.get("about"):
                abouts.append(cand.data["about"])
            needs = d.get("needs_avery") or "yes"
            out.append(Signal(
                artifact="findings", row=r, type=d.get("kind") or "", origin=d.get("origin"), title=d.get("title") or "",
                abouts=abouts, sources=self.index.resolve_all(refs) | ({thread} if thread else set()), refs=refs,
                entities=[str(e) for e in d.get("entities") or []], needs_avery=needs,
                live=needs == "yes" or (needs == "unsure" and bool(d.get("ambiguity"))), priority=d.get("priority"),
                actions=[a.get("type") for a in d.get("proposed_actions") or [] if a.get("type")], candidate_id=cid,
                thread=thread, suspicious=bool(d.get("suspicious_instructions")), contradiction=bool(d.get("contradictions")),
                rescued=bool(d.get("rescued_by_safety_net"))))
            if cid:
                covered.add(cid)
        for r in self.candidates:  # candidates with no finding behind them (runs without findings.jsonl)
            d = r.data
            cid = d.get("candidate_id")
            if cid in covered:
                continue
            facts = d.get("facts") or {}
            tri = [t.data for t in self.triage_for(cid)]
            refs = [e.get("source_id", "") for e in d.get("evidence") or []] + list(d.get("context_refs") or [])
            needs = facts.get("needs_avery") or "yes"
            out.append(Signal(
                artifact="candidates", row=r, type=d.get("type") or "", origin=facts.get("origin"),
                title=facts.get("title") or d.get("about") or "", abouts=[k for k in [d.get("about"), *facts.get("about_tags", [])] if k],
                sources=self.index.resolve_all(refs), refs=refs, entities=[str(e) for e in d.get("entities") or []], needs_avery=needs,
                live=needs != "no", priority=max_priority(t.get("priority") for t in tri if t.get("include")),
                actions=[a.get("type") for t in tri for a in t.get("proposed_actions", []) if a.get("type")], candidate_id=cid,
                thread=facts.get("thread_id") and self.index.resolve(facts["thread_id"]),
                suspicious=d.get("type") == "suspicious_content" or bool(facts.get("instructions")),
                contradiction=d.get("type") == "contradiction" or bool(facts.get("contradictions")),
                rescued=bool(facts.get("rescued_by_safety_net"))))
        return out

    # ------------------------------------------------------------------ the rendered digest
    def _item_record(self, item_id: str) -> dict:
        """reduce item, or a stand-in built from the candidate + its triage result."""
        if item_id in self._reduce_by_id:
            return self._reduce_by_id[item_id]
        cand = self.candidate(item_id)
        tri = [t.data for t in self.triage_for(item_id)]
        rec: dict = {"id": item_id, "candidate_ids": [item_id]}
        if cand:
            rec["about"] = cand.data.get("about")
            rec["entities"] = cand.data.get("entities", [])
        if tri:
            rec["priority"] = max_priority(t.get("priority") for t in tri)
            rec["section"] = tri[0].get("section")
            rec["confidence"] = tri[0].get("confidence")
            rec["citations"] = [c for t in tri for c in t.get("citations", [])]
            rec["proposed_actions"] = [a for t in tri for a in t.get("proposed_actions", [])]
        return rec

    _SECTION_TITLES = {"urgent": "## Urgent", "decisions": "## Decisions", "news": "## AI Industry News", "pulse": "## Team",
                       "calendar_personal": "## Calendar"}

    def _sections_in_rendered_order(self) -> list[dict]:
        """compose.json lists sections in canonical order; a customize run can render them in another. Positions must
        follow the page, so sort by where each section's heading appears in digest.md (unknown headings keep their place)."""
        blocks = list(self.compose.get("sections", []))
        text = self.digest_text if isinstance(getattr(self, "digest_text", None), str) else ""
        if not text:
            return blocks
        pos = {}
        for name, head in self._SECTION_TITLES.items():
            i = text.find(head)
            if i >= 0:
                pos[name] = i
        return sorted(blocks, key=lambda b: pos.get(b.get("name"), 10**9))

    def _build_rendered(self) -> list[RenderedItem]:
        comp_items = {c.get("id"): c for c in self.compose.get("items", []) if isinstance(c, dict)}
        dropped = {v.get("item_id") for v in self.verify.get("violations", []) if v.get("fix") == "dropped"}
        actions_by_item: dict[str, list[dict]] = {}
        for r in self.actions_rows:
            actions_by_item.setdefault(r.data.get("item_id"), []).append(r.data | {"_line": r.line})

        placements: list[tuple[str, str, str | None]] = []  # (id, placement, section)
        seen: set[str] = set()
        one = self.compose.get("one_thing_id")
        section_of = {i: b.get("name") for b in self.compose.get("sections", []) for i in b.get("item_ids", [])}
        if one:
            placements.append((one, "one_thing", section_of.get(one)))
            seen.add(one)
        for block in self._sections_in_rendered_order():
            for i in block.get("item_ids", []):
                if i not in seen:
                    placements.append((i, "section", block.get("name")))
                    seen.add(i)
        for i in list(self.compose.get("cut_ids", [])) + list(self.reduce.get("overflow", [])):
            if i not in seen:
                placements.append((i, "also_pending", None))
                seen.add(i)

        out: list[RenderedItem] = []
        for pos, (iid, placement, section) in enumerate(placements, start=1):
            if iid in dropped:
                continue
            rec = self._item_record(iid)
            comp = comp_items.get(iid, {})
            cids = rec.get("candidate_ids") or [iid]
            ctypes = rec.get("candidate_types") or [c.data.get("type") for c in (self.candidate(x) for x in cids) if c]
            times = rec.get("times_surfaced") or max(
                [int(c.data.get("times_surfaced", 0)) for c in (self.candidate(x) for x in cids) if c] or [0])
            actions = actions_by_item.get(iid) or [dict(a) for a in comp.get("final_actions", [])]
            if placement == "also_pending":
                actions = []
            citations = evidence_refs(rec.get("citations", []))
            out.append(RenderedItem(
                id=iid, about=rec.get("about"), placement=placement,
                section=section or (rec.get("section") if placement == "one_thing" else None),
                priority=rec.get("priority"), confidence=rec.get("confidence"),
                what=comp.get("what", ""), why=comp.get("why") or rec.get("why", ""), candidate_ids=cids, candidate_types=ctypes,
                citations=citations, source_ids=self.index.resolve_all(citations), actions=actions,
                position=pos, is_one_thing=(iid == one), entities=rec.get("entities", []), times_surfaced=times,
            ))
        return out

    def rendered_by_id(self, iid: str) -> RenderedItem | None:
        return next((r for r in self.rendered if r.id == iid), None)

    def drafts(self) -> list[dict]:
        """Action rows that carry draft text (replies, forwards, decide drafts, or a message_person with text)."""
        if self.markdown_only:
            return [a | {"item_id": it.id, "_line": 0} for it in self.rendered for a in it.actions
                    if a.get("type") in DRAFT_TYPES and a.get("draft")]
        out = []
        for r in self.actions_rows:
            d = r.data
            text = d.get("draft")
            if d.get("type") in DRAFT_TYPES and text:
                out.append(d | {"_line": r.line})
        return out
