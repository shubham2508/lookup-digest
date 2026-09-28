"""Prompt files: prompts/<name>.md with a YAML front matter (specs/prompts.md).

---
name: triage
version: 1
model_role: triage
output_model: TriageResult
---
<prompt text with {{placeholders}}>

Placeholders use double braces so JSON examples in the prompt text are safe. Any change to a prompt bumps
`version` and gets a line in the eval history file (CLAUDE.md rule 10).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import PROMPTS_DIR

_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptError(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    model_role: str
    output_model: str
    text: str
    path: Path

    @property
    def version_tag(self) -> str:
        return f"{self.name}@v{self.version}"

    @property
    def variables(self) -> list[str]:
        return sorted(set(_VAR.findall(self.text)))

    def render(self, **values: object) -> str:
        missing = [v for v in self.variables if v not in values]
        if missing:
            raise PromptError(f"prompt {self.name!r} is missing values for {missing}")
        return _VAR.sub(lambda m: str(values[m.group(1)]), self.text)


def parse_prompt(text: str, path: Path) -> Prompt:
    m = _FM.match(text)
    if not m:
        raise PromptError(f"{path}: missing front matter (--- name/version/model_role/output_model ---)")
    meta = yaml.safe_load(m.group(1)) or {}
    for k in ("name", "version", "model_role", "output_model"):
        if k not in meta:
            raise PromptError(f"{path}: front matter lacks {k!r}")
    return Prompt(
        name=str(meta["name"]), version=int(meta["version"]), model_role=str(meta["model_role"]),
        output_model=str(meta["output_model"]), text=text[m.end():], path=path,
    )


def load_prompt(name: str, prompts_dir: Path | None = None) -> Prompt:
    path = (prompts_dir or PROMPTS_DIR) / f"{name}.md"
    if not path.exists():
        raise PromptError(f"no prompt file {path}")
    return parse_prompt(path.read_text(encoding="utf-8"), path)


def list_prompts(prompts_dir: Path | None = None) -> list[Prompt]:
    d = prompts_dir or PROMPTS_DIR
    return [parse_prompt(p.read_text(encoding="utf-8"), p) for p in sorted(d.glob("*.md")) if not p.name.startswith("README")]
