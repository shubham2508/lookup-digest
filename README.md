# lookup-digest

Daily Digest: a personal triage tool that produces a one-page 6:00am PT digest for "Avery Chen" from synthetic
email, calendar, notes, and tasks. This is the myRico work trial; the build is in progress. Start with `CLAUDE.md`.

## Quickstart (M0)

```
uv sync --all-groups            # Python 3.12, deps, editable install
cp .env.example .env            # then paste OPENROUTER_API_KEY
uv run pytest                   # foundation tests
uv run digest --help            # the CLI; most commands are stubs until their track lands
uv run digest llm-check         # one live structured call through OpenRouter, cached and costed
```

The one-page install-and-run README replaces this file at milestone M10.
