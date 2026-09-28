"""OpenRouter client: structured output, disk cache, per-call cost log, validation with one retry.

CLAUDE.md rules 5 (validate, retry once, then degrade) and 9 (cost per call from the response usage).
Cache key = hash(role, prompt_version, model, reasoning_effort, messages, output schema).
The caller decides how to degrade when LLMOutputInvalid is raised; this module never crashes a run on
bad model output, it reports it.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .config import ModelsConfig, RoleConfig, load_models
from .paths import CACHE_DIR, ROOT

T = TypeVar("T", bound=BaseModel)

# keywords OpenAI-style strict JSON schema rejects; Pydantic still enforces them after parsing
_STRIP_KEYS = {
    "format", "minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "pattern", "default", "examples", "multipleOf", "uniqueItems",
}


class LLMError(Exception):
    """Base class for this module."""


class LLMOutputInvalid(LLMError):
    """The model's output failed validation twice. The caller skips the item, logs it, notes it in the header."""

    def __init__(self, role: str, errors: list[str], raw: list[str]):
        super().__init__(f"{role}: output failed validation after retry: {errors[-1][:300]}")
        self.role, self.errors, self.raw = role, errors, raw


class LLMRoleUnconfigured(LLMError):
    """The role has no model in config/models.yaml (e.g. judge until Shubham picks)."""


class LLMSessionRole(LLMError):
    """The role is served by a Claude Code session, not an API (generator)."""


def _strip(node: Any, in_properties: bool = False) -> Any:
    if isinstance(node, dict):
        # keys of a `properties` map are field names, never keywords: a field called `default` must survive
        out = {k: _strip(v, in_properties=(k == "properties")) for k, v in node.items() if in_properties or k not in _STRIP_KEYS}
        if not in_properties and out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"].keys())
        return out
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON schema for structured output: every property required, no additionalProperties, no unsupported keywords."""
    try:
        from openai.lib._pydantic import to_strict_json_schema

        schema = to_strict_json_schema(model)
    except Exception:  # noqa: BLE001 - helper missing in some SDK versions; fall back to the plain schema
        schema = model.model_json_schema()
    return _strip(schema)


def load_api_key(env_name: str = "OPENROUTER_API_KEY") -> str | None:
    key = os.environ.get(env_name)
    if key:
        return key
    try:
        from dotenv import dotenv_values

        return dotenv_values(ROOT / ".env").get(env_name) or None
    except Exception:  # noqa: BLE001 - no .env or unreadable: the caller reports the missing key
        return None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cost_known: bool = False

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd
        self.cost_known = self.cost_known or other.cost_known


@dataclass
class LLMResult(Generic[T]):
    output: T
    role: str
    model: str
    cached: bool
    usage: Usage
    retries: int
    latency_ms: int
    cache_key: str
    raw: str


class CostLog:
    """Append-only JSONL of every LLM call (cached ones included, at zero cost) plus in-memory totals."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[dict] = []
        self._lock = threading.Lock()

    def record(self, **entry: Any) -> None:
        entry.setdefault("ts", datetime.now(UTC).isoformat(timespec="seconds"))
        with self._lock:
            self.entries.append(entry)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, sort_keys=True) + "\n")

    def totals(self) -> dict:
        by_role: dict[str, dict] = {}
        tot = {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "cost_unknown_calls": 0}
        with self._lock:
            for e in self.entries:
                r = by_role.setdefault(e.get("role", "?"), {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
                for d in (tot, r):
                    d["calls"] += 1
                    d["cached"] += 1 if e.get("cached") else 0
                    d["prompt_tokens"] += e.get("prompt_tokens", 0)
                    d["completion_tokens"] += e.get("completion_tokens", 0)
                    d["cost_usd"] += e.get("cost_usd", 0.0)
                if not e.get("cached") and not e.get("cost_known", True):
                    tot["cost_unknown_calls"] += 1
        tot["cost_usd"] = round(tot["cost_usd"], 6)
        for r in by_role.values():
            r["cost_usd"] = round(r["cost_usd"], 6)
        tot["by_role"] = by_role
        return tot


def _usage_from(resp: Any) -> Usage:
    u = getattr(resp, "usage", None)
    if u is None:
        return Usage()
    cost = getattr(u, "cost", None)
    if cost is None:
        extra = getattr(u, "model_extra", None) or {}
        cost = extra.get("cost")
    return Usage(
        prompt_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(u, "completion_tokens", 0) or 0),
        cost_usd=float(cost or 0.0),
        cost_known=cost is not None,
    )


class LLM:
    def __init__(
        self,
        models: ModelsConfig | None = None,
        *,
        cache_dir: Path | None = None,
        cost_log: CostLog | None = None,
        client: Any = None,
        seed: int | None = 7,
        api_key: str | None = None,
        max_retries_transport: int = 3,
    ):
        self.models = models or load_models()
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR / "llm"
        self.cost_log = cost_log or CostLog(self.cache_dir / "cost_log.jsonl")
        self.seed = seed
        self._client = client
        self._api_key = api_key
        self._max_retries_transport = max_retries_transport
        self._client_lock = threading.Lock()

    # ------------------------------------------------------------------ client
    @property
    def client(self) -> Any:
        with self._client_lock:
            if self._client is None:
                from openai import OpenAI

                key = self._api_key or load_api_key(self.models.provider.api_key_env)
                if not key:
                    raise LLMError(f"{self.models.provider.api_key_env} is not set (env or .env)")
                import httpx

                self._client = OpenAI(
                    base_url=self.models.provider.base_url,
                    api_key=key,
                    max_retries=self._max_retries_transport,
                    # a hung request must fail fast and be retried, never stall a run (integration, 2026-09-28)
                    timeout=httpx.Timeout(180.0, connect=20.0),
                    default_headers={"X-Title": self.models.provider.app_name},
                )
            return self._client

    def role_config(self, role: str) -> RoleConfig:
        cfg = self.models.role(role)
        if cfg.is_session:
            raise LLMSessionRole(f"role {role!r} is served by a Claude Code session, not an API call")
        if not cfg.model:
            raise LLMRoleUnconfigured(f"role {role!r} has no model in config/models.yaml (see OPEN_QUESTIONS.md #1)")
        return cfg

    # ------------------------------------------------------------------ cache
    @staticmethod
    def cache_key(role: str, prompt_version: str, cfg: RoleConfig, messages: list[dict], schema: dict) -> str:
        payload = {
            "role": role, "prompt_version": prompt_version, "model": cfg.model,
            "reasoning_effort": cfg.reasoning_effort, "temperature": cfg.temperature,
            "messages": messages, "schema": schema,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _cache_path(self, role: str, key: str) -> Path:
        return self.cache_dir / role / f"{key}.json"

    # ------------------------------------------------------------------ calls
    def complete(
        self,
        role: str,
        prompt_version: str,
        messages: list[dict],
        output_model: type[T],
        *,
        cache: bool = True,
        tag: str = "",
        max_tokens: int | None = None,
    ) -> LLMResult[T]:
        cfg = self.role_config(role)
        schema = strict_schema(output_model)
        key = self.cache_key(role, prompt_version, cfg, messages, schema)
        path = self._cache_path(role, key)

        if cache and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            try:
                output = output_model.model_validate_json(data["content"])
            except ValidationError:
                output = None  # stale cache (schema changed): fall through to a live call
            if output is not None:
                self.cost_log.record(role=role, model=data.get("model", cfg.model), prompt_version=prompt_version,
                                     cached=True, prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
                                     cost_known=True, tag=tag, cache_key=key)
                return LLMResult(output=output, role=role, model=data.get("model", cfg.model), cached=True,
                                 usage=Usage(cost_known=True), retries=0, latency_ms=0, cache_key=key,
                                 raw=data["content"])

        t0 = time.perf_counter()
        usage_total = Usage()
        errors: list[str] = []
        raws: list[str] = []
        msgs = list(messages)
        output: T | None = None
        for attempt in range(2):
            content, usage = self._call(cfg, msgs, output_model.__name__, schema, max_tokens)
            usage_total.add(usage)
            raws.append(content)
            try:
                output = output_model.model_validate_json(content)
                break
            except ValidationError as e:
                errors.append(str(e))
                if attempt == 0:
                    msgs = msgs + [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": (
                            "Your previous output failed schema validation:\n" + str(e)[:2000]
                            + "\nReturn corrected JSON only, matching the schema exactly. "
                              "Do not change any facts; fix the structure and the field values that were rejected."
                        )},
                    ]
        latency_ms = int((time.perf_counter() - t0) * 1000)
        retries = max(0, len(raws) - 1)
        self.cost_log.record(role=role, model=cfg.model, prompt_version=prompt_version, cached=False,
                             prompt_tokens=usage_total.prompt_tokens, completion_tokens=usage_total.completion_tokens,
                             cost_usd=usage_total.cost_usd, cost_known=usage_total.cost_known, tag=tag,
                             cache_key=key, retries=retries, latency_ms=latency_ms, invalid=output is None)
        if output is None:
            raise LLMOutputInvalid(role, errors, raws)

        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "content": raws[-1], "model": cfg.model, "role": role, "prompt_version": prompt_version,
                "usage": usage_total.__dict__, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        return LLMResult(output=output, role=role, model=cfg.model, cached=False, usage=usage_total,
                         retries=retries, latency_ms=latency_ms, cache_key=key, raw=raws[-1])

    def _call(self, cfg: RoleConfig, messages: list[dict], name: str, schema: dict, max_tokens: int | None) -> tuple[str, Usage]:
        body: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        }
        if self.seed is not None:
            body["seed"] = self.seed
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if max_tokens or cfg.max_tokens:
            body["max_tokens"] = max_tokens or cfg.max_tokens
        extra: dict[str, Any] = {"usage": {"include": True}}
        if cfg.reasoning_effort:
            extra["reasoning"] = {"effort": cfg.reasoning_effort, "exclude": True}
        try:
            resp = self.client.chat.completions.create(**body, extra_body=extra)
        except Exception as e:  # provider rejected the schema → json_object fallback, schema in the prompt
            if "response_format" not in str(e) and "schema" not in str(e).lower():
                raise
            fallback = dict(body)
            fallback["response_format"] = {"type": "json_object"}
            fallback["messages"] = [{"role": "system", "content": "Return only JSON matching this schema:\n" + json.dumps(schema)}] + messages
            resp = self.client.chat.completions.create(**fallback, extra_body=extra)
        content = resp.choices[0].message.content or ""
        return content, _usage_from(resp)

    def complete_many(self, calls: list[dict], max_workers: int = 8) -> list[LLMResult | Exception]:
        """Run several `complete` calls in parallel; each element is a result or the exception it raised."""

        def one(kw: dict) -> LLMResult | Exception:
            try:
                return self.complete(**kw)
            except Exception as e:  # noqa: BLE001 - reported per item, never crashes the batch
                return e

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            return list(ex.map(one, calls))
