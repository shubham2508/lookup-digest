<!-- last-modified: 2026-09-23T08:45:00-07:00 -->
Date: 2026-09-21 | Attendees: (none)

# Q2 (FY27, Nov-Jan) planning doc - owner Avery

Status: draft v2. Review at the Thu Sep 24 14:30 planning sync (Avery, Priya, Jordan, Tomás, Kim). Two open comments below, unresolved; resolve before the sync or take them live.

## Goals for the quarter
1. Close the Series A and get the money in the bank before the holidays.
2. Halberd full-plant rollout (Oct 6) stable through Q2; convert to the expansion tier.
3. Two new mid-market logos (Meridian, Ridgeway) on the Plant Bundle.
4. Ship multi-line ingest so new lines stop needing hand-holding.

## Engineering
- Hiring: two backend reqs. Mei (offer going out) fills one; the other stays open through Q2.
- Designer req: paused until the raise closes; revisit in January.
- On-call: current rotation is four people (Jordan, Sofia, Dev, Omar). Jordan wants a fifth.

> [Jordan, 2026-09-22]: Four people on a weekly rotation means one week in four on call, plus swaps whenever someone is out. Omar and Dev already traded twice this month. If the second backend hire lands in Q2, I want that person in the rotation by month two, and Mateo on a daytime-only tier before then. Can "5th on-call person" be an explicit Q2 headcount line? (open comment)

- Backfill / ingest: throughput has been fine; cost has not. See Priya's inference note.

> [Priya, 2026-09-23]: backfill concurrency cap needs to be a decision in this doc, not a footnote. cap at 2 and the halberd backfill finishes ~1 week later; leave it and the inference line stays ~2x model through the raise. numbers are in my email from tuesday. pick one before thursday. (open comment)

## GTM
- Plant Bundle at $48k/yr for new mid-market; sign-off needed so Meridian gets a quote this week.
- Veritas renewal slipped to next quarter (Walter); Tomás owns the follow-up. Model it in Q2, not Q1.
- Northstar: keep the weekly cadence with Grace; watch the vendor-review chatter.

## Vendors / tooling
- Analytics: Lumen - decision hinges on ingestion + backfill behaviour; Metrika renews 9/25. Demo Thursday. If Lumen can't backfill 12 months without a manual export, stay on Metrika.
- Everything else renews as-is.

## Finance
- Runway 19 months without the A. Q2 budget assumes no new spend beyond the backend hire.

## Before Thursday
- Resolve Jordan's and Priya's comments (above).
- Kim: attach the Q2 budget sheet.
