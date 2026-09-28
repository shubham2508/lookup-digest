# world/dev/prose — the prose files the renderer turns into data/dev/ (Track B, M2)

Written by the Data session (Fable 5.1). Code (`generator/`) adds every header, Message-ID, In-Reply-To/References,
quoted history, forwarded blocks, dates with PT offsets, bulk headers, signatures, the notes' `Date:` line and the
`<!-- last-modified -->` line. **Prose files contain only what a person typed.**

Day → date: day 1 = Wed 2026-08-26 … day 20 = Mon 09-14, 21 Tue, 22 Wed, 23 Thu, 24 Fri, 25 Sat, 26 Sun 09-20,
27 Mon 09-21, 28 Tue 09-22, 29 Wed 09-23, 30 Thu 2026-09-24. Times are PT "HH:MM".

## threads/<thread_id>.yaml — one human email thread (storyline threads and background arcs)
```yaml
thread_id: t-marcus-ts
subject: "Series A - updated cap table?"      # first message's subject; replies get "Re: " automatically
storyline: S1                                  # S1..S16, a BG-<case> tag, or null
category: investors_board                      # manifest BackgroundCategory
labels: null                                   # only for threads NOT labeled in a storyline/background.yaml; else null
messages:
  - id: m1                                     # local id, unique within the file
    beat_ref: S1.b2                            # storyline beat ref, or null
    day: 28
    time: "16:42"
    from: marcus                               # a person id from world.yaml, or {name: "...", email: "..."} for a one-off
    to: [avery]                                # person ids, one-off {name,email}, or the aliases parents_list / team_list / eng_list
    cc: []
    reply_to: null                             # local id of the message this replies to (sets In-Reply-To/References)
    quotes_previous: false                     # true → the renderer appends "On <date>, <name> wrote:" + "> " quoted history of reply_to
    forward_of: null                           # a forwarded chain: list of {from, day, time, to, cc, subject, body}, oldest first
    signature: default                         # default = the sender's signature from world.yaml · none · or a literal string
    body: |
      Avery,

      Before we go further on the term sheet I need the updated cap table ...
```
Rules: `must_include` phrases from the storyline beat appear **verbatim** in `body` (case and punctuation exact).
Never write the words trap, P0, storyline, expected, or "must include". Never gender Avery or Sam (no he/she/his/her
for them; use names or "you"). Write in the sender's `style` from world.yaml. Vary length. Hardness knobs on ~30%
of human mail: a typo or two, a long signature (set `signature` to a literal longer block), indirect phrasing,
mixed topics, a P.S. Avery's own mail is short and lowercase-ish, signs "Avery" or nothing (`signature: none`).

## bulk/<category>.yaml — many single emails (newsletters, marketing, notifications, recruiters, one-off FYIs)
```yaml
category: newsletters
items:
  - id: nl-stratechery-0826                    # unique source id: nl-… newsletters · mkt-… marketing · auto-… automated · t-… human one-offs
    day: 1
    time: "06:30"
    from: {name: "Stratechery", email: "email@stratechery.com"}   # or a person id
    to: [avery]
    subject: "..."
    bulk: true                                 # adds List-Unsubscribe + Precedence: bulk (newsletters, marketing, mass mail)
    signature: none
    body: |
      ...
    labels:
      kind: newsletter                         # newsletter · marketing · automated · thread
      must_not: true
      reason: newsletter                       # free text from background.yaml's reason vocabulary
      classification_case: null
      expected: null                           # newsletters with attachable items and action-bearing automated mail carry their ExpectedExtraction here
```
An automated item's `expected`: `{type: automated, automated: {system, action_bearing, action_kind, about}}`.
A newsletter with items: `{type: newsletter, news_items: [{headline_hint, topics, entities, attaches_to}]}`.
A human one-off (kind: thread): `{type: human_thread, domain, intent_primary, about, ball_awaiting, closed_by_courtesy, sender_relationship: {category, subtype}}`.

## notes/<file>.md — the note body only
The renderer prepends `<!-- last-modified: … -->` and `Date: YYYY-MM-DD | Attendees: …` from notes.yaml. Start
the file with the `# Title` line. Plant every phrase listed under `must_include` for that note in notes.yaml verbatim.

## tasks.md — written by the renderer from notes.yaml (no prose file)
