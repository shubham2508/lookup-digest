# On-call & infra review - Mar 17

Jordan, Priya, Arjun, Felix, Nora. Avery declined (deep-work block) and asked for the notes.

## On-call
- Current: five engineers in a weekly primary rotation, no compensation beyond comp time. Two people have raised it in 1:1s; Felix's pager weeks have averaged three night pages.
- Decision: pay a stipend of $400/week to the primary on-call engineer, starting with the Apr 1 rotation. Secondary stays unpaid. Cost about $20.8k/yr at current headcount (Nora).
- This is a comp change, so it needs Avery's sign-off. Nora needs it in Gusto by Fri 3/27 to land in the first April payroll. Jordan to write it up for Avery this week.
- April rotation gets published once the stipend is confirmed.

## Infra
- Northstar go-live freeze: Mon 3/30 – Thu 4/2 on the Northstar tenant. Change freeze for everyone else Tue 3/31 – Wed 4/1.
- GPU reserved commit expires 3/31. Priya owns the recommendation (finance review this afternoon).
- Halberd Line 3 MES upgrade (Halberd's side) tentatively Wed 3/25 evening. Arjun to coordinate with Sanjay and take primary that night.
- Sentry noise: 60% of alerts last month were the Coastline CSV parser. Kofi to fix the root cause or downgrade the alert.

## Actions
- Jordan: stipend write-up to Avery (sign-off needed by 3/27).
- Nora: payroll change once approved.
- Arjun: MES upgrade coordination with Sanjay.
- Priya: GPU recommendation.
