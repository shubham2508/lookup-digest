# Eval history

One line per prompt change (CLAUDE.md rule 10): date · prompt · version · headline metrics before → after.

| date | prompt | version | P0 recall | traps passed | must-not rate | one-thing acc | cost/run | note |
|---|---|---|---|---|---|---|---|---|
| 2026-09-28 | profile_compiler | v2 | — | — | — | — | — | A M3: notes verbatim from the bullet, read windows as HH:MM; no dev data yet (fixture smoke only) |
| 2026-09-28 | extractor | v1 | — | — | — | — | ≈$0.01 (fixture) | A M3: first version; 19/19 quotes verified on the fixture |
| 2026-09-28 | triage | v2 | — | — | — | — | — | A M5: v1→v2 explicit ambiguity.default + one result per id (after the llm.py `_strip` fix); fixture: 0 invalid packs |
| 2026-09-28 | compose · materializer · customize_compiler · baseline | v1 | — | — | — | — | ≈$0.005–0.02/run (fixture) | A M5/M7/M8: first versions; `digest eval --world dev` pending Track B's data |
| 2026-09-28 | extractor | v1 | — | — | — | — | — | first real dev run; baseline for later changes |
| 2026-09-28 | triage | v2 → v4 | 91.7% → 100% | 114/175 → 120/175 | 4.7% → 5.9% | 100% → 50% | $0.040 → $0.049 | before→after spans code fixes too (Tuesday crash, P0 restore), not only the prompt. Changes: quiet-threshold rule (S3), dev notifications/RSVP/generic news excluded, co-founder email and team escalation → P0 |
| 2026-09-28 | compose | v1 → v3 | (same runs) | | | | | one thing = one item; cut from the bottom; today's hard deadline preferred. One-thing accuracy fell: see DESIGN.md |
| 2026-09-28 | extractor · triage · compose · materializer · linker · topic_grouper | v1→2 · v4→5 · v3→4 · v1→2 · v1→2 · v1→2 | (next report) | | | | | leak removed: examples copied dev storylines (S1 cap table, S2 diligence move, S3/S10 $3.4M, S5 Oct 6, S8 Mei, S13 DeepSeek); now a made-up cast in no mailbox. Triage's 'Sam and Wren' rule → 'contacts whose category is family'. Scores before this line were measured with the leak. |
