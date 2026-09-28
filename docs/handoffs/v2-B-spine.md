# v2 · Track B · Spine, sweeps, safety nets — handoff

You build the **entity spine**, **retrieval**, the three **sweeps**, and trim compute to **safety nets** with
linker-based reconciliation and merge. Start with one line: **"Track B, v2"**.

Work in the worktree `/Users/shubham/Desktop/work/lookup-digest-v2-b-spine` (branch `v2-b-spine`; `.env` is there).
Never edit the main checkout.

## Read first, in this order
1. `CLAUDE.md` golden rules 2, 3, 5, 6, 7, 8 (the rest is v1 process). Rule 3 now reads: code for math, thresholds,
   hard rules and safety nets; LLMs read raw content for judgment; structure is an index and a floor, never a gate.
2. `specs/PIVOT_SPEC.md` §3, §5.2–5.4 and `MIGRATION_PLAN.md` (all; §2 has Shubham's corrections: **no string
   similarity anywhere; sameness is the linker's decision**).
3. `digest/findings.py`, the `Finding`/`SweepOutput`/`SignatureFacts`/`ContactClassification` block in
   `digest/schemas.py`, `tests/test_findings.py`.
4. `digest/compute/contacts.py`, `context.py`, `candidates.py`, `linker.py`, `jev.py`, `signals.py`;
   `tests/test_a_compute.py` (your tests move to `tests/test_b_compute.py`).
5. `prompts/triage.md` lines 14–33 (rubric, taxonomy: copy verbatim into the sweep prompts) and `prompts/linker.md`.

## Never open
`world/`, `eval/manifests/`, `generator/`, `eval/`. You may read `data/<world>/` and `tests/fixtures/mini/`.

## You own
`digest/compute/*.py` except `__init__.py` (A owns orchestration; you expose functions), `digest/compute/sweeps.py`
(new), `prompts/calendar_sweep.md`, `prompts/notes_tasks_sweep.md`, `prompts/news_sweep.md`,
`prompts/contact_classifier.md`, `prompts/signature_parser.md`, `prompts/linker.md`, `tests/test_b_compute.py`,
`tests/test_b_sweeps.py`. Do not touch `digest/pipeline.py`, `digest/read/`, `digest/compose/`, `eval/`,
`digest/schemas.py`, `digest/llm.py`, `digest/findings.py` (ask the orchestrator).

## Deliverables (A calls these by exactly these signatures)

**B1 · spine** (`contacts.py`): `build_contacts(world, profile, linker, llm, ctx) -> ContactDirectory`.
Keep: resolution order (profile → role-at-org via linker → internal domain → automated → learned domain), behavior
stats, org-tier inheritance at outside firms only (`compute/__init__.py::_inherit_org_tiers`, move it here).
Replace the extractor's `sender_observations` with:
- `signature_parser` (`prompts/signature_parser.md`, `SignatureFacts`): one cached call per **new contact**, input =
  its signature blocks from normalize (`NormalizedMessage.signature`) and the From header; cached by content hash.
- `contact_classifier` (`prompts/contact_classifier.md`, `ContactClassification`): one cached call per contact not
  resolved by the profile; input = signature facts, domain, the profile rules that might match (incl. role-at-org),
  3–5 representative messages (clean bodies, capped), behavior stats. `unresolved` when evidence is thin. Cache key
  = contact id + evidence hash (re-runs only when new evidence arrives).
Signatures and bodies go in labeled untrusted data blocks.

**B2 · retrieval** (`context.py`): `retrieve(thread, world, directory, as_of, cap_tokens=4000) -> list[ContextRef]`
(`ContextRef(source_id: str, text: str)`): events in [as_of − 7d, as_of + 7d] sharing a participant or org; notes
mentioning a participant, org or subject word; tasks with participant/keyword overlap; the previous two threads with
the same participants (first/last message excerpts, not LLM summaries). Most relevant first (same participants >
same org > keyword), capped. Word overlap is allowed **here only**: retrieval chooses what is read, it decides nothing.

**B3 · sweeps** (`sweeps.py`): `run_sweeps(world, directory, findings, profile, settings, llm, ctx, as_of) -> list[Finding]`
with `cache_salt=as_of.date().isoformat()`; each sweep is one `SweepOutput` call (batch if the input exceeds ~60k
tokens), its output through `check_citations` with a `SourceIndex` over what it saw.
| Sweep | Input | Looks for |
|---|---|---|
| calendar | both calendars normalized for [as_of, as_of + 2 business days] + last 14 days of declines; attendee contact records; profile blocks and family rules; titles + contradictions of reader findings | deep-work bookings by others, family collisions, double bookings, declined-meeting fallout, meetings needing prep, entries contradicted by email |
| notes + tasks | all notes and tasks.md raw, note dates, tasks mtime; reader finding titles | Avery's promises and action items, overdue cadences (monthly board update), drafts with stale facts ($3.2M vs $3.4M), tasks contradicted by email, open comments, paused plans |
| news | newsletter issues raw (router type `newsletter`), in batches; titles/entities of today's `needs_avery: yes` findings | only items that change something on Avery's plate; cite the issue; nothing otherwise |
The calendar sweep's `event:` citations quote the event title; build the SourceIndex accordingly.

**B4 · safety nets** (`candidates.py`, ~350 lines left): `safety_nets(ci) -> list[Finding]`, `origin="safety_net"`,
`kind` = the v1 type name, `why` carries the computed fact. Keep exactly: P0-contact waiting ≥ threshold business
days (`reply_owed`/`quiet_thread`), reference-customer inbound past end of business day, deep-work overlap by
another organizer (today or next business day), shared-family event or personal date overlapping accepted work
(today → +2 days), ≥3 recruiter messages from one domain in 7 days → one `recruiter_pattern`, stale/missing source,
suspicious instructions (never P0), action-bearing automated message with a deadline. **Delete** commitments,
contradictions, declined_meetings, hiring_stalls, cadence_drops, obligations, tasks_due, profile_drift,
news_attachments and `aboutkeys.py`. `ComputeInputs` may lose the extraction fields it no longer has.

**B5 · reconcile and merge** (`linker.py` + a small `merge.py`):
`reconcile(findings, nets, linker) -> (findings, rescues)`: for each net finding, the linker (Jev first, LLM when
unsure, `task="net_covers_finding"`) picks the reader/sweep finding on the same thread/entities that is the same
issue; if one, attach the computed fact to its `why` and drop the net finding; if none, keep it with
`rescued_by_safety_net=True` and log `{"net": kind, "title": …}`. `group_findings(findings, linker) -> list[AboutMerge]`:
reuse `Linker.group_topics` on `about` tags with the finding title as text; only same-kind tags group. Reduce (A's
side, unchanged) already joins same-thread and same-about items.

**Acceptance:** unit tests for every kept rule, for reconcile (a net covered vs a rescue), and for the classifier
input (no name-based guessing); a small driver `python -m digest.compute.sweeps --world dev --as-of 2026-09-24T06:00`
that prints sweep findings; `uv run pytest -q` green in your worktree. Write `docs/handoffs/v2-B-STATUS.md` and stop.

## Budget
Contacts and sweeps are cached; a full Thursday sweep set ≈ $0.05. Never run two pipelines at once in one worktree.

## Commits
`[v2-B] B3: sweeps …`, your paths only. The orchestrator merges `v2-b-spine` into `main`.

## Unattended mode (Shubham is asleep)
Do not stop to ask. When something is ambiguous: write it to `OPEN_QUESTIONS.md` (what, options, what you picked),
take the default from `MIGRATION_PLAN.md` §5 or the most conservative option, and continue. When a permission or
tool prompt would block you, prefer the path that does not need it. Finish every deliverable you can, write your
STATUS file, and stop only then. The orchestrator reviews everything at the merge.
