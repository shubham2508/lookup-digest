# prompts/

One file per LLM prompt, `<name>.md`, with a YAML front matter header (see `digest/prompts.py`).
Specs for each prompt are in `specs/prompts.md`; Track A writes P1–P6, Track C writes E1 (judge).
The generator prompts G1–G3 are not files here: the Data track's Claude Code session plays that role.

Rules: any change bumps `version`, runs the eval, and appends a line to `eval/history.md`.
`{{placeholder}}` is the variable syntax (double braces, so JSON examples stay literal).
