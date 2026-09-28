"""Load one run's artifacts (digest/runs.py ARTIFACTS) and build the scorer's view of what the digest showed.

This is the only module that knows artifact shapes: `digest/schemas.py` pins them all (ReduceResult,
MaterializedAction, VerifyResult since OPEN_QUESTIONS #7a). The reader stays tolerant of missing files and keys, so
a run that crashed half-way is still scored (a missing artifact becomes a miss attributed to its stage).

Item ids in compose.json are reduce ids; if reduce.json is absent, they are looked up as candidate ids. A run with
a digest.md but no compose.json (the naive baseline, eval.md §8) is scored from the markdown alone
(`markdown_view.py`).
"""
from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from digest.runs import ARTIFACTS

from .digest_md import ParsedDigest, parse_digest
from .match import SourceIndex, evidence_refs, max_priority

OPTIONAL_ARTIFACTS = {"trace"}  # the debug trace is not a pipeline output; its absence is not a miss
DRAFT_TYPES = ("reply", "forward_delegate", "decide", "message_person")


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


class RunView:
    """Everything the scorer knows about one run directory."""

    def __init__(self, run_dir: Path, index: SourceIndex, repo_root: Path | None = None, day: int | None = None):
        self.dir = Path(run_dir)
        self.day = day
        self.index = index
        self.repo_root = repo_root
        self.missing: list[str] = [a for a, f in ARTIFACTS.items() if a not in OPTIONAL_ARTIFACTS and not (self.dir / f).exists()]
        self.extractions = self._jsonl("extractions")
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

    def extraction_sources(self, row: Row) -> set[str]:
        return self.index.resolve_all(evidence_refs(row.data) + [row.data.get("source_id", "")])

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
        for block in self.compose.get("sections", []):
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
