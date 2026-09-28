# Handoffs

One Claude Code session per track, all on `main` in this directory. Start a session with one line, e.g.
**"Track B, M2"**, and the session reads, in order: `CLAUDE.md` → its handoff doc here → its read list.

| Track | Doc | Owns | Milestones |
|---|---|---|---|
| A · Product | [A-product.md](A-product.md) | `digest/`, `prompts/` (P1–P6), `tests/test_a_*.py` | M3 → M4 → M5, later M7 · M8 · M9 halves |
| B · Data | [B-data.md](B-data.md) | `world/`, `generator/`, `data/`, `eval/manifests/`, `tests/test_b_*.py` | M1 (gate) → M2, later held-out (M8) |
| C · Grader | [C-grader.md](C-grader.md) | `eval/` (except manifests), `prompts/judge.md`, `profile/customize/`, `tests/test_c_*.py` | M6, later M7 · M8 · M9 halves |
| Orchestrator | (this session) | everything shared: `digest/schemas.py`, `digest/llm.py`, `digest/runs.py`, `digest/store.py`, `digest/config.py`, `eval/manifest_schema.py`, `cli/`, `config/`, docs | M0, integration, M10 |

Progress and blockers go in [STATUS.md](STATUS.md). Questions go in `OPEN_QUESTIONS.md` and the session stops there.
