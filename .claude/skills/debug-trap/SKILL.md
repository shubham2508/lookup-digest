---
name: debug-trap
description: Debug a failing eval assertion, a missing or wrong digest item, or a bad P0 in the Daily Digest. Use when a report in eval/reports/ lists a failed assertion, when P0 recall is under 100%, when an item that should be on the page is missing, buried in "Also pending", or wrongly shown, or when the user asks "why did the digest do X". Traces the item from source email to page, finds the first stage that lost it, fixes that stage without leaking test data, and re-measures.
---

# Debug a failing trap

The digest is a fixed pipeline; every stage writes an artifact. A wrong digest is always a wrong artifact line in one
stage. Find the first stage that lost the item, fix that stage, re-measure. Never guess from the final page alone.

## 0. Before touching anything

- Is a batch running? `pgrep -fl "digest eval --matrix|cli.main run"`. If yes, do NOT edit `digest/`, `prompts/`,
  `config/` or `eval/`: a step that starts mid-edit crashes or mixes versions. Wait, or work in a worktree
  (`git worktree add ../lookup-digest-fix -b fix-<name>`) and merge after the batch ends.
- Never open `world/` or `eval/manifests/` from product code, and never tune on `heldout` results.

## 1. Read the failure

In `eval/reports/<world>_<date>.md`, section 3 "Trap assertions → Failed", each line reads:

```
- **S14-d30-present** (`item_present`; S14 day 30) → stage **compose**: rendered but wrong ['section'] … [compose.json](runs/dev/…)
```

Note the assertion id, the storyline (S1–S16 or BG-…), the run day, the **attributed stage**, and the artifact link.
The expectation itself is in `eval/manifests/<world>.yaml` (search the assertion id); read it to know what "correct" is.
P0 misses are listed per day in section 2 as `P0 missing: <about key>`.

## 2. Trace the item through the run

Open the run folder `runs/<world>/<YYYY-MM-DDT06-00>[_suffix]/`, or the debug UI (`uv run digest ui`, open the run,
tab **Why each item**, search the topic). Walk the stages in order and stop at the first one that is wrong:

| Stage | Artifact | Question to ask |
|---|---|---|
| ingest / normalize | `run.json` (threads, freshness), `degradations.jsonl` | Is the email there at all? Dated before as_of? Threaded right? |
| extract (LLM) | `extractions.jsonl` (search the `thread:<Message-ID>`) | Did it capture the ask / promise / ball / date correctly? Evidence quote valid? |
| link (LLM) | `links.jsonl` | Did the linker merge or match the right things, and is its reason sensible? |
| compute (code) | `candidates.jsonl` | Is there a candidate of the expected type and topic key, with the right facts (business days, overlaps, tier)? |
| triage (LLM) | `triage.jsonl` (by candidate_id) | include? priority? section? proposed actions? Read `why`. |
| reduce (code) | `reduce.json` | Merged into the right item? Over the cap (`overflow`)? |
| compose (LLM) | `compose.json` | Placed, cut to `cut_ids`, or the one thing? |
| materialize | `actions.jsonl` | Right action type, draft text, assumptions? |
| verify (code) | `verify.json` | Was it fixed or dropped by a hard rule? |

For any LLM stage, `trace.jsonl` holds the exact prompt sent and the raw output (UI tab **LLM calls**; the tag is
the thread id, `triage:c1,c2,…`, `compose`, `draft:<item>:<type>`, or `link:<task>`).

## 3. Fix the stage that lost it

| Lost in | Fix in | Notes |
|---|---|---|
| extract | `prompts/extractor.md` rules | Bump `version:`; this invalidates the extraction cache (a cold re-read costs ~$0.4 per world) |
| link | `prompts/linker.md` / `topic_grouper.md`, or the hard pre-filters in `digest/compute/candidates.py` | Code narrows options by people / dates / kind; the LLM decides sameness. No word-similarity thresholds |
| compute | the rule in `digest/compute/candidates.py` (one function per candidate type) | Add or fix a unit test in `tests/test_a_compute.py` |
| triage | `prompts/triage.md` rules | Policy (who matters) comes from `profile/profile.md` via the compiled profile, never from names typed into the prompt |
| reduce / compose placement | `digest/reduce/__init__.py`, `validate_compose` in `digest/compose/__init__.py` | Guarantees (P0 never cut, page limit) belong in code, not only in the prompt |
| materialize | `prompts/materializer.md`, `digest/materialize/__init__.py` | |
| verify | `digest/verify/__init__.py` | Hard rules are code |

**Leak rule (hard):** a prompt example must never reuse a person, company, email or storyline from `world/dev/` or
`world/heldout/`. Use the made-up cast already in the prompts (Dara Quinn / Brightwater, Oren Tal / Halden Mills,
Nia Okoro, Jun Park, Pellucid Freight). Teach the pattern, not the answer. Check before committing:

```
grep -n -i -E "marcus|cap table|renee|halberd|veritas|northstar|mei-|lumen|tom[aá]s|keystone|ipv|wren" prompts/*.md
```

Also never write the expected answer of a storyline into a rule (e.g. "$3.4M"); rules name the category of behavior.

## 4. Re-measure

```
uv run pytest -q                                               # unit tests
uv run digest run --world dev --as-of 2026-09-24T06:00          # the failing morning (cached, cheap)
uv run digest eval --world dev                                  # re-score what exists
```

A history-dependent trap (escalation, "third time flagged", resolved items) needs the earlier mornings run first, in
order: `digest eval --matrix --world dev` does all of it.

If a prompt changed, append a line to `eval/history.md`: date · prompt · old→new version · P0 recall, traps passed,
must-not rate, one-thing accuracy before → after · one-line note. Commit with the stage in the message.

## 5. When the expectation itself looks wrong

Do not change the answer key to make a test pass. Write the case in `OPEN_QUESTIONS.md` (what, where, options,
suggestion) and ask Shubham; the storylines were approved by a human and only a human changes them.
