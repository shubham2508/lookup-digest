"""Load config/settings.yaml and config/models.yaml into validated objects."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .paths import CONFIG_DIR

Effort = Literal["low", "medium", "high"]
PIPELINE_ROLES = ("extractor", "triage", "compose", "materializer", "compiler", "linker",
                  "thread_reader", "calendar_sweep", "notes_tasks_sweep", "news_sweep", "contact_classifier", "signature_parser")
ALL_ROLES = PIPELINE_ROLES + ("generator", "judge", "sim_avery")
SESSION_MODEL = "claude-code-session"  # marker: no API calls for this role


class RoleConfig(BaseModel):
    model: str | None = None
    family: str | None = None
    reasoning_effort: Effort | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    @property
    def is_session(self) -> bool:
        return self.model == SESSION_MODEL


class ProviderConfig(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    app_name: str = "lookup-digest"


class ModelsConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    roles: dict[str, RoleConfig]

    @model_validator(mode="after")
    def _check(self) -> ModelsConfig:
        missing = [r for r in ALL_ROLES if r not in self.roles]
        if missing:
            raise ValueError(f"models.yaml is missing roles: {missing}")
        pipeline_families = {self.roles[r].family for r in PIPELINE_ROLES if self.roles[r].family}
        gen = self.roles["generator"].family
        judge = self.roles["judge"]
        if judge.model:  # the family rule is only checkable once a judge is chosen
            if judge.family is None:
                raise ValueError("judge has a model but no family; set roles.judge.family")
            if judge.family in pipeline_families or judge.family == gen:
                raise ValueError(
                    f"family rule violated: judge family {judge.family!r} must differ from the pipeline "
                    f"{sorted(pipeline_families)} and the generator {gen!r} (OPEN_QUESTIONS.md #1)"
                )
        return self

    def role(self, name: str) -> RoleConfig:
        try:
            return self.roles[name]
        except KeyError:
            raise KeyError(f"unknown model role {name!r}; known: {sorted(self.roles)}") from None


class Budget(BaseModel):
    length_words: int = 350
    max_items: int = 12
    k_cap: int = 25
    question_budget: int = 2
    evidence_quote_max_words: int = 20


class ContextCfg(BaseModel):
    window_days: int = 14
    max_items: int = 8


class CalendarCfg(BaseModel):
    expand_before_days: int = 30
    expand_after_days: int = 14


class FreshnessCfg(BaseModel):
    email_stale_hours: int = 24
    calendar_stale_hours: int = 24
    tasks_stale_days: int = 7


class RecruiterPattern(BaseModel):
    count: int = 3
    window_days: int = 7


class CadenceDrop(BaseModel):
    ratio: float = 2.0
    min_current_gap_days: int = 3
    baseline_days: tuple[int, int] = (1, 20)
    recent_days: tuple[int, int] = (21, 30)


class ThresholdsDefault(BaseModel):
    investor_quiet_business_days: int = 3
    hiring_stall_days: int = 5
    recruiter_pattern: RecruiterPattern = Field(default_factory=RecruiterPattern)
    cadence_drop: CadenceDrop = Field(default_factory=CadenceDrop)
    declined_meeting_lookback_days: int = 14
    family_conflict_lookahead_days: int = 2
    behavior_window_days: int = 30


class DraftsCfg(BaseModel):
    max_sentences: int = 3
    banned_phrases: list[str] = Field(default_factory=list)


class LLMCfg(BaseModel):
    cache_dir: str = ".cache/llm"
    max_workers: int = 8
    seed: int | None = 7
    max_retries_transport: int = 3
    jev_min_probability: float = 0.7


class StoreCfg(BaseModel):
    path_template: str = "runs/{world}/store.sqlite"
    rulings_path_template: str = "runs/{world}/rulings.yaml"


class Settings(BaseModel):
    timezone: str = "America/Los_Angeles"
    digest_time: str = "06:00"
    budget: Budget = Field(default_factory=Budget)
    context: ContextCfg = Field(default_factory=ContextCfg)
    calendar: CalendarCfg = Field(default_factory=CalendarCfg)
    freshness: FreshnessCfg = Field(default_factory=FreshnessCfg)
    thresholds_default: ThresholdsDefault = Field(default_factory=ThresholdsDefault)
    drafts: DraftsCfg = Field(default_factory=DraftsCfg)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    store: StoreCfg = Field(default_factory=StoreCfg)


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_models(path: Path | None = None) -> ModelsConfig:
    return ModelsConfig.model_validate(_read_yaml(path or CONFIG_DIR / "models.yaml"))


def load_settings(path: Path | None = None) -> Settings:
    return Settings.model_validate(_read_yaml(path or CONFIG_DIR / "settings.yaml"))
