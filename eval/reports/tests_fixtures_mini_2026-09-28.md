# Eval report · tests/fixtures/mini · 2026-09-28

Manifest world `mini`, anchor 2026-09-24 (day 30), run days [30]. P0 recall is the only gate; everything else is reported.

> 4 manifest item(s) have no message labels, so product evidence cannot be mapped to them and absence checks on them pass vacuously: nl-scbrief-212, auto-docusign-mei, mkt-rippleboard, t-sam-daycare

## 1. Summary

| metric | pipeline · dev |
|---|---|
| P0 recall (gate = 100%) | 0.667 ❌ |
| Trap assertions passed | 7/7 |
| Must-not rate | 0% |
| One-thing accuracy | 100% |
| Cost / run (USD) | 0.0123 |
| Runs scored | 1 |

Not run yet: pipeline · heldout, baseline · dev, baseline · heldout.

## 2. Per-stage metrics (eval.md §2)

Misses by attributed stage: extraction 5, compute 4, triage 3, materializer 1

### Day 30 · `tests/fixtures/mini_runs/2026-09-24T06-00`

**extraction**

| metric | value |
|---|---|
| type_accuracy | 0.333 |
| domain_accuracy | 100% |
| intent_primary_accuracy | 100% |
| ball_awaiting_accuracy | 100% |
| closed_by_courtesy_accuracy | 100% |
| automated_action_kind_accuracy | — |
| note_kind_accuracy | — |
| commitments | P 100% · R 100% (tp 1, fp 0, fn 0) |
| asks_recall | 100% |
| due_date_accuracy | 100% |
| schedule_mentions_recall | — |
| role_changes_recall | — |
| claims_recall | — |
| stage_signals_recall | — |
| agreements_recall | — |
| evidence_validity | 0.909 |
| evidence_dropped | 1 |
| evidence_replaced | 0 |
| injection_recall | — |
| items_labeled | 6 |
| items_without_extraction | 4 |

Misses:
- [extraction] nl-scbrief-212: no extraction: expected `newsletter`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl)
- [extraction] auto-docusign-mei: no extraction: expected `automated`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl)
- [extraction] mkt-rippleboard: no extraction: expected `marketing`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl)
- [extraction] t-sam-daycare: no extraction: expected `human_thread`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl)

**compute**

| metric | value |
|---|---|
| contact_category_accuracy | 0.75 |
| contact_subtype_accuracy | 0.75 |
| contact_stage_accuracy | 0.667 |
| contact_tier_accuracy | 100% |
| about_merge_accuracy | 100% |
| about_merge_pairs_unlogged | 0 |
| candidates | P 0.875 · R 0.875 (tp 7, fp 1, fn 1) |

Misses:
- [compute] contact dana@lumenanalytics.example: category: expected `vendor`, got `cold_inbound` · [tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json](tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json)
- [compute] contact dana@lumenanalytics.example: subtype: expected `evaluating`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json](tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json)
- [compute] contact dana@lumenanalytics.example: stage day 30: expected `evaluating`, got `—` · [tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json](tests/fixtures/mini_runs/2026-09-24T06-00/contacts.json)
- [compute] candidate news_attachment rollout:halberd:oct-6: expected `present`, got `missing` · [tests/fixtures/mini_runs/2026-09-24T06-00/candidates.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/candidates.jsonl)

**triage**

| metric | value |
|---|---|
| include | P 100% · R 0.833 (tp 5, fp 0, fn 1) |
| priority_accuracy | 0.8 |
| priority_confusion | P0: P0: 2; P1: P1: 2; P2: P3: 1 |
| section_accuracy | 100% |
| sender_vs_content_up | — |
| sender_vs_content_down | — |
| sender_vs_content_cells | 0 |
| action_recall | 0.857 |
| action_confusion | task: task: 1; forward_delegate: forward_delegate: 1; reply: reply: 1; approve: approve: 1; message_person: message_person: 1; calendar_response: calendar_response: 1; decide: calendar_response: 1 |
| ambiguity_type_accuracy | — |
| question_default_present | — |

Misses:
- [triage] family:daycare: excluded by triage: expected `include`, got `exclude` · [tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L8](tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L8)
- [triage] meeting:lumen-demo: priority: expected `P2`, got `P3` · [tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L5](tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L5)
- [triage] meeting:lumen-demo: proposed action decide: expected `decide`, got `calendar_response` · [tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L5](tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L5)

**compose**

| metric | value |
|---|---|
| p0_recall | 0.667 |
| p0_expected | 3 |
| p0_gate | **FAIL** |
| one_thing_correct | pass |
| must_not_rate | 0% |
| absent_violations | 0 |
| section_placement_accuracy | 100% |
| compose_reduce_flags | none |
| words | 101 |
| length_budget | 350 |
| length_ok | pass |
| header_present | pass |
| items_cited_rate | 100% |
| citations_resolved_rate | 100% |
| verify_unresolved | 0 |

Misses:
- [extraction] P0 missing: family:daycare (no extraction for ['t-sam-daycare']): expected `rendered`, got `absent` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl)

**materializer**

| metric | value |
|---|---|
| drafts | 2 |
| max_sentences_ok | 100% |
| banned_phrases_absent | 0.5 |
| no_never_draft_recipient | 100% |
| assumptions_shown | 100% |
| numbers_match_data | — |

Misses:
- [materializer] draft to renee.tan@halberd.com: banned phrase: expected `none`, got `just wanted to` · [tests/fixtures/mini_runs/2026-09-24T06-00/actions.jsonl#L3](tests/fixtures/mini_runs/2026-09-24T06-00/actions.jsonl#L3)

## 3. Trap assertions

7 passed · 0 failed · 0 not run.

<details><summary>Passed</summary>

- S1-one-thing (`one_thing`): one thing: i1(deal:series-a:cap-table,P0,urgent), cites ['t-marcus-captable']
- S1-task-action (`action_present`): task on i1(deal:series-a:cap-table,P0,urgent)
- S11-no-draft-sam (`no_draft_to`): no draft to {'contact': 'sam@parkfamily.example'}
- marketing-absent (`item_absent`): absent: {'source_id': 'mkt-rippleboard'}
- S12-lumen-flagged (`candidate_present`): candidate(s) ['c5']
- S12-jordan-not-flagged (`candidate_absent`): no calendar_conflict:deep_work candidate for meeting:jordan-1on1
- news-decoy-absent (`item_absent`): absent: {'about': 'other:eu-telemetry-guidance'}

</details>

## 4. Customize and variant results

No customize or variant runs scored yet (M7).

## 5. Judge (E1, reported, not gated)

judge: skipped (no model configured)

## 6. Label audit

Not done yet: ~30 labels to hand-check (eval.md §9.5).
