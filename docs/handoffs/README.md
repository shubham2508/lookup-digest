# Handoffs

One Claude Code session per track, started with one line ("Track A, v2"); the session reads `CLAUDE.md`, then its
handoff doc here, then its read list. Questions go in `OPEN_QUESTIONS.md`; progress and blockers in [STATUS.md](STATUS.md);
the entry point for the next orchestrator session is [NEXT-SESSION.md](NEXT-SESSION.md).

| Track | Handoff | Report |
|---|---|---|
| A · Readers (raw threads → Findings; pipeline) | [v2-A-readers.md](v2-A-readers.md) | [v2-A-STATUS.md](v2-A-STATUS.md), gate evidence [v2-A-checkpoint.md](v2-A-checkpoint.md) |
| B · Spine, retrieval, sweeps, safety nets, reconcile | [v2-B-spine.md](v2-B-spine.md) | [v2-B-STATUS.md](v2-B-STATUS.md) |
| C · Eval (diagnostics, v1/v2/baseline table, judge export) | [v2-C-eval.md](v2-C-eval.md) | [v2-C-STATUS.md](v2-C-STATUS.md) |
| Orchestrator | `MIGRATION_PLAN.md`, shared contracts (`digest/schemas.py`, `digest/findings.py`, `digest/llm.py`, `config/`) | [STATUS.md](STATUS.md) |

The v1 build (extraction-centric: tracks A product, B data, C grader; milestones M0–M10) and its handoffs are in the
tag `v1-extraction-centric`; the session transcripts for both builds are in `sessions/`.
