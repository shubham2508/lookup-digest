# Open Questions

Claude Code: add questions here instead of deciding silently. Format: what · where · options · suggestion.
Shubham reviews every addition (checkpoint 4). Answered items move to **Decided** at the bottom, with the date.

## Pending decisions for Shubham

### 1. Model IDs per role (`config/models.yaml`) — judge still open; needed to finish M0

Direction from Shubham (2026-09-28): small budget; GPT-6 Luna is the workhorse at per-stage reasoning effort; **generation is done by a Claude Code session (Fable 5.1), not by an API model** (decided, see bottom); a stronger model only for the judge, chosen after a short calibration. Family rule: judge ≠ OpenAI (pipeline) and ≠ Anthropic (generator). Prices are $ per 1M tokens, in / out, from the live OpenRouter catalogue; all support structured output, and Luna supports `reasoning_effort`.

| Role | Direction | Options |
|---|---|---|
| `extractor`, `triage`, `compose`, `materializer`, `compiler` | `openai/gpt-6-luna` (0.10 / 0.50), per-role `reasoning_effort`: extractor low · triage medium · compose high · materializer low · compiler low | `openai/gpt-6-luna-pro` (same price) for `compose` only |
| `generator` | **decided:** Claude Code session (Fable 5.1) writes the prose files; `generator/` code assembles, labels, validates | — |
| `judge` | third family; mid-tier is enough, because it applies one fixed rubric with the evidence attached, and everything with an expected output is scored by code | `google/gemini-3.8-flash` (0.75 / 3.75, ≈ $1 total) · `x-ai/grok-4.7` (1.6 / 4.8, ≈ $1.6) · stronger fallback `google/gemini-3.1-pro-preview` (2 / 12, ≈ $3) |
| `sim_avery` | cheapest; mostly code (matches a question card to the manifest's intended answer by about-key), LLM only as fallback | `openai/gpt-5-nano` (0.05 / 0.40) or reuse `gpt-6-luna` |

Judge plan (Shubham, 2026-09-28): the first judging round runs on Fable via the `judge_reference` role in `config/models.yaml` (≈ $1 for ~20 items); the third-family candidate (Gemini 3.8 Flash or Grok 4.7) scores the same items with the same rubric; agreement within 1 point on ≥ 80% keeps the cheap judge, recorded in DESIGN.md. Fable is never the judge of record (same family as the generator). Shubham picks after that round.

OpenRouter spend on this config ≈ $4–5 (pipeline ≈ $3, judge ≈ $1–1.6, sim_avery ≈ 0). Generation costs nothing on OpenRouter.


### 18. Scorer: a fuzzy "claimed" key blocks a citation match (orchestrator, 2026-09-29)

**What.** `_by_cites` refuses to match a rendered item to expected item X through its citations when the item's own
about key fuzzy-matches another expected item Y of that day, even if the item cites none of Y's sources. Dev day 30
(commit 4915503): the diligence-call contradiction was on the page as a P0 with both dates, citing Marcus's move
email and the calendar event, but keyed `deal:series-a:diligence`; that fuzzy-matches Elena's
`deal:series-a:diligence-prep`, so the report said "P0 missing".
**Where.** `eval/scorer/common.py` `_by_cites` / `claimed_abouts`.
**Options.** (a) Leave it: the pipeline now keys schedule contradictions by the meeting (1751a1e), so this case no
longer occurs. (b) Block the citation match only when the item also cites one of Y's `cites_any`.
**Suggestion.** (b), noted in DESIGN.md as a grader change made after results were seen. Your call; not changed.


### 21. Track C · v2 scorer interpretations (C-grader, 2026-09-29, unattended): built with the picks below; confirm or redirect

Where: `eval/scorer/common.py` (selectors), `readers.py` (C1), `assertions.py` (C3), `attribution.py`, `report.py`.

| # | What | Options | Picked |
|---|---|---|---|
| 21a | **Key-only selectors miss v2 items.** Readers write light tags (`deal:series-a`), so an assertion with an `about` and no `cites_any` (`S4-d30-present`, `S2-d30-0605-present`, …) finds nothing although the reader flagged the thread. | (1) keep key-only; (2) when a selector names a key but no sources, that day's expected items' `cites_any` for the key stand in; (3) add `cites_any` to every assertion (manifest edit, Track B) | (2), for every item-level check and the candidate kinds, v1 and v2 alike. On v1's own runs it credits items v1 rendered under other keys (franchise tax, press request): dev 115 → 118/175, held-out 129 → 137/207. |
| 21b | **Which v1 numbers head the table.** | (1) as reported (handoff C4); (2) rescored with this scorer (same rules as v2) | Column = (1), line under the table = (2), both in `eval/v1_results.yaml` (the v1 runs are overwritten by v2 runs). Suggest DESIGN.md quotes (2) for any v1-vs-v2 claim. |
| 21c | **C3 about alternative** ("type = v1 name **or** about matches"). Taken literally, rescoring v1 turned three passing absent checks into failures (an `approval_pending` candidate about `candidate:ines-ferreira` counted as a `hiring_stall`). | (1) any finding about the key; (2) the about alternative only for free-text kinds (a finding that names another v1 rule is that rule); `contradiction` / `suspicious_content` / `news_attachment` also need their Finding analog (`contradictions`, `suspicious_instructions`, the news sweep); only live findings (yes, or unsure with a card) | (2). With it, v1 rescored matches v1 as reported except the 21a/21d fixes. |
| 21d | **`count_items_of_type` without `about`** on a type v2 has no rule for (`cadence_drop`, `obligation_cadence`, …): the name never appears in v2. `about` was ignored in v1 (`BG-exp-one-item` counted all 19 approval items). | (1) name only; (2) that day's expected keys of the type, counted by key (not by shared note citations); honour `about` | (2) |
| 21e | **Reader diagnostics truth (C1).** The label rule (ball on Avery / open ask / open promise → yes) disagrees with the answer key on some threads: must-not threads with the ball on Avery (courtesy close, far deadline, S16 fulfilled elsewhere) and per-day timing (S3 before 3 business days). | (1) label only; (2) label + day rules | (2): thread fully visible at as_of; cited by an included item that day → yes with its band and actions (a must-not thread behind a pattern item, e.g. TalentBridge, not scored); `must_not_surface` → no; key in that day's `absent` or an excluded item cites it → no; `fulfilled_by_source` closes a promise. |
| 21f | **Stages the chain lacks.** | — | `spine` (before `read`) for contact classification; `net` also covers the code floors (`enforce`) when they override a right finding, and hard-rule violations in `triage.jsonl`. |


### 22. Track B · v2 spine, sweeps, nets, reconcile (B-spine, 2026-09-29, unattended): built with the picks below; confirm or redirect

Evidence: integrated dev Thursday (`digest run --world dev --as-of 2026-09-24T06:00` on branch `v2-b-spine`, $0.27
cold, $0.01 cached). Where: `digest/compute/{contacts,context,candidates,merge,sweeps,linker}.py`, `prompts/{signature_parser,
contact_classifier,calendar_sweep,notes_tasks_sweep,news_sweep}.md`.

| # | What | Options | Picked |
|---|---|---|---|
| 22a | **A waiting-on-Avery net on a thread the reader read and raised nothing on.** Spec §5.3 says rescue it. Without extraction the net's "waiting" is only "last message inbound, no reply", so it fires on courtesy closes; dev Thursday rescued 6 of them as P0/P1 items with drafts ("ravi, thanks for loading the deck… see you tomorrow at 11" to a Sep 8 reminder). | (1) spec literal: rescue; (2) the linker judges the reader's thread summary (tried: Jev flips on wording, the LLM wrote "nothing remains open" and returned no match); (3) the reader's reading of the raw thread stands: covered, logged with its summary in `links.jsonl` | (3). Nets still rescue on threads no reader read (a failed or skipped reader), and a thread with reader findings gets the net's fact attached (spec: "same thread"). Dev Thursday: 22 nets → 8 attached, 6 closed by the reader, 6 by the linker, **3 rescues** (TalentBridge pattern, 3 Ramp approvals, Stripe payout failure: mail no reader reads). |
| 22b | **Net thresholds.** The spec gives Capital: 3 business days only. | capital (any tier, the profile's "Marcus or another VC") ≥ 3 → `quiet_thread`; other P0 contacts (family, co-founder) any unanswered message → `reply_owed`; a teammate's reply in the thread counts as answered for an outside sender | as listed |
| 22c | **Automated request net in code** (no reader sees automated mail). | (1) regex on the request (sign / approve / verify, payment failed), "no action needed" excluded, dev tools excluded, last 7 days, one finding per system and kind; signature and payment P1, approval P3 (the rubric's "approving expenses"); deadline not parsed; (2) send flagged automated threads to readers (Track A) | (1). Dev: DocuSign (attached to the reader's "Sign Mei's offer"), Ramp ×3, Stripe payout. |
| 22d | **Dropped nets.** v1's `personal_date_collisions` (a personal *email* about a date) needs extraction. | drop (readers and the calendar sweep cover it) · keep in code | drop; dev: the daycare closure is a reader finding. `double_book` kept (MIGRATION_PLAN's keep list; the handoff's omits it). |
| 22e | **Spine choices.** | — | Classifier only for contacts with ≥1 message to or from Avery (calendar-only people stay unresolved or take the learned domain); its input has all-visible stats, not the 30-day window, so the cache re-runs only on new evidence; the learned domain is a hint and the fallback; role-at-org runs after the classifier so a handover in the reason counts; an org-less role rule (recruiters) applies on the classifier's exact category and subtype. Dev: 138 contacts, 5 unresolved; all four procurement leads matched by Jev (p ≥ 0.97). |
| 22f | **Retrieval** (#19 verdict). | — | The two related threads with the same people are ranked by subject-word overlap, before or after the thread: the S16 delivery thread ("notes on the pricing deck", later than the promise) is now the first ref of thread:20260916-1040.tomas. |
| 22g | **Edits outside B's files, for review** (branch `v2-b-spine`, commit "integration"). | take · revert | `compute/__init__.py`: `assemble` passes `msg_thread` and `read.summaries` to reconcile, marks only the rescue log as rescued (stale source is carried, not rescued); `build_spine` calls B's `build_contacts` directly; the dead v1 `compute_world` removed. `tests/test_a_stages.py`, `test_a_pipeline.py`: counts by origin now that sweeps and nets land. `tests/a_fakes.py`: 3 lines route the new schemas to `tests/b_fakes.py`. |
| 22h | **For the orchestrator (reduce, not B):** identical coarse keys across threads are not joined. Dev Thursday: `meeting:ipv-diligence-call` on 4 findings (3 reader threads + the calendar sweep) and `family:wren-pediatrician-2026-09-24` on 2 (reader + sweep) rendered as separate items. | join identical v2 about keys regardless of colons (thread_reader v2 makes tags specific) · join by shared citation · leave | suggest the first; `group_findings` merges (linker-judged) should join too. |
| 22i | **Prompt versions** (rule 10: an `eval/history.md` line after a prompt change). B never opens `eval/`. | — | New: `signature_parser` v1, `contact_classifier` v2, `calendar_sweep` v1, `notes_tasks_sweep` v2, `news_sweep` v2 (the linker's `net_covers_finding` task text is new; `linker.md` unchanged). The orchestrator adds the history line with the P6 run. |


## Decided

- **2026-09-29 evening · #25 final code review: fix high and medium, verify with one day** (Shubham: "fix high severity
  and medium ones … one day iteration is also fine"). Fixed: decide-card drafts pass the never-draft and draft checks
  (materialize and verify); a customize "hide section" moves a P0 to "Also outside your filter"; any API/transport
  error degrades instead of crashing; calendar personal/work from the calendar and family contacts, not keywords;
  all-day events make no conflicts; no tier inheritance on free-mail domains; suspicious-by-source for "never P0";
  topic grouping sends Jev's unsure picks to the LLM; history links items by cited source; rerun logs replace, not
  append; every "===" run in untrusted text is defused; the cadence net; drift facts reach drafts; the owner's name and
  time zone come from the profile. Also removed every keyword decision left in `digest/` (router newsletter/marketing
  split no longer gates reading, recruiter = the classifier's exact label, the compose-notes filter, the task due date
  from the resolved deadline, the customize regex guard) and the dead v1 code. Verified by rerunning Thursday per
  world without rulings: `eval/reports/review_fixes_2026-09-29.md` (dev day 30 unchanged; held-out day 30 P0 7/8 → 8/8).

- **2026-09-29 ~10:30 · #24 how dedupe/merge works on free-text findings, and how sure we are** (Shubham: "findings are
  free text, how can you be sure?"). The unit on the page is the *issue*, and one issue lives in several threads and
  sources, so findings are merged across threads by `digest/reduce/__init__.py::join_keys` and
  `digest/compute/merge.py`. **What is exact:** the rules never read the free text. A finding's citations are source
  ids plus verbatim quotes that code has already checked against the source; its entities are contact ids from the
  contact cards (names are mapped to ids, unknown ones dropped); its tags are `kind:slug` strings. Two findings join
  when (1) they carry the same qualified tag, string-equal; (2) they cite the same message with the same words; (3) they
  carry the same tag and share a contact id; (4) a safety net's fact is attached to the reader finding the linker says it
  covers; (5) tags of different kinds that share a person are put to the linker (Jev, LLM under p 0.7) as a pick-one
  question. Nothing uses similarity. A coarse tag alone (`deal:series-a`) never joins. **What free text costs:** tag
  equality is a sufficient condition, not a necessary one; when two readers tag one issue differently and share no
  message and no person, the issue renders twice, which the eval counts (`expected_items_rendered_twice`). When two
  different issues share a tag and a person, they over-merge, which the eval also counts
  (`items_merging_expected_items`). **Measured (final reports, day 30, 34 expected keys):** dev 3 rendered twice, 3
  over-merged; held-out 7 and 7; the other days 1–4 and 0–3. Over-merging is the worse failure (an item can drop
  off the page: held-out's early-dismissal miss); duplication only costs a slot. **Cost:** exact rules are a hash join,
  O(findings × keys); the linker is asked only inside buckets (same tag kind, or a person on 2–8 keys), ~100 Jev
  questions a morning. **Next step if this is tuned:** ask each reader for the tags earlier digests used on its
  thread (tag continuity), and require a shared message or event, not only a shared person, for rule (3).

- **2026-09-29 ~09:30 · #23 grader matching without string similarity; closes #18** (Shubham: "what should the actual
  behavior be? it's a code match, not an LLM match"). `eval/scorer/match.py::about_match` is exact key equality; the
  rapidfuzz ratio is gone. Whether a rendered item (or finding) *is* an expected item is decided in
  `eval/scorer/coverage.py`: (1) an exact key, or a citation of a source **unique** to that expected item that day;
  (2) an item labeled, exactly, with another expected item's key is that item and is never credited here (the old #18
  guard without the ratio); (3) items that cite only sources shared with other expected items go to the decider, the
  product's own linker (Jev first, the LLM under p 0.7), one question per expected item per day, memoized, logged in
  the report's notes ("matching: …"). The #9 fallback keeps its source routes (a source labeled with the key, or of
  the same storyline) and drops the token-in-entity heuristic. Under pytest no live decider is built (tests inject a
  stub or run strict). Held-out and dev were re-scored on the same runs; no pipeline change.

- **2026-09-29 ~07:40 · #21 (C) and #22 (B) accepted as built** (orchestrator, delegated). #21a–f: key-only selectors
  borrow the answer key's sources; v1 column as reported with the rescored line beneath; count-by-key for rule-less
  types; reader truth from the labels; `spine` and `net` stages. #22a–g: waiting nets covered by a reader that read the
  thread; thresholds (capital ≥ 3 business days, other P0 contacts any unanswered message); automated-request net in
  code; personal-date collisions left to readers and the calendar sweep; classifier only for contacts with mail;
  retrieval ranks same-people threads by subject overlap; B's integration edits kept. #22h done in reduce: identical
  v2 tags on threads that share a person join, and every linker about-merge pair joins. #22i: history line with the
  final run.

- **2026-09-29 ~05:45 · #20 judging and eval spend for v2** (Shubham): no OpenRouter spend on evaluation. The
  judge of record for the v2 numbers is the Claude Code orchestrator session (Fable 5.1) applying `prompts/judge.md`
  in-session to the final digests; `deepseek/deepseek-v4.1-flash` stays configured for a later API run (cents).
  Note for DESIGN.md: this breaks the third-family rule from #1 (same family as the generator); Shubham's call,
  budget-driven. API money goes to producing digests only: dev 5 mornings + baseline, held-out 5 mornings +
  baseline; honesty variants, customize suite and the 5-day simulation run only if budget remains (v1's condition
  results stay reported from the v1 tag). **Keep the DeepSeek judge code and config in hand** (`eval/judge/judge.py`,
  `roles.judge` in `config/models.yaml`, `digest eval --world <w> --judge`); it is not deleted, only not run now.

- **2026-09-29 ~05:30 · #19 v2 pivot approved; the P2 reader checkpoint is delegated to the orchestrator** (Shubham,
  before sleeping). Criteria, fixed now so the review is not a judgment call made after seeing the output: for each
  of the five planted threads listed in `docs/handoffs/v2-A-checkpoint.md`, (1) the planted issue appears as a Finding with
  `needs_avery: yes`; (2) its priority is within the answer key's band for that item; (3) one of the expected action
  types is proposed; (4) no fact in `why`/`title` is absent from the raw thread. Pass = readers match or beat v1 triage
  on ≥4 of 5 and never fail (4). Fail = stop the merge of P3–P5, keep v1, report in the morning. Tracks run
  unattended (defaults from MIGRATION_PLAN.md §5 instead of questions).
  **Verdict (orchestrator, 2026-09-29 ~06:10): PASS.** Threads 1, 2, 4 beat v1 (one finding instead of three; no
  invented "8:00"; the calendar contradiction lands in calendar_personal as the key expects); thread 3 matches on
  priority and section but proposes `task` where the key expects `message_person`/`decide`; thread 5 shares v1's miss
  (a promise delivered in another thread), which Track A showed disappears once that thread is retrieved (B2 must rank
  same-participant threads by subject overlap, not only recency). No finding states a fact absent from the raw thread.
  Carried to integration (A5, orchestrator): compose rewrote Jordan's reply into a customer draft (recipient check in
  code), reduce joins every same-thread finding (join by shared citation instead), history keyed on free-text tags,
  freshness qualifier keyed on v1 types. Details: `docs/handoffs/v2-A-checkpoint.md`.

- **2026-09-29 · Orchestrator fixes from the final dev runs (implementing the spec, no design change).** Traced with
  the debug-trap procedure; each is a commit with a test. Tier inheritance only at outside firms (every Tessera
  teammate had inherited the co-founder's P0). Jev picks under p 0.7 go to the LLM linker (an obvious meeting move
  came back 0.49). Schedule contradictions are keyed by the meeting, so a date ruling does not attach to the whole
  deal. Triage v6: no invented clock times; due by the next business day counts as today; a P0 contact's ask at
  the quiet threshold is P0. Extractor v3: a promise to deliver later does not answer an ask; event-implied
  deadlines; dated claims carry their date. Evidence match ignores markdown `*`. Ruling ids use the digest's date.
  Escalation framing and freshness qualifiers are enforced in code, including on Also-pending lines. compose.json
  lists the P0 one-liners outside a customize filter.

- **2026-09-28 · #16 the linker: LLM decides "same thing?", no word similarity in compute** (Shubham: "word-match things suck").
  *Before:* rapidfuzz thresholds decided topic-key merges (ratio ≥ 85), calendar event ↔ email meeting (≥ 55), promise already in tasks (≥ 80), promise fulfilled in another thread (≥ 70), task done per email (≥ 80), declined-meeting fallout (≥ 60–70), and news ↔ open item (exact words). They over- and under-merged on real data (five items for one board update; three job candidates merged into one).
  *Now:* `digest/compute/linker.py` + `prompts/linker.md` + `prompts/topic_grouper.md` (role `linker`, Luna, low effort). Code narrows the options with hard facts only (same people, ±7 days, later in time, same topic kind); one batched, cached LLM call per question type decides sameness and writes a reason; every decision goes to `runs/…/links.jsonl` and shows in the UI's LLM calls tab. Without an LLM, or if the call fails, only identical keys match: a missed link is visible, an invented one is not. ~8 calls, ~$0.2 per run cold, cached after.
  *Still string-based:* contact name/org/title matching in `digest/compute/contacts.py` (week two).
  *Alternative evaluated:* TypeSafe's Jev 1.13 (a classifier model, via OpenRouter's `/api/alpha/decisions`): 0.44 s and $0.00002 for a test question, answered correctly with probabilities, but gives no written reason. Plan: add it as a second linker backend after the final runs and compare on dev; not swapped in before the submission numbers.
  *Update (196e557, 1751a1e):* Jev now answers first (role `decider`); the LLM decides a question when Jev fails or its top probability is under 0.7 (`llm.jev_min_probability`). The submission numbers are on this setup.
  Commits: 0435905 (linker), 5038594 (prompt-example leak removed).
- **2026-09-28 · #17 prompt-example leak removed.** Worked examples in six prompts had copied dev storylines (S1 cap table 'will send it tonight', S2 diligence move, S3/S10 $3.4M ARR draft, S5 'Oct 6 still on' reply, S8 Mei, S13 DeepSeek price cut). All replaced with a made-up cast that appears in no mailbox; triage's 'Sam and Wren' rule now reads the family category from the profile. All scores before commit 5038594 were measured with the leak and are not reported as results. The `debug-trap` skill enforces a grep check for world names in prompts.

- **2026-09-28 · held-out planted-pattern section names** stay as the generator's dev names (`talentbridge`, `stripe_payout`), so the held-out manifest tags HireVector and Gusto as `BG-talentbridge` / `BG-stripe`. Cosmetic; renaming would touch the generator and both worlds. Noted for DESIGN.md.
- **2026-09-28 · integration fixes to Track A's compute and prompts** (orchestrator, after the first dev run): see STATUS 17:20. Prompt versions: triage 2 → 3, compose 1 → 2; `eval/history.md` gets the before/after line once the dev report exists.

- **2026-09-28 · Track A M4–M9 notes (#14), all accepted as implemented:** (14a) a personal-domain slot inside the workday is a `calendar_conflict:family` candidate even without an overlapping work event, with `facts.overlaps_work_event=false` for triage to weigh; (14b) calendar freshness = max(event stamps, `.ics` mtime); (14c) the `_strip` fix stands (reviewed: correct, keys inside `properties` are field names); (14d) the handoff example was wrong, #8(a) rules: Fri→Tue = 1; (14e) `TriageBatch`, `BaselineDigest`; (14f) `test_cli.py`; (14g) `digest answer` targets the latest plain run.
- **2026-09-28 · #15 simulate runs get their own folder.** `digest simulate` re-runs days 26–30 with rulings applied, so if it wrote to the plain run dirs the eval would score rulings-applied digests. Decision: `RunContext.tag` (added; joins the suffix) → `digest run --tag sim` writes `runs/<world>/<as_of>_sim/`; simulate passes `--tag sim` and the §7 checks read the `_sim` dirs; plain runs stay rulings-free for P0 recall and trap assertions. Small edits to `digest/cli.py` (`--tag`) and `eval/cli.py`/`sim_avery` (pass and read the tag); the orchestrator makes them at integration.
- **2026-09-28 · integration findings to verify on the real dev run** (from C's matrix on the fixture against A's pipeline; may predate A's final commit): `corrupt_ics` header must say the calendar is unreadable and no calendar conflicts may appear; `stale_inbox` must qualify overdue/quiet items with "may be a sync gap"; `weekend.md` must keep the cap-table P0 as a one-liner (locked invariant). Owner: orchestrator at integration, routed to A only if larger than a small fix.

<details><summary>Track A's #14 as written</summary>

### 14. Track A · M4–M9 notes (A-product, 2026-09-28): implemented as suggested; confirm or redirect

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 14a | **`calendar_conflict:family` without an overlapping work event.** §6.4 requires overlap with an accepted/organized work event, but the M4 acceptance (and the fixture) expect the pediatrician at 15:00 with nothing booked. | (1) strict overlap only; (2) also flag a personal-domain slot that falls inside the workday (Mon–Fri 09:00–18:00) with `facts.overlaps_work_event = false`, triage decides | (2). Overlaps, when present, are listed in `facts.overlaps`. |
| 14b | **Calendar freshness.** §3 says `latest_item_time` = max event `last_modified`, so a calendar nobody edited for two days reads "calendar stale (2 days)" on quiet mornings. | (1) spec literal; (2) also count the `.ics` file mtime (the sync time) | (2): `max(event stamps, ics mtime)`; unreadable/missing still flagged; `corrupt_ics` still yields "calendar unreadable". |
| 14c | **`digest/llm.py` `_strip`** removed any schema key named `default`, including the *property* `Ambiguity.default`, so triage could never emit it (two failed packs per run). Fixed in place: keys inside a `properties` map are field names, never keywords. `tests/test_schemas.py` `_walk` adjusted the same way. Orchestrator-owned file; please review the 3-line change. | — | fixed |
| 14d | **Handoff example "Fri→Tue = 2 business days"** conflicts with the decided rule #8(a) (weekday dates strictly between message and run date: Fri→Tue = 1). | — | Implemented #8(a); `tests/test_a_compute.py` documents Fri→Mon 0, Fri→Tue 1, Thu→Tue 2, Wed→Tue 3. |
| 14e | **Triage packing.** `TriageBatch {results: [TriageResult]}` registered in `digest/schemas.py` (allowed by the handoff) so 5–10 candidates share one call; a pack that fails validation twice is retried candidate-by-candidate before any fallback. `BaselineDigest {markdown}` registered for `digest baseline`. | — | done |
| 14f | **`tests/test_cli.py`** lost `test_stubs_say_not_implemented`: every command is real now (A: run/answer/baseline; B: generate; C: eval/simulate). Replaced by no-state checks for `answer` and `baseline`. | — | done |
| 14g | **`digest answer` picks the latest plain run** (no variant/customize/baseline suffix) of the world; a question number refers to that digest only. `digest simulate` runs days in order, so this is the intended card. | — | done |

</details>

- **2026-09-28 · Track C M7–M9 questions (#13, restored below), ruled:**
  (13a) **`rulings.yaml` lives at `runs/<world>/rulings.yaml`**, now `settings.store.rulings_path_template`; `digest answer` and `digest simulate` write it, the store's `rulings` table mirrors it, per-world so dev rulings never leak into held-out.
  (13b) **`digest simulate --fresh` (opt-in) stays**: it renames the old `rulings.yaml` and store aside, never deletes. The integration and eval runs always pass `--fresh` so the §7 assertions start from clean state.
  (13c) **The header phrase is `applied N learned rules`**, exactly as architecture §10 specifies, rendered when N ≥ 1 and omitted when N = 0. Track A also writes `rulings_applied: N` into `run.json`; the scorer prefers that field and falls back to the header regex `applied (\d+) learned rules?`. Track A confirms 13a and 13c by implementing them in M9.
- **2026-09-28 · Track A's edits to shared files accepted:** `digest/llm.py` `_strip` no longer drops a property that happens to be named like a schema keyword (a real bug: `Ambiguity.default` was being stripped); `TriageBatch` and `BaselineDigest` added to `digest/schemas.py` and `LLM_OUTPUT_MODELS`. A commits them with its milestone.

<details><summary>Track C's #13 as written (restored; my cleanup had dropped it)</summary>

### 13. Track C · M9: where `rulings.yaml` lives, and how `digest simulate` starts clean (C-grader, 2026-09-28): built as suggested

| # | What · where | Options | Implemented (suggestion) |
|---|---|---|---|
| 13a | **`rulings.yaml` path.** architecture §10 names the file; no spec says where. The simulation checks that an answered card produced a ruling for that scope. | (1) `runs/<world>/rulings.yaml`, next to `store.sqlite`; (2) repo root; (3) `profile/rulings.yaml` | (1). The scorer reads (1), then falls back to (2). Entries as §10: `{id, scope: {contact\|about\|thread_kind}, ruling, option_chosen, from_question, created, expires}`. |
| 13b | **Simulation state.** `digest simulate` runs days 26–30 in order, so rulings and digest history must start empty, or earlier runs leak into the escalation and ruling checks. | (1) `simulate --fresh` renames `runs/<world>/rulings.yaml` and `store.sqlite` to `*.bak-<timestamp>` first (reversible, never deletes); (2) product flag `--state-dir`; (3) accept leakage | (1), opt-in; without it the report notes any pre-existing rulings. |
| 13c | **"applied N learned rules"** in the header (§10) is how the scorer sees a ruling applied when triage output alone is ambiguous. | keep the phrase · redirect | Keep; the scorer matches `applied \d+ learned rule`. |

</details>

- **2026-09-28 · M1 storyline review: approved.** All 16 `world/dev/storylines/*.yaml` are `reviewed: true`; the eight judgment calls (former #5) are confirmed as drafted; S3 keeps the three-business-day rule.

- **2026-09-28 · full scope, no cut line.** Everything through M10 is built today; submission tomorrow morning; walkthrough the following week. Nothing is deferred.
- **2026-09-28 · held-out anchor = 2026-03-26** (Thursday = day 30; day 1 = Wed 2026-02-25; the window crosses the Mar 8 spring-forward on day 12, in the history, not in the run days). Held-out world is **full size** (~500 emails), same trap types, different disguises and names, written in a separate Data session.
- **2026-09-28 · Track A M3 contract notes (#6), all accepted as implemented:** (6a) `Extraction.source_id` = `thread:<root Message-ID>` / `note:notes/<file>.md` / `task:<slug-of-title>`; evidence ids `msg:<Message-ID>` (with brackets), `note:…#L<n>`, `task:<slug>`, `event:<uid>`; forwarded messages get `<fwdN.<parent id>>`. (6b) Avery's address detected from the data, logged as `owner_email`. (6c) the generator writes `<!-- last-modified: <ISO> -->` as the first line of `tasks.md` and every note; ingest prefers it over mtime. (6d) honesty variants stay in ingest. (6e) a required singleton evidence with a bad quote is replaced by a verbatim span and logged as `evidence_replaced`. (6f) `tests/test_cli.py` updated.
- **2026-09-28 · Track C M6 contract gaps (#7), all accepted:** (7a) `ReduceItem/ReduceResult`, `MaterializedAction`, `VerifyViolation/VerifyStats/VerifyResult` are pinned in `digest/schemas.py`; Track A writes `reduce.json`, `actions.jsonl`, `verify.json` in those shapes. (7b) every manifest email item carries `messages[].message_id`; the fixture manifest now does too; notes/tasks use A's source-id forms. (7c) `RunContext.suffix`: `--customize x.md` → `…_customize-x`, `digest baseline` → `…_baseline`, combined with `+`. (7d) compute/reduce writes `about_merges` into `reduce.json`. (7e) assertion arg shapes as defined in `eval/scorer/assertions.py`; Track B authors to them. (7f) done.
- **2026-09-28 · business days (#8): option (a).** Weekday dates strictly after the message date and strictly before the run date. S3 stays as drafted.
- **2026-09-28 · about keys for computed candidates (#9): (a) + (b).** The `world/dev/README.md` convention for the manifest; the scorer falls back to type + shared entity/citation when the key does not fuzzy-match. Track A uses the same slugs in compute.
- **2026-09-28 · expected-item matching (#10): option (b).** Fuzzy about key **or** any rendered citation in `cites_any`; "present" = full item, one-liner, or "Also pending" line.
- **2026-09-28 · cadence formula (#11): as suggested.** Each gap belongs to the window of its later message; if the recent window has no complete gap, use the current gap (as_of − last inbound); merge predecessor + successor at the same org/role. Track A implements exactly this with S6/S7 as the unit tests.
- **2026-09-28 · S2 (#12): option (a),** keep as drafted; the contradiction comes from the calendar join, not the thread's ball.

- **2026-09-28 · deadline:** the repo is submitted the morning of 2026-09-29; the walkthrough is the following week. Cut line recorded in CLAUDE.md ("Deadline") and `docs/handoffs/STATUS.md`. Building continues after submission until the walkthrough.
- **2026-09-28 · dev anchor = 2026-09-24** (Thursday = day 30; day 1 = 2026-08-26; run days Sun 20 – Thu 24 Sept; all PDT, no DST crossing). `world/dev/world.yaml` carries `anchor: 2026-09-24`; `digest generate --anchor` overrides. Held-out anchor is decided separately at M8.
- **2026-09-28 · OpenRouter key limit:** Shubham raises it; not a build concern. Cost is still logged per run.
- **2026-09-28 · commit policy (a):** each track session commits its own paths at milestone ends with a `[A-product]` / `[B-data]` / `[C-grader]` prefix; the orchestrator commits foundation, integration and docs; never `git add -A`; stagger commits if sessions run at the same moment.
- **2026-09-28 · generator = Claude Code session (Fable 5.1), not an API model.** The Data track session writes every email body, note, and background item as prose files with labels under `world/<world>/prose/`; `generator/` code turns them into `.eml` / `.ics` / notes / tasks with real headers, threading, and DST-correct dates, emits the manifest, and runs the validator. Reproducible from world files + committed prose; a changed beat means rewriting its prose file. Zero OpenRouter spend for generation. `models.yaml` records `generator: claude-code-session`.
