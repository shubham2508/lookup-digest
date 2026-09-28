# world/dev — format conventions (Track B, M1)

Everything here is the generator's script. The digest never reads it. Days are world-relative (day 30 = `anchor`).
Run days 26–30 = Sun 2026-09-20 … Thu 2026-09-24; each run is "as of" 06:00 PT, so a beat at `day: 29, time: "21:00"`
is first visible on the **day 30** run and a beat at `day: 29, time: "06:05"` is also first visible on day 30.

## Files
- `world.yaml` — orgs, people (with `truth`, `style`, `signature`), edges, anchor.
- `storylines/S01…S16.yaml` — one arc each (format below). `reviewed: false` blocks generation until Shubham flips it.
- `background.yaml` — category targets (full + pass-1), every must-not item with its reason, planted patterns,
  classification cases, mini-arcs.
- `calendar.yaml` — every event in `work.ics` and `shared_family.ics` (organizer, attendees + PARTSTAT, RRULE, CREATED).
- `notes.yaml` — the 10 notes and `tasks.md` (what each plants, plus labels).
- `variants.yaml` — honesty run variants (stale_inbox, no_notes, corrupt_ics, built-in stale tasks) and their assertions.

## Storyline file
```yaml
id: S1                      # matches manifest storyline tags
name: cap-table-promise
reviewed: false             # Shubham sets true after reviewing `expectations` and `assertions`
tier_truth: P0
summary: ...                # what happens, what it tests, why the timing works
threads: [{id, subject, category}]         # every email thread this storyline renders (ids are manifest source_ids)
beats: [{ref, day, time, source, thread|event|note, from, to, cc, event, must_include, hardness}]
labels: [{thread|note|event|task, category, must_not_surface?, must_not_reason?, classification_case?, expected: {...}}]
   # `expected` follows eval/manifest_schema.py ExpectedExtraction field by field
contacts: [{id, category, subtype, tier, stages, replaces?, rules?, note}]   # contacts touched, stage timelines
about_keys: {should_merge: [[a, b]], should_not_merge: [[a, b]]}
expectations:               # THE ANSWER KEY, one entry per run day 26–30 (spec §4). Fields map to RunDayExpectation.
  - run_day: 29
    candidates: [{type, about, facts_hint}]       # compute must produce these
    items: [{about, priority | priority_band, section, actions | actions_any, cites_any, one_thing?, ambiguity?, notes}]
    absent: [about keys that must not appear]
    one_thing: {about, cites_any}                  # only where this storyline owns the one thing
    unasserted: "reason"                           # explicit "not scored today" (never silent)
assertions: [{id, kind, run_day, args, description}]   # AssertionKind + args, eval.md §3
sim_avery: [{scope_about|scope_contact, intended_option, rationale}]
simulate: [...]             # assertions that only apply under `digest simulate` (args.mode: simulate); M9, deferred
variants: [{id, extra_beats, expectations, assertions}]   # storyline variants → data/dev__<id>/
```

## Conventions
- **Present** means the item appears as a full item, a one-liner, or an "Also pending" line. `absent` means none of those.
- `actions`: every listed type must be proposed. `actions_any`: at least one of them. Action types are `digest.schemas.ActionType`.
- `priority_band`: any of the listed priorities passes; `priority` is exact. P0 gate uses `priority: P0` rows only.
- `cites_any`: at least one cited source id must be in the list. World files use short symbolic ids: threads `t-…`,
  newsletters `nl-…`, automated `auto-…`, marketing `mkt-…`, notes `note:<file>`, events `event:<uid>`, tasks `task:<n>`.
  **The M2 manifest emitter renders them in the product's forms** (OPEN_QUESTIONS #6a/#7b): a thread's manifest
  `source_id` stays the symbolic id but every item lists its `messages[].message_id`, which is how the scorer joins the
  product's `thread:<root Message-ID>` / `msg:<Message-ID>` ids to the manifest; notes become `note:notes/<file>.md`;
  tasks become `task:<slug-of-title>` (slug function shared with `digest/ingest`, to be pinned at M2); events stay
  `event:<uid>`.
- Staleness that survives `git clone` (OPEN_QUESTIONS #6c): the renderer writes `<!-- last-modified: <ISO> -->` as the
  first line of `tasks.md` and of every note in addition to setting the file mtime.
- Canonical about keys for computed candidates (proposed; see OPEN_QUESTIONS #9): `other:<org>-cadence` (cadence_drop),
  `other:recruiter-<org>` (recruiter_pattern), `meeting:<event-slug>` (calendar conflicts on work events),
  `family:<event-slug>` (family conflicts), `other:profile-<field>` (profile_drift), `other:stale-<source>` (stale_source).
- `must_include` phrases are rendered verbatim; prose never contains "trap", "P0", "storyline", "expected".
- Business days = Mon–Fri, no holidays. "Business days quiet" = weekday dates strictly after the message date and strictly
  before the run date (OPEN_QUESTIONS #8). S3's boundary depends on it.

## Prose and rendering (M2)
- `prose/FORMAT.md` is the contract for the prose files (`prose/threads/*.yaml`, `prose/bulk/*.yaml`, `prose/notes/*.md`,
  `prose/variants/<id>/*.yaml`); `prose/AGENT_BRIEF.md` is the writing brief the prose subagents followed.
- `digest generate --world dev [--anchor YYYY-MM-DD] [--seed N]` → `data/dev/` (+ `data/dev__fulfilled/`) and
  `eval/manifests/dev.yaml`; it refuses to write the manifest when the validator (`generator/validate.py`,
  data_generation §9) reports a problem. Reproducible from the world files + prose + seed.
- Renderers: `generator/render_eml.py` (RFC 5322; RFC 2047 headers; `>` quoted history; Gmail-style forwarded blocks
  with nested quotes), `generator/render_ics.py` (VTIMEZONE, RRULE, PARTSTAT, ORGANIZER, CREATED/LAST-MODIFIED),
  `generator/render_notes.py` (`<!-- last-modified -->` + `Date: … | Attendees: …` header, mtimes).
