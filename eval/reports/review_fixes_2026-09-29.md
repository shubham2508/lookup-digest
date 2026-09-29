# Thursday rerun after the final code review · 2026-09-29

The five-morning reports (`dev_2026-09-29.md`, `heldout_2026-09-29.md`) were produced before a last code review. Its
fixes (hard rules on decide-card drafts, a customize filter that could hide a P0, one API error crashing a run, calendar
and routing decisions made by keywords, all-day events, tier inheritance on free-mail domains, owner name and time zone
from the profile, the cadence net, drift reaching drafts, history matched by cited source, compose v8, linker and
topic_grouper v3) were verified by rerunning Thursday (day 30) on both worlds on the submitted code, without the
simulation's rulings (as the plain mornings ran), and scoring all runs on disk. Held-out was run once and not tuned on.

## Day 30

| metric | dev before | dev after | held-out before | held-out after |
|---|---|---|---|---|
| P0 recall | 8/8 | 8/8 | 7/8 | **8/8** |
| One thing right | yes | yes | yes | yes |
| Must-not rate | 0.063 | 0.063 | 0.077 | 0.077 |
| Section placement | 0.833 | **1.00** | 0.909 | 0.909 |
| Words (budget 350) | 236 | 223 | 275 | 244 |
| Items cited | 100% | 100% | 100% | 100% |
| Cost of the rerun | | $0.02 | | $0.03 |

## Five mornings (four unchanged runs + the new Thursday)

| | dev before | dev after | held-out before | held-out after |
|---|---|---|---|---|
| P0 recall | 100% | 100% | 84.6% | **92.3%** |
| Trap assertions | 127/175 | 126/175 | 149/207 | **151/207** |
| Must-not rate | 5.5% | 5.5% | 6.1% | 6.1% |
| One thing right | 2/2 | 2/2 | 2/2 | 2/2 |

Assertions that changed on day 30:

| world | now passing | now failing |
|---|---|---|
| dev | S2 both dates mentioned | S5 reply and grounded draft (compose cut the Halberd rollout item, P1, from a 12-item page) |
| held-out | S11 early-dismissal present, its time, the ENT item's actions, message_person; the 350-word limit | S10 "3.6" not mentioned; S6 PO email surfaced (the new cadence net cites it); S9 a notes-sweep profile fact |

Runs: `runs/examples/{dev/2026-09-24T06-00,heldout/2026-03-26T06-00}`. The five-morning reports stay the record of the final
matrices; the numbers above come from rescoring the runs on disk with `digest eval --world <w> --out <dir>`.
