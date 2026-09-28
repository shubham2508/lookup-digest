<!-- last-modified: 2026-03-25T08:45:00-07:00 -->
Date: 2026-03-23 | Attendees: (none)

# H1 FY27 (Apr-Sep) planning doc - owner Avery

Status: draft v3 · review at the Thu 3/26 14:00 planning sync · comments inline, please

## 1. Goals for the half
1. Close the Series A and land the operating model the board signs off on.
2. Two more reference-grade plants live: Northstar's second site after the Apr 1 go-live, and Coastline line 2.
3. Renew Halberd and Veritas without discounting more than 5%.
4. Ship the scheduling module out of beta by July.

## 2. Engineering
- Headcount: hold at the current team until the round closes; the second backend req stays paused (hiring sync 3/18). Kenji's start date assumed May 4.
- On-call: move to a paid primary rotation from Apr 1 (Jordan's proposal; separate sign-off).
- Reliability: p99 ingest latency target 4s; MES connector conformance suite covering the Halberd and Northstar variants.

> **open comment — Jordan Liu, 2026-03-24 17:35:** "Hold at the current team" plus a paid on-call rotation still leaves five people carrying the pager. If Kenji slips past May the rotation math doesn't work. Can we say explicitly what happens if the round closes after June?

## 3. GTM
- Pipeline target: $1.8M new ARR in the half. Pinewood and Ironclad are the two qualified prospects today.
- Reference program: one case study per reference customer by end of June (Tobias to be asked at the QBR).
- Pricing: no list changes in H1.

## 4. Security & compliance
- SOC 2 Type II renewal window opens in May. Bastion Compliance is the current platform; the contract auto-renews 3/27 for 12 months unless we cancel.
- Quillon Security trial — decision hinges on evidence collection coverage: do their integrations cover our stack without the manual uploads we do in Bastion every quarter? Demo Thu 3/26 09:30. If Quillon covers 80%+ of controls automatically, cancel Bastion before the 27th; otherwise renew Bastion and revisit in H2.
- Pen test: annual retest scheduled for June (same vendor as the Feb test).

## 5. Finance
- Runway: 16 months pre-round. Budget assumes the GPU commit is renewed at a 1-year term (Priya to confirm).
- Board reporting: monthly written update during the raise, then back to quarterly.

> **open comment — Priya Iyer, 2026-03-25 08:44:** budget line assumes a 1-year GPU renewal but nobody has said yes to that. if we go on-demand this number is ~$9k/mo higher from apr. need the decision before this doc is final.

## 6. Open questions for Thursday
- Second backend req: unpause on term sheet, or on close?
- Do we keep Bastion for a transition quarter even if Quillon wins?
- Case-study timing with Northstar: before or after their second site?
