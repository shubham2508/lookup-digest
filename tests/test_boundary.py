"""CLAUDE.md rule 2: the digest package must never read world/ or eval/ (or generator/)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = ROOT / "digest"
FORBIDDEN_PKGS = {"generator", "world", "eval"}
PATH_RE = re.compile(r"(?<![\w.<-])(generator|world|eval)[/\\]")


def test_digest_never_imports_or_opens_generator_world_or_eval():
    offenders: list[str] = []
    for py in sorted(DIGEST.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        rel = py.relative_to(ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in FORBIDDEN_PKGS:
                        offenders.append(f"{rel}:{node.lineno}: import {a.name}")
            elif (isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                  and node.module.split(".")[0] in FORBIDDEN_PKGS):
                offenders.append(f"{rel}:{node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and PATH_RE.search(node.value):
                offenders.append(f"{rel}:{node.lineno}: string {node.value[:60]!r}")
    assert not offenders, "digest/ touches forbidden folders:\n" + "\n".join(offenders)


def test_boundary_scanner_catches_violations(tmp_path):
    """The scanner itself must work, or the rule above is a no-op."""
    bad = tmp_path / "bad.py"
    bad.write_text("import eval\nfrom generator import x\np = open('world/dev/world.yaml')\n")
    tree = ast.parse(bad.read_text())
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in FORBIDDEN_PKGS for a in node.names) or isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_PKGS or isinstance(node, ast.Constant) and isinstance(node.value, str) and PATH_RE.search(node.value):
            hits += 1
    assert hits == 3
