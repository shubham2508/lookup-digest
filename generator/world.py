"""Load world/<world>/ (script + prose) into plain dataclasses. No rendering here."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

WORLD_ROOT = Path(__file__).resolve().parents[1] / "world"

# recipient aliases used in prose files (FORMAT.md); rendered as list addresses
ALIASES: dict[str, dict[str, str]] = {
    "parents_list": {"name": "Little Acorns Families", "email": "families@littleacornsoakland.com"},
    "team_list": {"name": "Tessera Team", "email": "team@tessera.io"},
    "eng_list": {"name": "Tessera Engineering", "email": "eng@tessera.io"},
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    """Same rule as the product's task slug (OPEN_QUESTIONS #6a/#7b): lowercase, non-alnum runs → '-', ≤60 chars."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "task"


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Person:
    id: str
    name: str
    email: str
    emails: list[str]
    org: str | None
    title: str | None
    truth: dict
    style: str
    signature: str

    @property
    def domain(self) -> str:
        return self.email.split("@", 1)[1]


@dataclass
class World:
    path: Path
    name: str
    raw: dict
    people: dict[str, Person]
    orgs: dict[str, dict]
    storylines: list[dict]
    background: dict
    calendar: dict
    notes: dict
    variants: dict
    threads: list[dict] = field(default_factory=list)      # prose/threads/*.yaml
    bulk: list[dict] = field(default_factory=list)         # prose/bulk/*.yaml, flattened items with `category`
    note_bodies: dict[str, str] = field(default_factory=dict)

    @property
    def anchor(self):
        return self.raw["anchor"]

    @property
    def avery(self) -> Person:
        return self.people["avery"]

    def addr(self, ref: Any) -> dict[str, str]:
        """A person id, an alias, or {name, email} → {name, email}."""
        if isinstance(ref, dict):
            return {"name": ref.get("name") or ref["email"], "email": ref["email"]}
        if ref in self.people:
            p = self.people[ref]
            return {"name": p.name, "email": p.email}
        if ref in ALIASES:
            return dict(ALIASES[ref])
        raise KeyError(f"unknown recipient/sender ref {ref!r}")

    def person_for(self, ref: Any) -> Person | None:
        return self.people.get(ref) if isinstance(ref, str) else None

    def storyline(self, sid: str) -> dict | None:
        return next((s for s in self.storylines if s["id"] == sid), None)


def load_world(name: str, root: Path = WORLD_ROOT) -> World:
    path = root / name
    raw = load_yaml(path / "world.yaml")
    people: dict[str, Person] = {}
    for p in raw["people"]:
        people[p["id"]] = Person(id=p["id"], name=p["name"], email=p["emails"][0], emails=list(p["emails"]),
                                 org=p.get("org"), title=p.get("title"), truth=p.get("truth", {}),
                                 style=p.get("style", ""), signature=p.get("signature") or "")
    orgs = {o["id"]: o for o in raw["orgs"]}
    storylines = [load_yaml(f) for f in sorted((path / "storylines").glob("S*.yaml"))]
    background = load_yaml(path / "background.yaml")
    calendar = load_yaml(path / "calendar.yaml")
    notes = load_yaml(path / "notes.yaml")
    variants = load_yaml(path / "variants.yaml") if (path / "variants.yaml").exists() else {"honesty_variants": []}
    w = World(path=path, name=name, raw=raw, people=people, orgs=orgs, storylines=storylines,
              background=background, calendar=calendar, notes=notes, variants=variants)
    prose = path / "prose"
    for f in sorted((prose / "threads").glob("*.yaml")):
        t = load_yaml(f)
        t["_file"] = str(f)
        w.threads.append(t)
    for f in sorted((prose / "bulk").glob("*.yaml")):
        b = load_yaml(f)
        for it in b.get("items", []):
            it = dict(it)
            it.setdefault("category", b.get("category"))
            if it.get("category_override"):
                it["category"] = it["category_override"]
            it["_file"] = str(f)
            w.bulk.append(it)
    for f in sorted((prose / "notes").glob("*.md")):
        w.note_bodies[f.name] = f.read_text(encoding="utf-8")
    return w
