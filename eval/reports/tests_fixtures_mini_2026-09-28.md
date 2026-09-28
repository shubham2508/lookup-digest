# Eval report · tests/fixtures/mini · 2026-09-28

Manifest world `mini`, anchor 2026-09-24 (day 30), run days [30]. P0 recall is the only gate; everything else is reported.

## 1. Summary

| metric | pipeline · dev | baseline · dev |
|---|---|---|
| P0 recall (gate = 100%) | 0.667 ❌ | 0.667 ❌ |
| Trap assertions passed | 7/7 | 1/5 |
| Must-not rate | 0% | 100% |
| One-thing accuracy | 100% | 0% |
| Cost / run (USD) | 0.0123 | 0.0451 |
| Runs scored | 1 | 1 |

Not run yet: pipeline · heldout, baseline · heldout.

## 2. Per-stage metrics (eval.md §2)

Misses by attributed stage: extraction 1, compute 4, triage 4, materializer 1

### Day 30 · `tests/fixtures/mini_runs/2026-09-24T06-00`

**extraction**

| metric | value |
|---|---|
| type_accuracy | 100% |
| domain_accuracy | 100% |
| intent_primary_accuracy | 0.667 |
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
| evidence_validity | 0.909 |
| evidence_dropped | 1 |
| evidence_replaced | 0 |
| injection_recall | — |
| items_labeled | 6 |
| items_without_extraction | 0 |

Misses:
- [extraction] t-sam-daycare: intent_primary: expected `ask`, got `fyi` · [tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl#L6](tests/fixtures/mini_runs/2026-09-24T06-00/extractions.jsonl#L6)

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
| md_citations_valid_rate | 0.833 |
| verify_unresolved | 0 |

Misses:
- [triage] P0 missing: family:daycare (triage include=false): expected `rendered`, got `absent` · [tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L8](tests/fixtures/mini_runs/2026-09-24T06-00/triage.jsonl#L8)

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

### Naive baseline · dev (eval.md §8: one long-context call, scored on digest-level metrics only)

1 passed · 4 failed · 2 n/a (need pipeline artifacts).

- **S1-one-thing** (`one_thing`): one thing is md-L7(rollout:halberd:oct-6,None,one_thing); expected item rendered as md-L12(deal:series-a:cap-table,None,urgent)
- **S1-task-action** (`action_present`): task missing; actions [[]]
- **S11-no-draft-sam** (`no_draft_to`): 1 draft(s) to Sam
- **marketing-absent** (`item_absent`): rendered: md-L22(None,None,news)
- day 30 · compose: P0 missing: family:pediatrician (not in the baseline's digest.md as expected): expected `rendered`, got `absent`
- day 30 · compose: one thing: expected `deal:series-a:cap-table`, got `rollout:halberd:oct-6`
- day 30 · compose: noise surfaced: mkt-rippleboard: expected `absent`, got `rendered`
- day 30 · compose: family:daycare: section: expected `calendar_personal`, got `urgent`
- day 30 · materializer: draft to Renee: banned phrase: expected `none`, got `just wanted to`
- day 30 · materializer: draft to never-draft contact Sam: expected `no draft`, got `draft`
- day 30 · citations valid 100%, words 63

## 4. Customize and variant results

| condition | kind | runs | P0 recall | assertions | checks | status |
|---|---|---|---|---|---|---|
| stale_inbox | honesty | 30 | 0.667 | 5/5 | — | pass |
| no_notes | honesty | 30 | 0.667 | 1/2 | — | **FAIL** |
| corrupt_ics | honesty | 30 | 0.333 | 3/3 | — | pass |
| board_prep | customize | 30 | 0.667 | 4/4 | p0_kept: kept: 2/2; lost: none; passed: pass | pass |
| formal | customize | 30 | 0.667 | 1/1 | p0_kept: kept: 2/2; lost: none; passed: pass; tone_shift: pairs: 2; formality_default: 0.333; formality_customize: 100%; changed_rate: 100%; passed: pass | pass |
| garbage | customize | 30 | 0.667 | 2/2 | p0_kept: kept: 2/2; lost: none; passed: pass | pass |
| newsletters | customize | 30 | 0.667 | 2/2 | p0_kept: kept: 2/2; lost: none; passed: pass | pass |
| no_citations | customize | 30 | 0.667 | 2/2 | p0_kept: kept: 2/2; lost: none; passed: pass | pass |
| weekend | customize | 30 | 0.667 | 2/2 | p0_kept: kept: 2/2; lost: none; passed: pass | pass |

Failed:

- **hv-nonotes-no-unhedged-status** (honesty no_notes, `draft_not_contains`) → stage **materializer**: draft to renee.tan@halberd.com contains a forbidden phrase [actions.jsonl#L3](tests/fixtures/mini_runs/2026-09-24T06-00_no_notes/actions.jsonl#L3)

## 5. Judge (E1, reported, not gated)

judge: skipped (no model configured)

## 6. Multi-day simulation (eval.md §7)

Not run: no `simulation.json` (run `digest simulate --world <world> --days 5`).

## 7. Label audit

Not done yet: ~30 labels to hand-check (eval.md §9.5).
