<!-- last-modified: 2026-09-22T09:30:00-07:00 -->
Date: 2026-09-22 | Attendees: Jordan Liu, Sofia Andrade, Dev Patel, Omar Haddad, Lena Hoffmann, Yuki Sato

# Standup notes - week of Sep 21

Kept by Jordan. Mon/Tue so far; the rest of the week gets added as we go.

## Mon Sep 21
- JL: Halberd rollout on track for Oct 6. Cutover checklist went to Renee from Yuki this afternoon. Remaining: operator training Sep 29 (14 people), final data-mapping sign-off from Joel.
- SA: Veritas line 2 ingest. Ivan's sample feed parsed clean on Friday; still waiting on the production schema from Ivan. Target Wed for ingest readiness; will pair with Yuki on the cutover window.
- DP: multi-line ingest refactor, PR #412 up for review. Swapped on-call with Omar this week.
- OH: on call. Quiet weekend, one alert (Northstar exception-report cron, self-healed). Reviewing #412.
- LH: regression pass on the Oct 6 build. Two issues opened, both non-blocking: (1) export CSV encoding - non-ASCII plant names come out mangled in Excel, BOM missing; (2) dashboard date filter resets to "last 7 days" after a page refresh. Neither blocks Oct 6; both tagged for the Oct 13 patch.
- YS: Halberd checklist sent; Veritas line 2 dates confirmed with Nadia; Brightline SSO group-mapping question answered by Jordan, closed.

## Tue Sep 22
- JL: no change on Halberd, still on track for Oct 6. Theo's debrief still needs a slot; will find one this week. Lumen demo is Thursday, Priya running it.
- SA: production schema from Ivan promised today. Field mapping is ready for the sample; will diff the real one the moment it lands. Still targeting Wed for readiness.
- DP: #412 review comments addressed; wants it merged before the Veritas cutover, not after.
- OH: on call, quiet. Picked up the CSV encoding fix (LH's #1) since it's a one-liner; date filter (#2) goes to Dev after #412.
- LH: re-ran the Halberd smoke suite on the fixed build: all green except the two above. Started the Veritas line 2 test plan.
- YS: prepping the Sep 29 training deck; Halberd operator one-pager draft to Renee tomorrow.

## Parking lot
- On-call rotation: still four people. Jordan raised it in the Q2 planning doc.
- Inference spend: Priya is writing it up for Avery; may mean capping backfill concurrency. No change to Halberd dates until Avery decides.
