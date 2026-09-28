# Data audit (PIVOT_SPEC §7) — dev world, 2026-09-29

Random sample (seed 7): 10 of 414 background emails, 5 of 109 storyline emails, plus 4 storyline emails read during
the Thursday trace. Question per email: realistic? is the trap trivially greppable?

| # | Email | Realistic? | Trap obvious? |
|---|---|---|---|
| BG | Grand Avenue Dental: appointment confirmed Thu 8:00 | yes; standard confirmation with a cancellation fee line | n/a |
| BG | Stripe: August statement ready | yes; numbers consistent with a ~$3M ARR company | n/a |
| BG | Omar: Re: PR #389 retry/backoff | yes; terse engineer voice, "merging after CI" | n/a |
| BG | Calendly: win-back offer | yes; marketing with unsubscribe footer | n/a |
| BG | Sofia: Re: PR #371 streaming CSV | yes; one rendering nit: name repeated twice before the quoted history | n/a |
| BG | HubSpot: CRM pitch | yes; cold marketing | n/a |
| BG | Google Calendar: Finance sync updated (description) | yes; a real agenda ("ARR reconciliation against the board deck") that seeds S10 quietly | n/a |
| BG | Marcus: "Got it, thanks. Ravi will reach out" | yes; courtesy close, the ball moves to Ravi without saying so | not greppable |
| BG | SaaS Operator #143 usage pricing | yes; long-form newsletter prose | n/a |
| BG | Avery: "congrats all. nice one." | yes; Avery's one-line style from the profile | n/a |
| S7 | Simon (Veritas): Re: August usage report | yes; formal, two real questions (double count, seat count) buried in a report reply | no: the handover is elsewhere and later |
| S6 | Tomás: Re: Invoice TS-0834 PO mismatch | yes; credit-memo detail; the Northstar downtime remark is an aside in paragraph four | no |
| S4 | Avery: "let's talk soon — I'll send some times for next week" | yes; the soft promise the profile describes | no: no date, no "promise" |
| S5 | Avery: "renee, yes, let's lock Oct 6" | yes; delegation to Yuki in one line | no |
| S5 | Renee: weekend email with the Fresno contact list ("Attatched") | yes; typo and apology read human | no |
| S1 | Avery to Marcus: "…reconciling it against the option pool numbers now. will send it tonight." | yes | no: the promise is four words at the end of a one-line reply |
| S1 | Naomi (WSGR): v3 comments, "Marcus's team asked us on Tuesday…" | yes; associate register, long disclaimer signature | no: the pressure is a subordinate clause |
| S14 | Jordan: Veritas ingest failing, line 2 | yes; impact/cause/status structure an engineering lead would write; "Nothing you need to do tonight" | no: no urgency words; the P0 comes from who the customer is |
| S11 | Little Acorns: closed Thursday (HVAC) | yes; the operative line is bold in the middle of a caring paragraph | no: it reads as a notice, not an alert |

**Verdict:** no generator change. Traps are carried by relationships and timing, not by phrasing; nothing here is
greppable in the "tonight by 11pm, promise" sense. The one nit (a duplicated sender name before quoted history in
some team emails) is cosmetic and left alone.
