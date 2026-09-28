"""Extractor stage (architecture §1–§2, extraction_schema §3): prompt P3 per thread / note / task / newsletter,
validated as ExtractorOutput, evidence-checked in code, cached by content + contact directory + prompt version."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..compile.profile import contact_directory
from ..config import Settings
from ..llm import LLM, LLMResult
from ..normalize import NormalizedWorld
from ..prompts import Prompt, load_prompt
from ..runs import RunContext
from ..schemas import ABOUT_KINDS, STAGE_VOCAB, Extraction, ExtractionMeta, ExtractorOutput, ProfileConfig
from .documents import Document, directory_hash, documents_for
from .evidence import EvidenceReport, SourceIndex, check_payload

PAYLOAD_FIELDS = {"human_thread": "human_thread", "newsletter": "newsletter", "automated": "automated",
                  "note": "note", "task": "task", "marketing": None}


@dataclass
class ExtractStats:
    documents: int = 0
    llm_calls: int = 0
    cached: int = 0
    skipped_marketing: int = 0
    invalid: int = 0
    evidence_checked: int = 0
    evidence_valid: int = 0
    evidence_dropped: int = 0
    evidence_replaced: int = 0
    type_changes: list[dict] = field(default_factory=list)


def input_hash(doc: Document, dir_hash: str, prompt_version: str) -> str:
    return hashlib.sha256(f"{doc.content_hash}|{dir_hash}|{prompt_version}".encode()).hexdigest()[:24]


def build_messages(prompt: Prompt, doc: Document, profile: ProfileConfig, owner_email: str | None) -> list[dict]:
    text = prompt.render(
        avery_name=profile.person, avery_email=owner_email or "unknown",
        contact_directory=json.dumps(contact_directory(profile), ensure_ascii=False),
        standing_topics=json.dumps(list(profile.standing_topics), ensure_ascii=False),
        about_kinds=", ".join(ABOUT_KINDS),
        stage_vocab=json.dumps({k: list(v) for k, v in STAGE_VOCAB.items()}),
        document=doc.text,
    )
    return [{"role": "system", "content": text}]


def reconcile_type(out: ExtractorOutput, doc: Document, stats: ExtractStats) -> ExtractorOutput | None:
    """Exactly one payload must match `type`. Coerce when unambiguous; None when nothing usable came back."""
    present = [k for k in ("human_thread", "newsletter", "automated", "note", "task") if getattr(out, k) is not None]
    want = PAYLOAD_FIELDS[out.type]
    if want is None:
        if present:
            stats.type_changes.append({"source_id": doc.source_id, "from": out.type, "to": present[0], "reason": "payload present"})
            return out.model_copy(update={"type": present[0], **dict.fromkeys(present[1:])})
        return out
    if want in present:
        if len(present) > 1:
            return out.model_copy(update={k: None for k in present if k != want})
        return out
    if len(present) == 1:
        stats.type_changes.append({"source_id": doc.source_id, "from": out.type, "to": present[0], "reason": "type/payload mismatch"})
        return out.model_copy(update={"type": present[0]})
    return None


def to_extraction(out: ExtractorOutput, doc: Document, meta: ExtractionMeta, stats: ExtractStats,
                  ctx: RunContext | None) -> Extraction:
    payload = out.payload
    if payload is not None:
        idx = SourceIndex(doc.sources)
        fallback = None
        if doc.kind == "thread" and doc.meta.get("message_ids"):
            fallback = f"msg:{doc.meta['message_ids'][-1]}"
        elif doc.sources:
            fallback = next(iter(doc.sources))
        payload, rep = check_payload(payload, idx, fallback)
        _account(rep, doc, stats, ctx)
        if out.type == "human_thread" and doc.kind == "thread":
            payload = _fix_ball(payload, doc)
    return Extraction(meta=meta, source_id=doc.source_id, type=out.type, payload=payload)


def _fix_ball(payload, doc: Document):
    """last_message_by/at are facts of the document; code sets them."""
    ball = payload.ball
    by, at = doc.meta.get("last_message_by"), doc.meta.get("last_message_at")
    if by and at and (ball.last_message_by != by or ball.last_message_at.isoformat() != at):
        return payload.model_copy(update={"ball": ball.model_copy(update={"last_message_by": by, "last_message_at": datetime.fromisoformat(at)})})
    return payload


def _account(rep: EvidenceReport, doc: Document, stats: ExtractStats, ctx: RunContext | None) -> None:
    stats.evidence_checked += rep.checked
    stats.evidence_valid += rep.valid
    stats.evidence_dropped += len(rep.dropped)
    stats.evidence_replaced += len(rep.replaced)
    if ctx is not None:
        for d in rep.dropped:
            ctx.degrade("extract", doc.source_id, "evidence_invalid", why=d["reason"], path=d["path"],
                        source_id=d["source_id"], quote=d["quote"])
        for r in rep.replaced:
            ctx.degrade("extract", doc.source_id, "evidence_replaced", path=r["path"], source_id=r["source_id"],
                        quote=r["quote"], replaced_with=r["replaced_with"])


def extract_documents(llm: LLM, docs: list[Document], profile: ProfileConfig, owner_email: str | None, settings: Settings,
                      ctx: RunContext | None = None, prompt: Prompt | None = None) -> tuple[list[Extraction], ExtractStats]:
    prompt = prompt or load_prompt("extractor")
    stats = ExtractStats(documents=len(docs))
    dir_hash = directory_hash(contact_directory(profile), list(profile.standing_topics))
    now = datetime.now(UTC)
    results: list[Extraction] = []
    calls: list[dict] = []
    call_docs: list[Document] = []
    for doc in docs:
        if doc.router_type == "marketing":
            stats.skipped_marketing += 1
            meta = ExtractionMeta(prompt_version=prompt.version_tag, model="router", input_hash=input_hash(doc, dir_hash, prompt.version_tag), extracted_at=now)
            results.append(Extraction(meta=meta, source_id=doc.source_id, type="marketing", payload=None))
            continue
        calls.append({"role": prompt.model_role, "prompt_version": prompt.version_tag,
                      "messages": build_messages(prompt, doc, profile, owner_email), "output_model": ExtractorOutput,
                      "tag": doc.source_id})
        call_docs.append(doc)
    outcomes = llm.complete_many(calls, max_workers=settings.llm.max_workers) if calls else []
    for doc, res in zip(call_docs, outcomes, strict=True):
        stats.llm_calls += 1
        if isinstance(res, LLMResult):
            stats.cached += 1 if res.cached else 0
            fixed = reconcile_type(res.output, doc, stats)
            if fixed is None:
                stats.invalid += 1
                if ctx is not None:
                    ctx.degrade("extract", doc.source_id, "no_payload", type=res.output.type)
                continue
            meta = ExtractionMeta(prompt_version=prompt.version_tag, model=res.model, input_hash=input_hash(doc, dir_hash, prompt.version_tag), extracted_at=now)
            results.append(to_extraction(fixed, doc, meta, stats, ctx))
        else:
            stats.invalid += 1
            reason = type(res).__name__
            if ctx is not None:
                detail = str(res)[:300]
                ctx.degrade("extract", doc.source_id, reason, detail=detail)
    return results, stats


def extract_world(llm: LLM, world: NormalizedWorld, profile: ProfileConfig, settings: Settings,
                  ctx: RunContext | None = None, prompt: Prompt | None = None) -> tuple[list[Extraction], ExtractStats]:
    return extract_documents(llm, documents_for(world), profile, world.owner_email, settings, ctx, prompt)


__all__ = ["ExtractStats", "extract_documents", "extract_world", "input_hash", "build_messages", "reconcile_type", "to_extraction"]
