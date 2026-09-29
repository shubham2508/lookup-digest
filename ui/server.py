"""A small local web app over the run artifacts.

GET  /                         the page (ui/index.html)
GET  /api/runs                 every run under runs/: world, dir, as_of, suffix, summary from run.json
GET  /api/run?dir=…&artifact=… one artifact of one run (jsonl → list, json → object, md → {"text"})
GET  /api/worlds               worlds under data/ with the dates their inbox spans
GET  /api/reports              eval/reports/*.md names; ?name=… returns one report's text
POST /api/launch               {"action": run|baseline|eval|matrix|simulate|generate, "world", "as_of", "variant",
                               "customize", "tag"} → starts one `digest …` command
GET  /api/launch               state of the last launch: running, returncode, log tail

One run at a time: two pipelines on one machine contend for the LLM cache and the store, so a second launch
while one is running is refused (409).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from digest.paths import DATA_DIR, ROOT, RUNS_DIR
from digest.runs import ARTIFACTS

STATIC = Path(__file__).parent / "index.html"
REPORTS_DIR = ROOT / "eval" / "reports"
JSONL_ARTIFACTS = {name for name, fn in ARTIFACTS.items() if fn.endswith(".jsonl")}
MAX_JSONL_ROWS = 5000


class Launch:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.args: list[str] = []
        self.log: Path = RUNS_DIR / "_ui" / "launch.log"
        self.started: str | None = None
        self.lock = threading.Lock()

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, args: list[str]) -> dict:
        with self.lock:
            if self.running():
                return {"ok": False, "error": "a run is already in progress; one pipeline at a time"}
            self.log.parent.mkdir(parents=True, exist_ok=True)
            out = open(self.log, "w", encoding="utf-8")  # noqa: SIM115 - the process owns the handle
            self.proc = subprocess.Popen([sys.executable, "-m", "cli.main", *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
            self.args = args
            self.started = datetime.now().isoformat(timespec="seconds")
            return {"ok": True, "pid": self.proc.pid, "args": args}

    @staticmethod
    def external_busy() -> bool:
        """A pipeline started outside the UI (a matrix in a terminal) is running: launching now would collide."""
        try:
            r = subprocess.run(["pgrep", "-fl", "digest eval --matrix|cli.main run|cli.main simulate"], capture_output=True, text=True, timeout=5)
        except Exception:  # noqa: BLE001 - no pgrep: don't block
            return False
        # a shell whose command line merely quotes the pattern (a watcher loop, a grep) is not a pipeline
        procs = [ln for ln in r.stdout.splitlines() if ln.strip() and not re.search(r"\b(zsh|bash|sh) -c\b|\bpgrep\b|\bgrep\b", ln)]
        return bool(procs)

    def status(self) -> dict:
        tail = ""
        if self.log.exists():
            tail = self.log.read_text(encoding="utf-8", errors="replace")[-4000:]
        return {"running": self.running(), "external_busy": (not self.running()) and self.external_busy(),
                "returncode": None if self.proc is None else self.proc.poll(),
                "args": self.args, "started": self.started, "log": tail}


LAUNCH = Launch()


def _run_summary(run_dir: Path) -> dict:
    try:
        r = json.loads((run_dir / ARTIFACTS["run"]).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a half-written run still lists
        r = {}
    return {
        "as_of": r.get("as_of"), "variant": r.get("variant"), "suffix": r.get("suffix"), "customize": r.get("customize"),
        "baseline": r.get("baseline", False), "tag": r.get("tag"), "cost_usd": r.get("cost_usd"), "llm_calls": r.get("llm_calls"),
        "llm_cached": r.get("llm_cached"), "degradations": r.get("degradations"), "wall_s": r.get("wall_s"),
        "items": (r.get("reduce") or {}).get("items"), "placed": (r.get("compose") or {}).get("placed"),
        "violations": len(((r.get("verify") or {}).get("violations")) or []), "header": r.get("header"),
        "has_trace": (run_dir / ARTIFACTS["trace"]).exists(), "has_digest": (run_dir / ARTIFACTS["digest"]).exists(),
    }


def list_runs(runs_dir: Path | None = None) -> list[dict]:
    base = runs_dir or RUNS_DIR
    out = []
    if not base.exists():
        return out
    run_dirs = [p for p in base.rglob("*") if p.is_dir() and ((p / ARTIFACTS["run"]).exists() or (p / ARTIFACTS["digest"]).exists())]
    for world_dir in sorted(run_dirs):
        rel = world_dir.relative_to(base)
        world = str(rel.parent)
        out.append({"world": world, "name": rel.name, "dir": str(rel), **_run_summary(world_dir)})
    out.sort(key=lambda r: (r["world"], r["name"]))
    return out


def read_artifact(rel_dir: str, artifact: str, runs_dir: Path | None = None) -> tuple[int, object]:
    base = (runs_dir or RUNS_DIR).resolve()
    if artifact not in ARTIFACTS:
        return 400, {"error": f"unknown artifact {artifact!r}; one of {sorted(ARTIFACTS)}"}
    run_dir = (base / rel_dir).resolve()
    if base not in run_dir.parents and run_dir != base:
        return 400, {"error": "run dir outside runs/"}
    path = run_dir / ARTIFACTS[artifact]
    if not path.exists():
        return 404, {"error": f"{ARTIFACTS[artifact]} not present in this run"}
    text = path.read_text(encoding="utf-8", errors="replace")
    if artifact in JSONL_ARTIFACTS:
        rows = []
        for line in text.splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    rows.append({"_unparsed": line[:500]})
            if len(rows) >= MAX_JSONL_ROWS:
                break
        return 200, rows
    if path.suffix == ".json":
        try:
            return 200, json.loads(text)
        except json.JSONDecodeError as e:
            return 200, {"_unparsed": text[:2000], "error": str(e)}
    return 200, {"text": text}


WORLD_MANIFESTS = {"dev": ROOT / "eval" / "manifests" / "dev.yaml", "heldout": ROOT / "eval" / "manifests" / "heldout.yaml",
                   "tests/fixtures/mini": ROOT / "tests" / "fixtures" / "mini" / "manifest.yaml"}
WORLD_LABELS = {"dev": "dev: tune and try things here", "heldout": "heldout: final score only, never tune",
                "tests/fixtures/mini": "mini: 7-email fixture, quick check"}


def list_worlds(data_dir: Path | None = None) -> list[dict]:
    """Worlds with the mornings their answer key covers (manifest meta: anchor = day 30, run_days)."""
    from datetime import date, timedelta

    import yaml

    out = []
    for world, mpath in WORLD_MANIFESTS.items():
        ddir = (ROOT / world) if "/" in world else (data_dir or DATA_DIR) / world
        if not ddir.is_dir() or not mpath.exists():
            continue
        try:
            with open(mpath, encoding="utf-8") as f:
                meta = (yaml.safe_load(f) or {}).get("meta", {})
            anchor = meta["anchor"] if isinstance(meta["anchor"], date) else date.fromisoformat(str(meta["anchor"]))
            days = meta.get("run_days") or [26, 27, 28, 29, 30]
        except Exception:  # noqa: BLE001 - a broken manifest just hides the dates
            anchor, days = None, []
        mornings = []
        for d in days:
            if anchor is None:
                break
            day = anchor - timedelta(days=30 - int(d))
            mornings.append({"as_of": f"{day.isoformat()}T06:00", "label": f"{day.strftime('%a %d %b %Y')} · day {d}"})
        emails = len(list((ddir / "inbox").glob("*.eml"))) if (ddir / "inbox").exists() else 0
        out.append({"world": world, "label": WORLD_LABELS.get(world, world), "emails": emails, "mornings": mornings})
    return out


def list_customize() -> list[dict]:
    """Preset customize prompts: path, short name, and the one-line text (so the UI can show and edit it)."""
    d = ROOT / "profile" / "customize"
    out = []
    for p in sorted(d.glob("*.md")) if d.exists() else []:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        out.append({"path": f"profile/customize/{p.name}", "name": p.stem.replace("_", " "), "text": text})
    return out


def save_custom_prompt(text: str) -> str:
    """A one-line instruction typed in the UI becomes runs/_ui/customize/<slug>.md, passed to --customize."""
    import hashlib
    import re

    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24].strip("-") or "custom"
    name = f"{words}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"
    path = RUNS_DIR / "_ui" / "customize" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return str(path.relative_to(ROOT))


def _store(world: str):
    import sqlite3

    from digest.config import load_settings

    path = ROOT / load_settings().store.path_template.format(world=world)
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def thread_subjects(world: str) -> dict:
    """thread_id → {subject, from, first} for readable labels."""
    con = _store(world)
    if con is None:
        return {}
    try:
        rows = con.execute("SELECT thread_id, subject, from_addr, MIN(sent_at) AS first FROM messages GROUP BY thread_id").fetchall()
        return {r["thread_id"]: {"subject": r["subject"], "from": r["from_addr"], "first": r["first"]} for r in rows}
    finally:
        con.close()


def read_source(world: str, sid: str) -> tuple[int, dict]:
    """The original text behind a citation: thread:/msg: → the email thread, note: → the note, task: → tasks.md,
    event: → the calendar event."""
    from digest.paths import data_dir

    con = _store(world)
    try:
        if sid.startswith(("thread:", "msg:")):
            if con is None:
                return 404, {"error": "no store for this world; run a digest first"}
            tid = sid
            if sid.startswith("msg:"):
                r = con.execute("SELECT thread_id FROM messages WHERE message_id=?", (sid[4:],)).fetchone()
                if r is None:
                    return 404, {"error": "message not in the store"}
                tid = r["thread_id"]
            msgs = []
            for r in con.execute("SELECT data FROM messages WHERE thread_id=? ORDER BY sent_at", (tid,)):
                m = json.loads(r["data"])
                msgs.append({"id": m.get("message_id"), "from": f'{m.get("from_name") or ""} <{m.get("from_addr")}>'.strip(),
                             "to": ", ".join(m.get("to") or []), "sent_at": m.get("sent_at"), "subject": m.get("subject"),
                             "body": m.get("body_new") or "", "forwarded_by": m.get("forwarded_by")})
            return 200, {"kind": "thread", "thread_id": tid, "messages": msgs, "highlight": sid[4:] if sid.startswith("msg:") else None}
        if sid.startswith("note:"):
            rel, _, line = sid[5:].partition("#L")
            path = data_dir(world) / rel
            if not path.exists():
                return 404, {"error": f"{rel} not found"}
            return 200, {"kind": "note", "path": rel, "text": path.read_text(encoding="utf-8", errors="replace"),
                         "line": int(line) if line.isdigit() else None}
        if sid.startswith("task:"):
            path = data_dir(world) / "tasks.md"
            return 200, {"kind": "tasks", "path": "tasks.md", "text": path.read_text(encoding="utf-8") if path.exists() else ""}
        if sid.startswith("event:"):
            if con is None:
                return 404, {"error": "no store"}
            r = con.execute("SELECT data FROM events WHERE uid=? LIMIT 1", (sid[6:],)).fetchone()
            return (200, {"kind": "event", "event": json.loads(r["data"])}) if r else (404, {"error": "event not in store"})
        return 400, {"error": "unknown source id"}
    finally:
        if con is not None:
            con.close()


VARIANT_WORDS = {"stale_inbox": "inbox 30h stale", "no_notes": "notes missing", "corrupt_ics": "work calendar broken"}


def _step_words(args: list[str]) -> str:
    """Plain words for one matrix step."""
    a = args
    if a[0] == "baseline":
        return "naive baseline (one LLM call)"
    if a[0] == "simulate":
        return "5-day simulation (simulated Avery answers cards)"
    if a[0] == "eval":
        return "score everything → report"
    at = a[a.index("--as-of") + 1] if "--as-of" in a else ""
    try:
        day = datetime.fromisoformat(at).strftime("%a %d %b")
    except ValueError:
        day = at
    if "--variant" in a:
        return f"{day} · broken data: {VARIANT_WORDS.get(a[a.index('--variant') + 1], a[a.index('--variant') + 1])}"
    if "--customize" in a:
        return f"{day} · customize: {Path(a[a.index('--customize') + 1]).stem.replace('_', ' ')}"
    return f"{day} · normal digest"


def matrix_progress(world: str) -> dict:
    """Progress of the latest full matrix for a world, from its log: the planned steps in plain words, which are
    done / failed, which one is running. Works for a matrix started from a terminal or from this page."""
    import re

    from eval.integrate import plan
    from eval.manifest_schema import load_manifest

    mpath = WORLD_MANIFESTS.get(world)
    if not mpath or not mpath.exists():
        return {"world": world, "steps": [], "active": False}
    steps = plan(world, load_manifest(mpath))
    logs = [p for p in (RUNS_DIR / world / "matrix.log", LAUNCH.log) if p.exists()]
    if LAUNCH.log in logs and not (LAUNCH.args[:2] == ["eval", "--matrix"] and world in LAUNCH.args):
        logs.remove(LAUNCH.log)
    status: dict[int, str] = {}
    if logs:
        log = max(logs, key=lambda p: p.stat().st_mtime)
        for m in re.finditer(r"^\[\s*(\d+)/(\d+)\]\s+(\w+)", log.read_text(encoding="utf-8", errors="replace"), re.M):
            status[int(m.group(1))] = m.group(3)
    active = LAUNCH.running() or Launch.external_busy()
    out = []
    for i, s in enumerate(steps, 1):
        st = status.get(i, "pending")
        out.append({"n": i, "words": _step_words(s.args), "status": st})
    if active:
        nxt = next((x for x in out if x["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "running"
    return {"world": world, "steps": out, "active": active and bool(status), "total": len(out),
            "done": sum(1 for x in out if x["status"] in ("ok", "failed", "blocked", "skipped"))}


def list_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    return [{"name": p.name, "size": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)]


def read_report(name: str) -> tuple[int, dict]:
    path = (REPORTS_DIR / name).resolve()
    if REPORTS_DIR.resolve() not in path.parents or not path.exists() or path.suffix != ".md":
        return 404, {"error": "no such report"}
    return 200, {"name": name, "text": path.read_text(encoding="utf-8", errors="replace")}


ACTIONS = ("run", "baseline", "eval", "matrix", "simulate", "generate")


def launch_args(body: dict) -> list[str] | None:
    """Turn a launch request into `digest …` CLI args. action: run (default) | baseline | eval | matrix | simulate | generate."""
    world = (body.get("world") or "").strip()
    action = (body.get("action") or ("baseline" if body.get("baseline") else "run")).strip()
    if not world or action not in ACTIONS:
        return None
    as_of = (body.get("as_of") or "").strip()
    if action == "baseline":
        return ["baseline", "--world", world] + (["--as-of", as_of] if as_of else [])
    if action == "eval":
        return ["eval", "--world", world, "--customize-suite", "--baseline"]
    if action == "matrix":
        return ["eval", "--matrix", "--world", world, "--keep-going"]
    if action == "simulate":
        return ["simulate", "--world", world, "--days", str(int(body.get("days") or 5)), "--fresh"]
    if action == "generate":
        return ["generate", "--world", world]
    args = ["run", "--world", world]
    for key, flag in (("as_of", "--as-of"), ("variant", "--variant"), ("customize", "--customize"), ("tag", "--tag")):
        v = (body.get(key) or "").strip()
        if v:
            args += [flag, v]
    return args


class Handler(BaseHTTPRequestHandler):
    runs_dir: Path | None = None  # overridable in tests

    def _json(self, code: int, obj: object) -> None:
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/", "/index.html"):
            data = STATIC.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/runs":
            self._json(200, list_runs(self.runs_dir))
        elif u.path == "/api/run":
            code, obj = read_artifact(q.get("dir", ""), q.get("artifact", ""), self.runs_dir)
            self._json(code, obj)
        elif u.path == "/api/worlds":
            self._json(200, list_worlds())
        elif u.path == "/api/customize":
            self._json(200, list_customize())
        elif u.path == "/api/progress":
            self._json(200, matrix_progress(q.get("world", "dev")))
        elif u.path == "/api/subjects":
            self._json(200, thread_subjects(q.get("world", "dev")))
        elif u.path == "/api/source":
            code, obj = read_source(q.get("world", "dev"), q.get("id", ""))
            self._json(code, obj)
        elif u.path == "/api/reports":
            if "name" in q:
                code, obj = read_report(q["name"])
                self._json(code, obj)
            else:
                self._json(200, list_reports())
        elif u.path == "/api/launch":
            self._json(200, LAUNCH.status())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        if u.path == "/api/launch":
            text = (body.get("customize_text") or "").strip()
            if text and not (body.get("customize") or "").strip():
                body["customize"] = save_custom_prompt(text)
            args = launch_args(body)
            if args is None:
                self._json(400, {"error": "world is required"})
                return
            res = LAUNCH.start(args)
            self._json(200 if res.get("ok") else 409, res)
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:  # quiet
        pass


def make_server(host: str = "127.0.0.1", port: int = 8765, runs_dir: Path | None = None) -> ThreadingHTTPServer:
    Handler.runs_dir = runs_dir
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    srv = make_server(host, port)
    url = f"http://{host}:{port}/"
    print(f"digest ui: {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
