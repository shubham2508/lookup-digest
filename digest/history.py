"""Digest history and rulings (architecture §10; OPEN_QUESTIONS #13): digest_items rows per run, times_surfaced and
resolved_later across runs, rulings.yaml at runs/<world>/rulings.yaml mirrored into the store."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import yaml

from .paths import ROOT
from .schemas import Candidate, ComposeResult, ReduceItem
from .store import Store

RULING_TTL_DAYS = 90


def rulings_path(world: str, settings) -> Path:
    template = getattr(settings.store, "rulings_path_template", None) or "runs/{world}/rulings.yaml"
    return ROOT / template.format(world=world)


def load_rulings(path: Path, as_of: datetime) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for r in data.get("rulings", []) or []:
        exp = r.get("expires")
        if exp:
            try:
                if datetime.fromisoformat(str(exp)) < as_of:
                    continue
            except ValueError:
                pass
        out.append(r)
    return out


def save_ruling(path: Path, ruling: dict) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    rulings = data.get("rulings", []) or []
    rulings = [r for r in rulings if r.get("id") != ruling["id"]]
    rulings.append(ruling)
    data["rulings"] = rulings
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def prior_runs(store: Store, world: str, as_of: datetime, suffix_free: bool = True) -> list[dict]:
    rows = store.query("runs", "world=? AND as_of<?", (world, as_of.isoformat()), order="as_of")
    if suffix_free:
        rows = [r for r in rows if not r.get("variant") and not r.get("customize") and not r.get("baseline")]
    return rows


def times_surfaced(store: Store, world: str, as_of: datetime) -> dict[str, int]:
    """about key → number of prior digests (same world, earlier as_of, plain runs) that surfaced it and it stayed open."""
    runs = {r["run_id"]: r for r in prior_runs(store, world, as_of)}
    if not runs:
        return {}
    counts: dict[str, set[str]] = {}
    for row in store.query("digest_items"):
        if row["run_id"] in runs and row.get("surfaced") and not row.get("resolved_later"):
            counts.setdefault(row["about"], set()).add(row["run_id"])
    return {k: len(v) for k, v in counts.items()}


def mark_resolved(store: Store, world: str, as_of: datetime, current: list[Candidate]) -> int:
    """Prior surfaced items whose about key has no candidate today are resolved (reply sent, promise kept, task closed)."""
    runs = {r["run_id"] for r in prior_runs(store, world, as_of)}
    if not runs:
        return 0
    open_abouts = {c.about for c in current}
    n = 0
    for row in store.query("digest_items"):
        if row["run_id"] in runs and row.get("surfaced") and not row.get("resolved_later") and row["about"] not in open_abouts:
            row["resolved_later"] = 1
            row["resolved_at"] = as_of.isoformat()
            store.upsert("digest_items", row)
            n += 1
    store.commit()
    return n


def answered_after_digest(store: Store, world: str, as_of: datetime, cands: list[Candidate], threads) -> set[str]:
    """Candidate ids the digest already showed and Avery answered afterwards (an Avery message after that run's as_of)."""
    runs = prior_runs(store, world, as_of)
    if not runs:
        return set()
    shown: dict[str, datetime] = {}
    by_run = {r["run_id"]: datetime.fromisoformat(r["as_of"]) for r in runs}
    for row in store.query("digest_items"):
        if row["run_id"] in by_run and row.get("surfaced"):
            t = by_run[row["run_id"]]
            if row["about"] not in shown or t > shown[row["about"]]:
                shown[row["about"]] = t
    out: set[str] = set()
    for c in cands:
        if c.type not in ("reply_owed", "quiet_thread") or c.about not in shown:
            continue
        tid = c.facts.get("thread_id")
        t = threads.get(tid)
        if t and any(m.is_from_avery and m.sent_at > shown[c.about] for m in t.messages):
            out.add(c.candidate_id)
    return out


def record_items(store: Store, run_id: str, reduced: dict[str, ReduceItem], compose: ComposeResult, also_pending: list[str],
                 outside: list[str], actions_by_item: dict[str, list[str]], surfaced_counts: dict[str, int]) -> int:
    placed = set(([compose.one_thing_id] if compose.one_thing_id else []) + [i for s in compose.sections for i in s.item_ids])
    n = 0
    for iid, it in reduced.items():
        surfaced = 2 if iid in placed else 1 if iid in also_pending or iid in outside else 0
        store.upsert("digest_items", {
            "run_id": run_id, "item_id": iid, "about": it.about, "surfaced": surfaced, "section": it.section, "priority": it.priority,
            "resolved_later": 0, "times_surfaced": surfaced_counts.get(it.about, 0) + (1 if surfaced else 0),
            "actions": actions_by_item.get(iid, []), "candidate_types": it.candidate_types, "entities": it.entities,
            "one_thing": iid == compose.one_thing_id,
        })
        n += 1
    store.commit()
    return n


def make_ruling(question_id: str, option: int, item: dict, action_text: str, created: datetime) -> dict:
    """A ruling from an answered card: scope = the item's about key + first contact entity + candidate type."""
    options = item.get("options") or []
    chosen = options[option - 1] if 1 <= option <= len(options) else f"option {option}"
    scope = {"about": item.get("about")}
    if item.get("entities"):
        scope["contact"] = item["entities"][0]
    if item.get("candidate_types"):
        scope["thread_kind"] = item["candidate_types"][0]
    return {"id": f"R-{created.strftime('%Y%m%d')}-{question_id}", "scope": scope, "ruling": chosen, "option_chosen": option,
            "from_question": question_id, "question": item.get("question") or action_text, "created": created.isoformat(),
            "expires": (created + timedelta(days=RULING_TTL_DAYS)).isoformat()}
