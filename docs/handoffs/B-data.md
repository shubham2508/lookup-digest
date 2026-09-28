# Track B · Data — handoff

You are **the generator**: you write the world (storylines, expectations, people) and then the prose of every
email, note and task yourself, and you build the code that turns those files into `data/<world>/` and the answer
key `eval/manifests/<world>.yaml`. There is no generator API model: this session (Fable 5.1) is the generator.

## Read first, in this order
1. `CLAUDE.md` (golden rules; the addendum).
2. This file.
3. `specs/data_generation.md` (all). Then `specs/extraction_schema.md` §7 and `eval/manifest_schema.py` (the answer-key contract you must emit). Then `specs/eval.md` §3–§4 (the trap assertions and P0 cases the manifest must carry).
4. `profile/profile.md` (who these people are to Avery), `docs/sample_digest.md` (tone of the world).
5. `docs/DESIGN_LOG.md` §9–§10 for the *why*; §3.8 for sender categories.

## Never open
`digest/` internals and `prompts/` (you must not tune the world to the pipeline), `runs/`. Importing
`digest.schemas` (about-key validation, vocabularies) and `eval.manifest_schema` is fine.

## Milestone M1 · draft the dev world  → **gate: Shubham approves every `expectations:` block**
Deliver, under `world/dev/`:
- `world.yaml` per data_generation §3: company, Avery, orgs, people (id, name, emails, org, title, `truth`, `style`, `signature`), edges. Named addresses for reference customers; one role alias on a non-reference customer. Gender-neutral for Avery and Sam throughout.
- `storylines/S01-cap-table-promise.yaml` … `S16-…yaml` per §4 format and the §5 table: `beats` (day, time, source, thread, from, to, cc, event, `must_include`), `labels`, `expectations`, `variants`, `reviewed: false`.
- `background.yaml` per §6: category counts (internal ~110, notifications ~70, newsletters ~80, customers ~60, SaaS marketing ~60, investors/board ~40, recruiters ~25, vendors/misc ~25, hiring ~20, lawyer ~15, personal ~15), every must-not item with its reason, the planted patterns (TalentBridge ×3, ~80 newsletters with only S5/S13 attachable + the EU AI Act decoy, the injection email, three expense reports, the Stripe failed payout), every classification case, and the mini-arcs for P2/P3 coverage (10–12, 2–4 emails each).
- Notes and tasks specs per §7 (10 notes, 5 tasks, cap-table promise absent from tasks).
- Calendar spec: recurring 1:1s, Avery-organized deep-work blocks, Lumen over the block, the stale Marcus Friday event, the declined pipeline review, Sam's events with realistic `CREATED` times.

**Expectations checklist, per storyline** (Shubham reviews against this):
- For each run day 26–30: present or absent; candidate type(s); priority (or band); section; expected action types; `cites_any` thread ids; `one_thing` where it applies.
- Variant expectations (e.g. S1 `fulfilled` → absent on day 30).
- Per-thread labels: type, domain, intent, about keys (use the fixed `kind` vocabulary), ball, sender relationship (category, subtype, stage), commitments and asks with `due_day`, schedule mentions, role changes, claims, stage signals, suspicious.
- Contacts touched, with stage timelines and handovers.
- Which eval.md §3 assertion(s) the storyline satisfies, expressed as `AssertionKind` + args.
Storyline S3 needs the weekend math to work for the chosen anchor (day 30 is a Thursday; day 26 is Sunday).
Dev anchor is decided: **2026-09-24** (Thursday, day 30; day 1 = Wed 2026-08-26; run days 26–30 = Sun 20 – Thu 24 Sept; all PDT). Put `anchor: 2026-09-24` in `world/dev/world.yaml`; `digest generate --anchor` overrides it. Storylines stay day-relative.

## Milestone M2 · generator code + prose + render + validate
1. **Prose files, written by you** (batches by thread or category; parallel subagents are fine). Recommended layout, yours to adjust as long as the manifest contract holds:
   - `world/<world>/prose/threads/<thread_id>.yaml`: `thread_id, subject, storyline, messages: [{id, beat_ref, day, time, from, to, cc, body, signature, quotes_previous: bool, forwarded_from: id|null}]`
   - `world/<world>/prose/bulk/<category>.yaml`: many items, each with `day, time, from, subject, body, labels{category, must_not, reason, classification_case}` and, for newsletters, the items with `attaches_to`.
   - `world/<world>/prose/notes/<file>.md` (rendered as-is with the `Date: … | Attendees: …` first line) and `tasks.md`.
   - `world/<world>/calendar.yaml`: events with organizer, attendees + PARTSTAT, RRULE, created/last-modified.
   Writing rules (prompts.md G1–G3): `must_include` phrases verbatim; never state labels or hint at the trap (no "trap", "P0", "storyline", "expected"); realistic, varied length; per-person `style` from `world.yaml`; hardness knobs on ~30% of human mail (typos, long signatures, quoted history, indirect phrasing, mixed topics); Avery's own sent mail in 20–25% of human threads; ~20 emails per weekday, ~6 per weekend day; beats cluster in days 20–30.
2. **Renderers (code, `generator/`)**: day → date via `--anchor` with `zoneinfo("America/Los_Angeles")` (DST-correct offsets); `.eml` per RFC 5322 (`Message-ID`, `In-Reply-To`, `References`, `Date` with offset, `From/To/Cc/Subject`, `List-Unsubscribe`/`Precedence: bulk` on bulk mail, `>` quoted history on replies, forwarded header blocks); `.ics` with `RRULE`, `PARTSTAT`, `ORGANIZER`, `CREATED`, `LAST-MODIFIED`; notes; `tasks.md` with mtime set 12 days before day 30. Variants render to `data/<world>__<variant>/`.
3. **Manifest emitter**: build `eval.manifest_schema.Manifest` from world + labels + expectations (items with `expected` extraction, contacts, about-key merge pairs, run-day expectations, assertions, variants, sim_avery answers) → `eval/manifests/<world>.yaml`.
4. **Validator (§9)**, run by `digest generate` and refusing on failure: every `must_include` verbatim; every `In-Reply-To` resolves; timestamps in-window with correct offsets; every label references an existing source id; no label words in prose; no gendered pronouns for Avery or Sam (check sentences that mention either); category counts within ±10%; any `reviewed: false` storyline blocks generation.
5. `generator/cli.py: generate(world, anchor, seed)` implemented; reproducible from world files + prose + seed.
Acceptance: validator passes; ~490–520 `.eml`; both `.ics` load; the manifest validates; `uv run pytest` green.

**Later (M8):** `world/heldout/` with a different anchor, the same trap *types* in different disguises and, where possible, different names. Do it in a fresh session. Never tune it to results.

## Rules of the road
- Everything in the world is data the pipeline must earn; don't make it easy (role addresses for reference customers were rejected for that reason).
- Questions → `OPEN_QUESTIONS.md`, then stop. Tests: `tests/test_b_<topic>.py`. Commit `[B-data] M1: …`, your paths only.
- Finish a session with a STATUS.md line and `/export sessions/B-data_M<n>.txt`.
