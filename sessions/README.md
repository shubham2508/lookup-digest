# sessions/

Exported Claude Code transcripts. The graders asked to see how the AI was used, so export as you go, one file per working session.

## How to export

In Claude Code (terminal or VS Code), run:

```
/export sessions/<track>_<milestone>.txt      e.g. sessions/B-data_M2.txt, sessions/orchestrator_M0.txt
```

`/export` writes a plain-text, human-readable transcript. Do not copy the raw `~/.claude/projects/<project>/<session-id>.jsonl` files in here: that format is internal to Claude Code and changes between releases.

## Before committing an export

`/export` does not redact anything. Tool output and file contents appear as-is, so search each export for secrets before it is committed:

```
grep -nE 'github_pat_|sk-or-|OPENROUTER_API_KEY=[^ ]|x-access-token' sessions/*.txt
```

Known case: the 2026-09-28 setup session ran `git remote -v`, whose output included the GitHub token that was embedded in the remote URL at the time. Scrub that line before committing the export.
