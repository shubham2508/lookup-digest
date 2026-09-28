# Eval history

One line per prompt change (CLAUDE.md rule 10): date · prompt · version · headline metrics before → after.

| date | prompt | version | P0 recall | traps passed | must-not rate | one-thing acc | cost/run | note |
|---|---|---|---|---|---|---|---|---|
| 2026-09-28 | profile_compiler | v2 | — | — | — | — | — | A M3: notes verbatim from the bullet, read windows as HH:MM; no dev data yet (fixture smoke only) |
| 2026-09-28 | extractor | v1 | — | — | — | — | ≈$0.01 (fixture) | A M3: first version; 19/19 quotes verified on the fixture |
| 2026-09-28 | triage | v2 | — | — | — | — | — | A M5: v1→v2 explicit ambiguity.default + one result per id (after the llm.py `_strip` fix); fixture: 0 invalid packs |
| 2026-09-28 | compose · materializer · customize_compiler · baseline | v1 | — | — | — | — | ≈$0.005–0.02/run (fixture) | A M5/M7/M8: first versions; `digest eval --world dev` pending Track B's data |
