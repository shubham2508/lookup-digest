# world/heldout — format conventions and disguise map (Track B, M8)

Everything here is the generator's script. The digest never reads it. **Never tune prompts on this world's results.**
File formats are exactly those of `world/dev/` (see `world/dev/README.md`) and prose follows
`world/dev/prose/FORMAT.md`; this file only records what differs.

## Time
anchor = **2026-03-26** (Thursday, day 30). Day 1 = Wed 2026-02-25. Days 1–11 are PST (-08:00); **day 12 = Sun
2026-03-08 is the spring-forward day**; days 12–30 are PDT (-07:00). No beat is scheduled 02:00–03:00 on day 12.
Run days 26–30 = Sun 03-22 … Thu 03-26, each as of 06:00 PT. Weekday layout is identical to dev (day 1 is a Wednesday
in both), so business-day math lines up; beat times and topics differ.

| day | date | | day | date | | day | date |
|---|---|---|---|---|---|---|---|
| 1 | Wed 02-25 | | 19 | Sun 03-15 | | 27 | Mon 03-23 |
| 5 | Sun 03-01 | | 20 | Mon 03-16 | | 28 | Tue 03-24 |
| 8 | Wed 03-04 | | 21 | Tue 03-17 | | 29 | Wed 03-25 |
| 12 | Sun 03-08 (DST) | | 22 | Wed 03-18 | | 30 | Thu 03-26 |
| 13 | Mon 03-09 | | 23 | Thu 03-19 | | 31 | Fri 03-27 |
| 14 | Tue 03-10 | | 24 | Fri 03-20 | | 34 | Mon 03-30 |
| 15 | Wed 03-11 | | 25 | Sat 03-21 | | 35 | Tue 03-31 |
| 18 | Sat 03-14 | | 26 | Sun 03-22 | | 36 | Wed 04-01 |

## Names
Names fixed by `profile/profile.md` stay: Avery, Sam, Wren, Priya, Marcus (IPV), Diane, Jordan, Tomás, Ben (WSGR),
Tessera, Halberd, Northstar, Veritas. Everyone else is new (see `world.yaml`). The three reference customers swap
roles relative to dev so no customer carries the same trap twice.

## Disguise map (same trap type → different disguise)

| # | dev | held-out | about keys (canonical) | thread / source ids |
|---|---|---|---|---|
| S1 | cap-table promise "will send it tonight"; Naomi follows up | Avery promises Marcus the **revised operating model** "in your inbox before midnight" (day 28 21:52); never sent; Ben's disclosure-schedule thread, **Imogen** follows up day 29; `fulfilled` variant | `deal:series-a:operating-model` | `t-ipv-model`, `t-disclosure-schedules` |
| S2 | diligence call Fri→Mon, Elena joins; 06:05 mail | calendar: **IPV technical diligence Tue 3/31 13:00** (organizer Owen); email day 27 moves it **earlier, to Fri 3/27 11:00**; **Julia** (operating partner) joins; Julia's prep ask lands day 29 **06:04** | `meeting:ipv-technical-diligence`, `deal:series-a:diligence-prep` | `t-ipv-diligence-date`, `t-ipv-diligence-prep`, `event:ipv-tech-diligence-20260331` |
| S3 | Marcus separate thread, Fri 17:52, quiet over weekend | Marcus asks Fri day 24 16:48 for **gross revenue retention by cohort**; Avery never answers; quiet business days [0,0,1,2,3] on runs 26–30 | `deal:series-a:retention-question` | `t-marcus-grr` |
| S4 | David Kim (Aperture) "let's talk soon" | **Farah Siddiqui (Larkspur)**; Avery day 10: "I'll send the cohort data and we'll find time after the 15th" — nothing since | `deal:series-a:larkspur` | `t-larkspur-followup` (+ history threads) |
| S5 | Renee (Halberd) "Oct 6 still on?" + sprint note + Factory Floor item | **Elise (Northstar)** day 29 13:52: "is the **April 1** SAP connector go-live still on?"; `eng-standup.md` says on track; *Plant Ops Digest* item about Northstar's Fresno plant | `rollout:northstar:apr-1` | `t-northstar-golive`, `nl-plantops-112` |
| S6 | Northstar cadence drop + Tomás forwards 14 msgs "thoughts?" | **Veritas (Dmitri)** cadence drop; Tomás forwards a **12-message** thread with Hugo (Veritas finance) on the annual vendor review, "thoughts?" | `other:veritas-cadence`, `renewal:veritas` | `t-veritas-*`, `t-fwd-veritas-vendor-review` |
| S7 | Veritas handover Simon→Nadia; renewal pushed twice | **Halberd handover Greta→Tobias** (day 14, "taking over from Greta"); **Martin (CFO)** pushes renewal a second time ("after our fiscal close"); `profile_update` | `other:halberd-procurement-lead`, `renewal:halberd` | `t-halberd-*` |
| S8 | Mei, DocuSign 48h, competing offer Friday | **Kenji Mori**, **Dropbox Sign** pending since day 28 08:15; Jordan: competing offer expires **Friday noon** | `offer:kenji-mori` | `t-kenji-loop`, `t-kenji-offer`, `t-kenji-thanks`, `auto-dropboxsign-kenji` |
| S9 | designer req paused; Keystone sends designers; Theo stalled | **second backend req paused** (hiring-sync day 22); **Northbeam** (retained) still sends backend candidates; **designer Clara Voss** onsite day 22, unmoved | `hiring-req:backend-2`, `candidate:clara-voss`, `candidate:yusuf-demir`, `other:recruiter-northbeam`, `other:profile-open-reqs` | `t-northbeam-*`, `t-clara-*` |
| S10 | monthly board updates; draft $3.2M vs $3.4M | minutes: "a short written update **every month until the round closes**", last sent **Feb 9**; draft says **$3.2M**; finance review says **$3.6M** | `board-update:monthly`, `other:profile-board-cadence`, `other:profile-arr` | notes + `t-diane-*` |
| S11 | pediatrician 3pm vs 2:30 Q2 sync; daycare closure; Sam email | Sam adds **"Wren - ENT follow-up"** Thu 11:15–12:00 at **22:17** day 29, overlapping the **11:00 Halberd renewal call**; Sunflower preschool **early dismissal 12:30** Thursday; Sam's multi-topic email | `family:ent-appointment`, `family:early-dismissal` | `t-sam-*`, `t-sunflower-*`, `event:wren-ent-20260326` |
| S12 | Lumen demo 10:30 Thu over block; Jordan 1:1 inside block | **Quillon Security** books **Thu 09:30–10:15** (organizer Maya); Avery's own recurring **Thu 10:30 "Architecture review - Priya / Avery"** inside the block; Maya asks: SOC 2 evidence walkthrough vs pen-test scoping; Bastion auto-renews day 31 | `meeting:quillon-demo`, `meeting:architecture-review` | `t-quillon-demo`, `event:quillon-demo-20260326`, `event:arch-review-thu` |
| S13 | Priya emails about inference-cost overrun; model price-cut newsletter | Priya emails day 28 20:41: **GPU reserved-capacity commit expires Mar 31**, provider raising on-demand prices Apr 1, needs a yes/no on a 1-year commit by Friday; *Compute Ledger* newsletter reports the price rise | `other:gpu-commit-decision` | `t-priya-gpu`, `nl-computeledger-41` |
| S14 | Jordan 21:00 day 29: Veritas ingest failing | Jordan day 29 **21:12**: Halberd Line 3 station events arriving **8 hours off** since an MES push; night-shift false late alerts; rollback needs Halberd's OK (Tobias) | `incident:halberd:timestamps` | `t-halberd-timestamps` |
| S15 | declined pipeline review → pricing sign-off | Avery **declined Jordan's "On-call & infra review"** Tue day 21 09:30 (over the block); it decided a **$400/week on-call stipend** starting Apr 1 that needs Avery's sign-off; `infra-review.md` + Jordan email | `approval:oncall-stipend` | `t-oncall-stipend`, `event:infra-review-20260317`, `note:infra-review` |
| S16 | Tomás pricing feedback "by Friday", sent | Avery promised Nora **comments on the 409A draft "by Friday"** (day 20); sent day 24 in a **separate thread** "409A - my notes" | `report:409a-draft` | `t-409a-draft`, `t-409a-notes` |

**One thing:** only S1 declares `one_thing` (days 29 and 30, citing `t-ipv-model`). No other file declares one.

**06:05 mail (eval.md §3):** S2's Julia email at day 29 **06:04** — absent on the day-29 run, present on day 30.

**Background (background.yaml):** HireVector ×3 in 7 days (days 23, 26, 28), the injection inside a NimbusPay
"partnership" email, three Brex expense reports (day 27), a Gusto payroll-funding debit failure (day 28 04:40),
the EU Cyber Resilience Act newsletter decoy, and every §6 classification case with new people.

**Assertion ids** follow dev's scheme (`S1-…`, `BG-…`, `V-…`); they only need to be unique inside this world.

## Pinned shared sources (storylines cite these; `notes.yaml` / `calendar.yaml` must match)

**Notes** (`must_include` phrases verbatim; `note:<file-stem>` in world files):

| file | kind | day time | attendees | must_include | plants (storyline) |
|---|---|---|---|---|---|
| board-meeting-minutes.md | meeting_notes | 2 16:45 | avery, priya, diane, nora | "every month until the round closes", "Feb 9" | monthly written update during the raise, last sent Feb 9; ARR $3.2M as of Jan 31 (S10) |
| investor-update-draft.md | draft | 19 22:05 | — | "$3.2M", "TBD" | Avery's half-written March update, ARR $3.2M, Pipeline TBD (S10) |
| finance-review.md | meeting_notes | 21 16:00 | avery, nora, priya | "ARR $3.6M", "GPU reserved commit" | ARR $3.6M as of Mar 15 (S10); GPU reserved commit ends 3/31, Priya to recommend (S13); payroll funding account switched to new bank (BG Gusto) |
| h1-planning.md | draft | 27 17:20 (mtime 29 08:45) | — | "evidence collection", "open comment" | two open comments (Jordan day 28, Priya day 29); Quillon eval hinges on evidence collection coverage, Bastion renews 3/27; review at Thu 3/26 14:00 sync (BG-h1, S12) |
| eng-standup.md | status | 28 09:40 | jordan, arjun, felix, kofi, carmen, hana | "on track for Apr 1", "non-blocking" | Northstar SAP connector on track for Apr 1, two non-blocking issues (S5); Halberd Line 3 MES upgrade Wed evening, Arjun on call (S14) |
| gtm-weekly.md | meeting_notes | 27 16:10 | avery, tomas, leo, hana | "after our fiscal close", "2nd push" | Martin pushed the Halberd renewal again (S7); Veritas: Dmitri quieter, Hugo running a vendor review (S6); Pinewood pilot scoping |
| hiring-sync.md | meeting_notes | 22 11:30 | avery, jordan, tomas | "paused until the A closes", "debrief TBD" | second backend req paused, Jordan to tell Northbeam; Clara onsite today, debrief TBD; Kenji offer approved; Maren portfolio review next Thu (S9, S8) |
| infra-review.md | meeting_notes | 21 10:45 | jordan, priya, arjun, felix, nora | "$400/week", "needs Avery's sign-off" | Avery declined; decision: on-call stipend $400/week per primary from Apr 1, needs Avery's sign-off (S15) |
| avery-todos.md | todo | 20 07:40 | — | "March update", "pen-test summary to Northstar" | "send Diane the March update (by 3/13)" duplicates task 1 with a different date; "pen-test summary to Northstar" already done per email on day 16 (S5 history) |
| customer-health-review.md | meeting_notes | 21 15:30 | avery, tomas, jordan, hana | "slower to respond", "green" | Veritas: Dmitri slower to respond this week, no tickets (S6); Northstar green, Apr 1 (S5); Halberd: Tobias new since 3/10, renewal timing unclear (S7) |

**tasks.md** (mtime day 18 18:05; 12 days old on day 30): 1 "Send Diane the March investor update" due day 20 ·
2 "Finalize H1 planning doc for Thursday's sync" due day 30 · 3 "Approve February expenses in Brex" due day 25 ·
4 "Send Northstar the pen-test summary" due day 16 (done per email day 16) · 5 "Review cyber policy renewal from Keel"
due day 55. Absent: `deal:series-a:operating-model` (S1), `report:409a-draft` (S16).

**Day-30 work calendar (Thu 03-26):** Deep work 09:00–11:00 (Avery, recurring Tue/Thu) · Quillon demo 09:30–10:15
(organizer Maya, Avery NEEDS-ACTION, created day 28 16:50) · Architecture review - Priya / Avery 10:30–11:00 (Avery,
recurring Thu) · Halberd QBR - Tobias intro 11:00–11:45 (organizer Tomás; Avery, Tobias, Hana ACCEPTED; created day 16)
· Lunch / email 12:30–13:15 (Avery, recurring weekdays) · Tidewater intro - Marco Bellini 12:30–13:00 (organizer
Marco, Avery ACCEPTED, created day 24) · H1 planning sync 14:00–15:00 (Avery) · Portfolio review - Maren Holt
16:00–16:45 (organizer Priya; Avery ACCEPTED; Maren ACCEPTED; created day 25).
**Family calendar:** Wren - ENT follow-up 11:15–12:00 day 30 (organizer Sam, created day 29 22:17, Avery
NEEDS-ACTION) overlaps the Halberd QBR (S11); Sunflower early dismissal 12:30 (email only, not on the calendar)
collides with the Tidewater intro (S11).
