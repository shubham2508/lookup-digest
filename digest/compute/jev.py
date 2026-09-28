"""Jev (TypeSafe's classifier model) through OpenRouter's decisions endpoint, for the linker's pick-one questions.

Jev answers typed questions (pick one option, yes/no, score) with calibrated probabilities and writes no text, so
it cannot hallucinate an option that was not offered. Request: {model, state, questions}; each question here is a
`choice` whose criteria map option ids → descriptions, always including "none". Limits (TypeSafe): 255 options per
question, ~32k tokens per request; questions are sent in chunks to stay well under that.

Calls are cached on disk by request hash and logged to the run's cost and trace logs like every LLM call.
Any failure raises JevError; the linker then falls back to the LLM path for that question type.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MAX_OPTIONS = 254          # + "none"
CHUNK_QUESTIONS = 25       # questions per request, at most
CHUNK_CHARS = 40_000       # and at most this much question text (Jev rejects ~32k-token requests: max_tokens_exceeded)


class JevError(Exception):
    pass


@dataclass
class JevDecider:
    api_key: str
    model: str = "typesafe/jev-1.13"
    cache_dir: Path | None = None
    cost_log: object | None = None
    trace_log: object | None = None
    timeout_s: float = 30.0

    def _post(self, body: dict, tag: str) -> dict:
        key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = self.cache_dir / "jev" / f"{key}.json" if self.cache_dir else None
        if path is not None and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if self.cost_log is not None:
                self.cost_log.record(role="linker", model=self.model, prompt_version="jev-decisions", cached=True, prompt_tokens=0,
                                     completion_tokens=0, cost_usd=0.0, cost_known=True, tag=tag, cache_key=key)
            if self.trace_log is not None:
                self.trace_log.record(role="linker", tag=tag, prompt_version="jev-decisions", model=self.model, cached=True,
                                      messages=[{"role": "state+questions", "content": json.dumps(body, ensure_ascii=False)}],
                                      raw=json.dumps(data), output=data.get("answers"), output_model="Jev decisions",
                                      retries=0, latency_ms=0, cost_usd=0.0, prompt_tokens=0, completion_tokens=0, cache_key=key, invalid=False)
            return data
        t0 = time.perf_counter()
        last: Exception | None = None
        for _attempt in range(2):
            try:
                r = httpx.post(ENDPOINT, json=body, timeout=self.timeout_s,
                               headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
                if r.status_code >= 400:
                    raise JevError(f"HTTP {r.status_code}: {r.text[:300]}")
                data = r.json()
                if "answers" not in data:
                    raise JevError(f"no answers in response: {str(data)[:300]}")
                break
            except (httpx.HTTPError, JevError, ValueError) as e:
                last = e
        else:
            raise JevError(str(last))
        ms = int((time.perf_counter() - t0) * 1000)
        usage = data.get("usage") or {}
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if self.cost_log is not None:
            self.cost_log.record(role="linker", model=data.get("model", self.model), prompt_version="jev-decisions", cached=False,
                                 prompt_tokens=int(usage.get("input_tokens") or 0), completion_tokens=int(usage.get("output_tokens") or 0),
                                 cost_usd=float(usage.get("cost") or 0.0), cost_known="cost" in usage, tag=tag, cache_key=key,
                                 retries=0, latency_ms=ms, invalid=False)
        if self.trace_log is not None:
            self.trace_log.record(role="linker", tag=tag, prompt_version="jev-decisions", model=data.get("model", self.model),
                                  cached=False, messages=[{"role": "state+questions", "content": json.dumps(body, ensure_ascii=False)}],
                                  raw=json.dumps(data), output=data.get("answers"), output_model="Jev decisions", retries=0,
                                  latency_ms=ms, cost_usd=float(usage.get("cost") or 0.0), prompt_tokens=int(usage.get("input_tokens") or 0),
                                  completion_tokens=int(usage.get("output_tokens") or 0), cache_key=key, invalid=False,
                                  ts=datetime.now(UTC).isoformat(timespec="seconds"))
        return data

    def pick(self, task: str, instructions: str, questions: list) -> dict[str, tuple[str | None, float]]:
        """questions: LinkQuestion list → {question id: (chosen option id or None, probability)}."""
        out: dict[str, tuple[str | None, float]] = {}
        qs = [q for q in questions if q.options]
        chunks: list[list] = [[]]
        size = 0
        for q in qs:
            qsize = len(q.item[:600]) + sum(len(o.text[:300]) + 12 for o in q.options[:MAX_OPTIONS])
            if chunks[-1] and (len(chunks[-1]) >= CHUNK_QUESTIONS or size + qsize > CHUNK_CHARS):
                chunks.append([])
                size = 0
            chunks[-1].append(q)
            size += qsize
        for chunk in (c for c in chunks if c):
            state = {"task": instructions}
            jq = {}
            for q in chunk:
                opts = q.options[:MAX_OPTIONS]
                crit = {o.id: o.text[:300] for o in opts}
                crit["none"] = "none of these is the same thing"
                jq[q.id] = {"type": "choice", "instructions": f"{instructions} ITEM: {q.item[:600]}", "criteria": crit}
            data = self._post({"model": self.model, "state": state, "questions": jq}, tag=f"link:{task}")
            for qid, a in (data.get("answers") or {}).items():
                choice = a.get("choice")
                prob = float((a.get("probabilities") or {}).get(choice, 0.0)) if choice else 0.0
                out[qid] = (None if choice in (None, "none") else choice, prob)   # "none" competes as an option
        return out
