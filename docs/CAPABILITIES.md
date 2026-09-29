# Capabilities and how each one is tested

What the digest does, the test that checks it, and where the result appears. The gate is P0 recall; everything else is
reported. Reports: `eval/reports/dev_2026-09-29.md`, `heldout_2026-09-29.md` (v1 in `*_v1.md`). Run it all with
`uv run digest eval --matrix --world dev --keep-going` (~$2, ~2 h) or score existing runs with `uv run digest eval --world dev --customize-suite --baseline`.

| Capability | How it is tested | Where |
|---|---|---|
| Never misses a P0: overdue promise to the lead investor, a partner's calendar conflict, a co-founder's email, a customer incident, the deal counsel's associate, a partner who inherits P0, the email that arrives after 06:00 | **P0 recall** over every expected P0 item, five mornings per world; the 15 P0 cases of `specs/eval.md` §4 are storylines with assertions | report §1 (gate), §2 "digest (the target)" per day, `P0 missing:` lines with the stage that lost it |
| The one thing is the right one on the mornings that have one | `one_thing` assertions (S1 day 29 and 30) | §1, §3 |
| An overdue promise buried in a one-line reply ("will send it tonight") is found, with a task and a forward to counsel | S1 assertions: item present, actions, one thing, cites | §3 |
| Calendar and email disagree: both dates shown, a calendar proposal, never one side picked silently | S2: `item_mentions_all` Friday + Monday, `action_present calendar_response`, present day 29 and 30 | §3 |
| A quiet investor thread surfaces at 3 business days, not before; Fri→Tue business-day math | S3: absent on days 27–28, present day 30; unit tests for the formulas | §3, `tests/test_b_compute.py` |
| Drafts use the data's number, not the profile's stale one ($3.4M, not $3.2M) | S3/S10 `draft_contains`, `item_qualified_with` drift | §3, judge factual score |
| Family first: a shared-calendar collision is P0, and Sam never gets a draft | S11 assertions + hard rule 1 (`no_draft_to never_draft`) checked on every run | §3, `verify.json` per run |
| A team exec's incident escalation is P0 with a reply to the exec, never a customer draft asserting a fix | S14: `item_present`, `action_absent reply` to the customer, priority | §3 |
| A promise fulfilled in another thread does not surface | S16 absent assertions (retrieval finds the delivery) | §3 |
| Recruiters only as a pattern; a lone recruiter never surfaces; newsletters only when they change an open item; a prompt injection is never P0 and never acted on | BG assertions (TalentBridge, newsletters decoy, CloudLedger injection) + hard rules 2–4, 11 | §3, `verify.json` |
| Honest when sources are stale or missing: caps confidence, says "may be a sync gap", says the calendar is unreadable, never invents a task status | honesty variants `stale_inbox`, `no_notes`, `corrupt_ics` + the built-in 11-day-stale tasks; `header_contains`, `item_qualified_with`, `confidence_max` | §4 |
| Customization within locked invariants: sections, focus, length, tone, newsletters change; citations, staleness flags and P0 visibility never do | customize suite, 9 prompts (`profile/customize/*.md`, `eval/customize_suite.yaml`): `p0_kept` on every run, `customize_rejected_noted`, `customize_not_understood`, `priorities_only`, `word_count_max`, tone shift | §4 |
| Memory across mornings: an answered card becomes a ruling applied later; an item shown three times says so; a closed item stops showing | `digest simulate --days 5` with a simulated Avery; `ruling_applied`, `escalation_framing`, `resolved_disappears`, `content_overrides_ruling` | §6, `runs/<w>/*_sim/` |
| Every claim cited, every citation verbatim and resolvable | code check on every finding (`digest/findings.py::check_citations`), `citations_present`, `citations_resolved_rate` | §2 digest metrics, `degradations.jsonl` |
| Beats a one-call baseline on the same inbox | `digest baseline`, scored on digest-level metrics | §1 baseline columns |
| Generalizes: a second world with new people and disguised traps, run once, never tuned on | held-out world (`world/heldout`, anchor 2026-03-26) | §1 held-out columns |
| Prose quality of digests and drafts | judge rubric (`prompts/judge.md`): digest = three questions answered / no noise / honest; drafts = factual / tone / assumptions. Applied in-session, scores in `eval/judge/in_session/`, or by the API judge with `--judge` | §1 judge rows, §5 |
| Where a miss happened | every failed assertion is attributed to the first stage that lost it: spine → read → sweep → net → merge → compose → materialize → verify; reader recall, sweep recall, rescue list, merge errors, contact classification per day | §2 diagnostics |
| The grader never uses string similarity | exact keys, unique sources, the product's decider for shared sources; every decision listed | report notes ("matching: …"), `OPEN_QUESTIONS.md` #23 |

Unit tests (`uv run pytest`, ~390): parsing and threading, business-day and overlap formulas, every safety net, the
Finding contract, reconcile and merge, the code floors, the customize compiler's mapping and locked invariants, the
scorer's matching, the import boundary (`digest/` never reads `world/` or `eval/`).
