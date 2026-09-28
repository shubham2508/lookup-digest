# Brief for held-out authoring subagents (Track B, M8)

You are authoring part of the **held-out** synthetic world for a triage-tool evaluation: a second, independent world
with the same trap *types* as `world/dev/` but different disguises, people, and topics. It is fictional. Read, in order:
1. `world/heldout/README.md`: time table (anchor 2026-03-26, DST on day 12) and the **disguise map**, which is binding
   (about keys, thread ids, key beat days/times, one-thing ownership).
2. `world/heldout/world.yaml`: every person id, email, title, `style`, `signature`. Use only these ids. If you truly
   need a new recurring person, don't edit world.yaml; use a one-off `{name, email}` in prose and list it in your final reply.
3. `world/dev/README.md` (storyline file format and conventions) and `world/dev/prose/FORMAT.md` (prose file format;
   follow it exactly, the renderer parses these files). Example: `world/dev/prose/threads/t-marcus-ts.yaml`.
4. The **dev counterpart** of each storyline you own (`world/dev/storylines/Sxx-*.yaml`). Mirror its depth: summary,
   threads, beats (with `must_include` and `hardness`), labels (with `expected` blocks per `eval/manifest_schema.py`
   ExpectedExtraction), contacts, about_keys, expectations for **every** run day 26–30, assertions (kinds from
   `eval/manifest_schema.py` AssertionKind), sim_avery, variants. Change the disguise, not the mechanism: the same
   candidate types, the same kinds of assertions, the same day-relative logic. Recompute every day/time-dependent
   fact (business days, hours pending, stall days) for the held-out beats.

Hard rules
- **Never open** `digest/`, `prompts/`, `runs/`, `tests/`, or `eval/` other than `eval/manifest_schema.py`.
  Don't tune anything to the pipeline.
- `reviewed: false` in every storyline file (Shubham's review gate).
- Every `must_include` phrase appears **verbatim** in the prose body that renders its beat (same case, punctuation,
  currency symbols). Check each one before you finish.
- Never write the words trap, P0, P1, P2, P3, storyline, expected, "must include", answer key, eval, label in any
  **prose** (bodies, subjects, notes). They are fine inside storyline YAML keys/values.
- Never gender Avery Chen or Sam Park anywhere (no he/she/him/her/his/hers/himself/herself for them), in YAML
  `event:` text and summaries too. Other people may be gendered freely.
- Use each sender's `style` and `signature` from world.yaml. Avery's mail: short, lowercase-ish, `signature: none`
  or signs "Avery". ~30% of human mail carries a hardness knob (typo, indirect phrasing, two topics, P.S., long
  signature, quoted history).
- Avery is in `to`/`cc` of every message in a thread file (or is the sender), except inside a `forward_of` chain.
- No beat or message between 02:00 and 03:00 on day 12 (DST gap). Weekends light; business hours mostly.
- About keys: `<kind>:<slug>[:<qualifier>]`, kind ∈ deal, offer, candidate, rollout, renewal, meeting, report,
  approval, invoice, incident, pricing, hiring-req, board-update, contract, family, other.
- Only S1 declares `one_thing`.

Outputs
- Storyline YAML: `world/heldout/storylines/Sxx-<name>.yaml`.
- One prose file per human thread: `world/heldout/prose/threads/<thread_id>.yaml` (FORMAT.md). Include every beat
  message plus the history messages the mechanism needs (e.g. baseline cadence, earlier replies).
- Storyline newsletters / automated items: `world/heldout/prose/bulk/<category>-<Sxx>.yaml` (FORMAT.md bulk shape,
  top-level `category:` set, item `labels` filled including `expected`).
- Final reply: files written, messages per file, emails per background category your storyline contributes, calendar
  events you rely on (uid, title, day, start–end, organizer, attendees+PARTSTAT, created day/time), note plants you
  rely on (file, phrase that must appear verbatim), task rows you rely on, and any must_include you could not place.
