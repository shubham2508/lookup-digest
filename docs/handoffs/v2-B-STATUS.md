# v2 · Track B · status

**2026-09-29 · B1–B5 done, integrated with main (A and C already merged) on branch `v2-b-spine`, suite green.**
Decisions taken unattended: `OPEN_QUESTIONS.md` #22 (a–i). Ready for the orchestrator's merge.

## Landed

| Deliverable | Where | Notes |
|---|---|---|
| B1 spine | `digest/compute/contacts.py`, `prompts/signature_parser.md` v1, `prompts/contact_classifier.md` v2 | `build_contacts(world, profile, linker, llm, ctx)`. Profile (email or exact name) → internal domain → automated → classifier (LLM, one cached call per contact with mail; input = parsed signature, domain, same-domain profile contacts, role rules, ≤5 messages, all-visible stats: no run date, so it re-runs only on new evidence) → role-at-org by the linker (signature title/org + the classifier's reason) → learned domain as fallback → org-tier inheritance (moved here) → behavior stats. Signature fields and classifier quotes are checked against their source; stage checked against the category's vocabulary. `ContactDirectory.signatures` / `.classifications` keep the raw outputs. Dev: 138 contacts, 5 unresolved; recruiters, family, candidates, investors, deal counsel all right on inspection. |
| B2 retrieval | `digest/compute/context.py` `retrieve()`, `ContextRef` | events ±7 d with the same people or org, note lines (±1, with `L<n>`) and tasks mentioning a participant, org or subject word, the two related threads with the same people ranked by subject-word overlap (before or after the thread), first + last message verbatim; ~4k-token cap, most relevant first. Word overlap here only. Fixes checkpoint problem #1: thread 5's false "overdue feedback" finding is gone in the integrated run. |
| B3 sweeps | `digest/compute/sweeps.py`, `prompts/calendar_sweep.md` v1, `notes_tasks_sweep.md` v2, `news_sweep.md` v2 | `run_sweeps(world, directory, findings, profile, settings, llm, ctx, as_of)`; three calls in parallel, `cache_salt` = as_of date, batches at ~60k tokens; code hands over the date math (day labels, overdue days, overlaps with other events and deep-work blocks, the weekdays after each note's date); citations checked per sweep (`event:` quotes are titles). Dev Thursday: calendar 3 (Lumen deep work, Wren collision, the moved IPV call now colliding with Monday's leadership sync), notes 5 (overdue monthly update with stale ARR $3.2M vs $3.4M, Plant Bundle sign-off, Lumen vs Metrika, SOC 2 task already done, profile drift), news 3 (Halberd and Northstar case studies at MX Summit, DeepSeek-V4 Pro −30% against Priya's inference-spend decision), no decoys. |
| B4 safety nets | `digest/compute/candidates.py` (1010 → 502 lines) | `safety_nets(ci) -> list[Finding]`, `ComputeInputs(world, profile, settings, as_of, directory, findings=…)`. Kept: waiting on Avery (capital ≥ 3 business days → `quiet_thread`; other P0 → `reply_owed`; a teammate's reply counts), reference customer past end of day, deep work, family (personal-domain events), double booking, recruiter pattern, stale source (`needs_avery: no`), suspicious (reader-reported + code guard, never P0, no action), automated requests. Each `why` starts with the computed fact. Deleted: every extraction rule, `aboutkeys.py`. |
| B5 reconcile + merge | `digest/compute/merge.py`, `linker.py` (task `net_covers_finding`) | `reconcile(findings, nets, linker, *, msg_thread=None, summaries=None, ignore_entities=(), log=None)`: a waiting net on a thread the reader read is covered by that reading (attached to a same-thread finding, or closed as judged; #22a); every other net goes to the linker with options narrowed and labelled by hard facts ([same message] / [same event] / [same thread] / [same person]); decisions go to `links.jsonl`. `group_findings(findings, linker)` (same-kind about tags via `Linker.group_topics`), `apply_merges`, `thread_of`, `net_fact`. Dev Thursday: 22 nets → 8 attached, 6 closed by the reader, 6 by the linker, 3 rescues (TalentBridge pattern, Ramp ×3, Stripe payout). |
| Driver | `python -m digest.compute.sweeps --world dev --as-of 2026-09-24T06:00 [--findings runs/…/findings.jsonl]` | prints contacts by category, nets, sweep findings, reconcile decisions and rescues; reads reader summaries from the run's `trace.jsonl`. |

Tests: `tests/test_b_compute.py` (28: formulas, spine resolution order, classifier input (evidence not names, stable
across mornings), signature/classifier checks, fixture nets, retrieval ×2, every net, reconcile ×4, merge),
`tests/test_b_sweeps.py` (6: inputs of each sweep, batching, citation check + origin + salt, end to end on the fake
client), `tests/b_fakes.py` (fake answers for the three new schemas; `a_fakes.FakeClient` routes to it). `tests/test_a_compute.py`
deleted (its formula tests moved). Full suite green after merging main.

## Cost

Dev Thursday, cold: spine ≈ $0.03 (52 signature + 63 classifier calls), sweeps ≈ $0.01–0.02, linker < $0.01. Integrated
`digest run` on this branch: $0.27 cold (readers $0.24 of it, cache cold because retrieval changed their input), $0.01
warm. Total spent this session ≈ $0.40.

## For the orchestrator (merge notes)

- Branch contains `Merge branch 'main' into v2-b-spine` (conflicts in `compute/__init__.py` and `test_a_stages.py`
  resolved to main's) and one commit touching A-owned files, labelled "integration" (#22g): review or revert.
- **Reduce (#22h):** identical coarse keys across threads are not joined (`meeting:ipv-diligence-call` on 4 findings
  and `family:wren-pediatrician-2026-09-24` on 2 in the dev digest), and `group_findings` merges only take effect on
  qualified keys. Cross-kind duplicates (Priya's backfill cap: `approval:inference-spend-plan` vs
  `other:backfill-concurrency-cap`) are not compared at all (same-kind rule from the handoff). Suggest: reduce joins
  identical v2 keys that share an entity, and every key pair in `comp.about_merges`.
- `eval/history.md` needs a line for the new prompt versions (#22i), with the P6 run.
- `digest run` on dev Thursday: 547 → 396 words after the reconcile fix, still over the 350 budget (compose).
- Heldout was not run (no tuning on it; #20: API spend only for producing digests).
