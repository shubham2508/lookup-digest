# Eval report · tests/fixtures/mini · 2026-09-28

Manifest world `mini`, anchor 2026-09-24 (day 30), run days [30]. P0 recall is the only gate; everything else is reported.

> day 30: malformed artifact: contacts.json: 12 of 12 rows are not JSON objects (e.g. model reprs), so contact metrics read them as missing

## 1. Summary

| metric | pipeline · dev |
|---|---|
| P0 recall (gate = 100%) | 100% ✅ |
| Trap assertions passed | 7/7 |
| Must-not rate | 0% |
| One-thing accuracy | 100% |
| Cost / run (USD) | 0% |
| Runs scored | 1 |

Not run yet: pipeline · heldout, baseline · dev, baseline · heldout.

## 2. Per-stage metrics (eval.md §2)

Misses by attributed stage: compute 15, triage 3

### Day 30 · `/Users/shubham/Desktop/work/lookup-digest/runs/tests/fixtures/mini/2026-09-24T06-00`

**extraction**

| metric | value |
|---|---|
| type_accuracy | 100% |
| domain_accuracy | 100% |
| intent_primary_accuracy | 100% |
| ball_awaiting_accuracy | 100% |
| closed_by_courtesy_accuracy | 100% |
| automated_action_kind_accuracy | 100% |
| note_kind_accuracy | — |
| commitments | P 100% · R 100% (tp 1, fp 0, fn 0) |
| asks_recall | 100% |
| due_date_accuracy | 100% |
| schedule_mentions_recall | — |
| role_changes_recall | — |
| claims_recall | — |
| stage_signals_recall | — |
| agreements_recall | — |
| evidence_validity | 100% |
| evidence_dropped | 0 |
| evidence_replaced | 0 |
| injection_recall | — |
| items_labeled | 6 |
| items_without_extraction | 0 |

**compute**

| metric | value |
|---|---|
| contact_category_accuracy | 0% |
| contact_subtype_accuracy | 0% |
| contact_stage_accuracy | 0% |
| contact_tier_accuracy | 0% |
| about_merge_accuracy | 0.5 |
| about_merge_pairs_unlogged | 0 |
| candidates | P 0.667 · R 100% (tp 8, fp 4, fn 0) |

_candidate reply_owed rollout:halberd:oct-6 matched by fallback to rollout:halberd_

_candidate calendar_conflict:deep_work meeting:lumen-demo matched by fallback to meeting:lumen-analytics-demo_

_candidate calendar_conflict:family family:pediatrician matched by fallback to family:wren_

_candidate news_attachment rollout:halberd:oct-6 matched by fallback to other:news:manufacturers-share-plant-floor_

_candidate task_due report:q2-planning matched by fallback to meeting:q2-planning_

Misses:
- [compute] contact renee.tan@halberd.com: category: expected `customer`, got `no contact` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact renee.tan@halberd.com: subtype: expected `reference`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact renee.tan@halberd.com: stage day 30: expected `active`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact renee.tan@halberd.com: tier: expected `P1`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact marcus@inflectionpoint.vc: category: expected `capital`, got `no contact` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact marcus@inflectionpoint.vc: subtype: expected `lead_investor`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact marcus@inflectionpoint.vc: stage day 30: expected `term_sheet`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact marcus@inflectionpoint.vc: tier: expected `P0`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact sam@parkfamily.example: category: expected `family`, got `no contact` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact sam@parkfamily.example: subtype: expected `partner`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact sam@parkfamily.example: tier: expected `P0`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact dana@lumenanalytics.example: category: expected `vendor`, got `no contact` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact dana@lumenanalytics.example: subtype: expected `evaluating`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] contact dana@lumenanalytics.example: stage day 30: expected `evaluating`, got `—` · [runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json](runs/tests/fixtures/mini/2026-09-24T06-00/contacts.json)
- [compute] about merge deal:series-a:cap-table ~ deal:series-a:captable: expected `merge`, got `apart` · [runs/tests/fixtures/mini/2026-09-24T06-00/reduce.json](runs/tests/fixtures/mini/2026-09-24T06-00/reduce.json)

**triage**

| metric | value |
|---|---|
| include | P 100% · R 100% (tp 6, fp 0, fn 0) |
| priority_accuracy | 0.833 |
| priority_confusion | P0: P0: 3; P1: P1: 2; P2: P1: 1 |
| section_accuracy | 100% |
| sender_vs_content_up | — |
| sender_vs_content_down | — |
| sender_vs_content_cells | 0 |
| action_recall | 0.75 |
| action_confusion | task: task: 1; forward_delegate: task: 1; reply: reply: 1; approve: approve: 1; message_person: message_person: 2; calendar_response: calendar_response: 1; decide: calendar_response: 1 |
| ambiguity_type_accuracy | — |
| question_default_present | — |

Misses:
- [triage] deal:series-a:cap-table: proposed action forward_delegate: expected `forward_delegate`, got `task; task` · [runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L4](runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L4)
- [triage] meeting:lumen-demo: priority: expected `P2`, got `P1` · [runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L2](runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L2)
- [triage] meeting:lumen-demo: proposed action decide: expected `decide`, got `calendar_response` · [runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L2](runs/tests/fixtures/mini/2026-09-24T06-00/triage.jsonl#L2)

**compose**

| metric | value |
|---|---|
| p0_recall | 100% |
| p0_expected | 3 |
| p0_gate | pass |
| one_thing_correct | pass |
| must_not_rate | 0% |
| absent_violations | 0 |
| section_placement_accuracy | 100% |
| compose_reduce_flags | none |
| words | 129 |
| length_budget | 350 |
| length_ok | pass |
| header_present | pass |
| items_cited_rate | 100% |
| citations_resolved_rate | 100% |
| md_citations_valid_rate | 0.75 |
| verify_unresolved | 0 |

**materializer**

| metric | value |
|---|---|
| drafts | 2 |
| max_sentences_ok | 100% |
| banned_phrases_absent | 100% |
| no_never_draft_recipient | 100% |
| assumptions_shown | 100% |
| numbers_match_data | — |

## 3. Trap assertions

7 passed · 0 failed · 0 not run.

<details><summary>Passed</summary>

- S1-one-thing (`one_thing`): one thing: i2(deal:series-a:cap-table,P0,urgent), cites ['t-marcus-captable']
- S1-task-action (`action_present`): task on i2(deal:series-a:cap-table,P0,urgent)
- S11-no-draft-sam (`no_draft_to`): no draft to {'contact': 'sam@parkfamily.example'}
- marketing-absent (`item_absent`): absent: {'source_id': 'mkt-rippleboard'}
- S12-lumen-flagged (`candidate_present`): candidate(s) ['c2']
- S12-jordan-not-flagged (`candidate_absent`): no calendar_conflict:deep_work candidate for meeting:jordan-1on1
- news-decoy-absent (`item_absent`): absent: {'about': 'other:eu-telemetry-guidance'}

</details>

## 4. Customize and variant results

| condition | kind | runs | P0 recall | assertions | checks | status |
|---|---|---|---|---|---|---|
| stale_inbox | honesty | 30 | 0.667 | 4/5 | — | **FAIL** |
| no_notes | honesty | 30 | 100% | 2/2 | — | pass |
| corrupt_ics | honesty | 30 | 100% | 0/3 | — | **FAIL** |

Failed:

- **hv-stale-overdue-qualified** (honesty stale_inbox, `item_qualified_with`) → stage **compose**: unqualified: i2(deal:series-a:cap-table,P0,urgent) [compose.json](runs/tests/fixtures/mini/2026-09-24T06-00_stale_inbox/compose.json)
- **hv-ics-header** (honesty corrupt_ics, `header_contains`) → stage **compose**: header lacks [['calendar unreadable', 'calendar unavailable', 'calendar: unreadable', 'calendar checks skipped', 'calendar missing']]: As of Thu 06:00 PT · inbox synced Wed 21:10 · calendar ok · notes ok · tasks ok · 1 item(s) degraded (see degradations.jsonl) [digest.md#L1](runs/tests/fixtures/mini/2026-09-24T06-00_corrupt_ics/digest.md#L1)
- **hv-ics-no-conflict-candidates** (honesty corrupt_ics, `no_candidates_of_type`) → stage **compute**: unexpected candidate(s) [('calendar_conflict:family', 'family:wren')] [candidates.jsonl#L2](runs/tests/fixtures/mini/2026-09-24T06-00_corrupt_ics/candidates.jsonl#L2)
- **hv-ics-no-conflict-items** (honesty corrupt_ics, `count_items_of_type`) → stage **compose**: 1 calendar_conflict items, expected <= 0: i1(family:wren,P0,calendar_personal) [compose.json](runs/tests/fixtures/mini/2026-09-24T06-00_corrupt_ics/compose.json)

## 5. Judge (E1, reported, not gated)

judge: skipped (not requested)

## 6. Multi-day simulation (eval.md §7)

Generic checks: 0/0 passed.

- not run · **sim-ruling-recorded**: no cards were answered during the simulation

## 7. Label audit

Not done yet: ~30 labels to hand-check (eval.md §9.5).

## Simulation transcript

```json
[
  {
    "day": 30,
    "as_of": "2026-09-24T06:00",
    "run_exit": 0,
    "answers": []
  }
]
```
