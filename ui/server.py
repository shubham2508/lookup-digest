"""A small local web app over the run artifacts.

GET  /                         the page (ui/index.html)
GET  /api/runs                 every run under runs/: world, dir, as_of, suffix, summary from run.json
GET  /api/run?dir=…&artifact=… one artifact of one run (jsonl → list, json → object, md → {"text"})
GET  /api/worlds               worlds under data/ with the dates their inbox spans
GET  /api/reports              eval/reports/*.md names; ?name=… returns one report's text
POST /api/launch               {"world", "as_of", "variant", "customize", "tag", "baseline"} → starts one `digest run`
GET  /api/launch               state of the last launch: running, returncode, log tail

One run at a time: two pipelines on one machine contend for the LLM cache and the store, so a second launch
while one is running is refused (409).
"""
from __future__ import annotations

import json
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

    def status(self) -> dict:
        tail = ""
        if self.log.exists():
            tail = self.log.read_text(encoding="utf-8", errors="replace")[-4000:]
        return {"running": self.running(), "returncode": None if self.proc is None else self.proc.poll(),
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


def list_worlds(data_dir: Path | None = None) -> list[dict]:
    base = data_dir or DATA_DIR
    out = []
    if not base.exists():
        return out
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        inbox = d / "inbox"
        dates: list[str] = []
        if inbox.exists():
            for f in inbox.glob("*.eml"):
                # file names start with the date the generator used; fall back to the Date header
                head = f.name[:10]
                if len(head) == 10 and head[4] == "-" and head[7] == "-":
                    dates.append(head)
        dates = sorted(set(dates))
        out.append({"world": d.name, "emails": len(list(inbox.glob("*.eml"))) if inbox.exists() else 0,
                    "first_day": dates[0] if dates else None, "last_day": dates[-1] if dates else None,
                    "suggested_as_of": [f"{x}T06:00" for x in dates[-5:]] if dates else []})
    return out


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


def launch_args(body: dict) -> list[str] | None:
    world = (body.get("world") or "").strip()
    if not world:
        return None
    if body.get("baseline"):
        args = ["baseline", "--world", world]
        if body.get("as_of"):
            args += ["--as-of", body["as_of"].strip()]
        return args
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
