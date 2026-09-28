# Standup notes - week of Mar 23

Jordan's running notes, Tue Mar 24. Jordan, Arjun, Felix, Kofi, Carmen, Hana.

## Northstar - SAP connector (go-live Wed Apr 1)
- Status: on track for Apr 1. Cutover runbook v2 went to Elise and Rosa (Fresno) on Friday; Hana walks their schedulers through it Thursday.
- Two non-blocking issues open from Carmen's regression pass: NS-412 (CSV export drops the plant-code column when the filter is empty) and NS-415 (dashboard date picker shows UTC on the Fresno tenant). Neither is in the go-live path; both targeted for the Apr 7 patch.
- Kofi: SAP IDoc retry logic merged (#1187). Load test against Northstar's QA tenant Wednesday.
- Freeze window on the Northstar tenant: Mon 3/30 – Thu 4/2.

## Halberd
- Line 3 MES upgrade (Sanjay's team) is Wed evening 3/25 from 18:00. Arjun on call for it, Felix backup. Sanjay says the station event payloads should be unchanged; we have asked for a sample from their staging MES anyway.
- QBR Thu 11:00 with Tobias (new procurement lead). Hana has the deck.

## Veritas
- Quiet. No tickets this week. Anika's lot-number question (VC-88) answered Monday.

## Coastline
- Purchasing mailbox asked for the invoice format change again; Ruth handling (support #2291).

## Platform
- Carmen: nightly suite 412/412 green after the timezone fix in #1181.
- Felix: pager handoff Thursday. Wants the stipend decision before the April rotation is published; needs Avery's sign-off, Jordan chasing.
- Kofi asked for a day on the Quillon integration spike before Thursday's demo. Jordan: half a day.
