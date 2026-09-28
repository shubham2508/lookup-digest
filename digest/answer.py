"""`digest answer Q<n> <option> --world <w>` (M9): turns an answered question card into a ruling (architecture §10,
OPEN_QUESTIONS #13a): runs/<world>/rulings.yaml plus the store's `rulings` table. The next run's triage sees it."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings, load_settings
from .history import make_ruling, rulings_path, save_ruling
from .paths import ROOT
from .runs import ARTIFACTS
from .store import Store

_Q_RE = re.compile(r"^Q(\d+)\s*·\s*(.*?)\s*(?:\(1\)|$)")


class NoSuchQuestion(Exception):
    pass


def latest_run_dir(world: str, settings: Settings) -> Path | None:
    store_p = ROOT / settings.store.path_template.format(world=world)
    base = store_p.parent
    if store_p.exists():
        with Store(store_p) as st:
            rows = [r for r in st.query("runs", "world=?", (world,), order="as_of DESC") if not r.get("variant") and not r.get("customize") and not r.get("baseline")]
        for r in rows:
            d = base / r["run_id"].split("/", 1)[1]
            if (d / ARTIFACTS["actions"]).exists():
                return d
    if base.is_dir():
        cands = sorted((d for d in base.iterdir() if d.is_dir() and "_" not in d.name and (d / ARTIFACTS["actions"]).exists()), reverse=True)
        return cands[0] if cands else None
    return None


def find_question(run_dir: Path, question_id: str) -> tuple[dict, dict]:
    """→ (the question's MaterializedAction row, its reduce item)"""
    n = question_id.upper().lstrip("Q")
    for line in (run_dir / ARTIFACTS["actions"]).read_text(encoding="utf-8").splitlines():
        a = json.loads(line)
        if a.get("type") != "question":
            continue
        m = _Q_RE.match(a.get("text", ""))
        if m and m.group(1) == n:
            reduce = json.loads((run_dir / ARTIFACTS["reduce"]).read_text(encoding="utf-8"))
            item = next((it for it in reduce["items"] if it["id"] == a["item_id"]), {})
            amb = item.get("ambiguity") or {}
            return a, {"about": item.get("about"), "entities": item.get("entities", []), "candidate_types": item.get("candidate_types", []),
                       "question": amb.get("question") or m.group(2), "options": amb.get("options") or []}
    raise NoSuchQuestion(f"no question {question_id.upper()} in {run_dir}")


def answer(question_id: str, option: int, world: str, settings: Settings | None = None, now: datetime | None = None) -> dict:
    settings = settings or load_settings()
    run_dir = latest_run_dir(world, settings)
    if run_dir is None:
        raise NoSuchQuestion(f"no digest run found for world {world!r}; run `digest run --world {world}` first")
    action, item = find_question(run_dir, question_id)
    if item["options"] and not 1 <= option <= len(item["options"]):
        raise NoSuchQuestion(f"{question_id.upper()} has {len(item['options'])} options; {option} is out of range")
    created = now or datetime.now(ZoneInfo(settings.timezone)).replace(microsecond=0)
    ruling = make_ruling(question_id.upper(), option, item, action.get("text", ""), created)
    ruling["run_dir"] = str(run_dir)
    save_ruling(rulings_path(world, settings), ruling)
    with Store(ROOT / settings.store.path_template.format(world=world)) as st:
        st.upsert("rulings", {"id": ruling["id"], "ruling": ruling["ruling"], "option_chosen": option, "from_question": ruling["from_question"],
                              "created": ruling["created"], "expires": ruling["expires"], "scope": ruling["scope"], "world": world})
        st.commit()
    return ruling
