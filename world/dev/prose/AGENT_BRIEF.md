# Brief for prose-writing subagents (Track B, M2)

You are writing the synthetic email/notes corpus for a triage-tool evaluation. The world is fictional. Read, in order:
1. `world/dev/prose/FORMAT.md` (file formats; follow it exactly, the renderer parses these files).
2. `world/dev/world.yaml` (every person's id, email, title, `style`, `signature`; orgs and domains).
3. Your assignment's storyline files under `world/dev/storylines/` and/or `world/dev/background.yaml`.
4. `world/dev/prose/threads/t-marcus-ts.yaml` (a finished example).

Hard rules
- **Never open** `digest/`, `prompts/`, `runs/`, `eval/`, `tests/`. You only read `world/dev/**` and write under `world/dev/prose/**`.
- Every `must_include` phrase listed for a beat (storylines) or an item (background.yaml) appears **verbatim** in that message's `body` (same case, same punctuation, same currency symbols). Check each one before you finish.
- Never write the words: trap, P0, P1, P2, P3, storyline, expected, "must include", answer key, eval, label. Never hint that something is a test.
- Never gender Avery Chen or Sam Park: no he/she/him/her/his/hers for either of them, anywhere (other people may be gendered freely).
- Use each sender's `style` and `signature` from world.yaml. `signature: default` appends the world.yaml signature; use `signature: none` for Avery's short replies and for casual/internal one-liners; use a literal string for a deliberately long or different signature.
- Realistic, varied lengths (2 lines to 30 lines). About 30% of human mail carries a hardness knob: a typo, an indirect phrasing ("I'll get that over to you" instead of "I will send X by Y"), two topics in one email, a P.S., an over-long signature, or a quoted history (`quotes_previous: true` on replies).
- Replies in a thread set `reply_to` to the local id they answer and usually `quotes_previous: true`. Subjects: only the first message's subject is written; replies get "Re: " from the renderer.
- Threads are Avery's mailbox: Avery is in `to` or `cc` of every message (or the message is from Avery), except messages inside a `forward_of` chain.
- Dates: `day` 1..30 (see FORMAT.md for the weekday table); weekend days have far less mail; business hours mostly, with some evening mail from Avery, Sam, Jordan, Tomás.
- Don't invent people with the same names as world.yaml people. One-off senders use `{name, email}` with a plausible fictional domain (never a real company's brand as the sender org unless it is a well-known SaaS tool or newsletter named in background.yaml).
- IDs: use the thread ids given in the storyline/background files exactly. For filler you create, use the id prefix your assignment gives you. Bulk item ids must be unique across the world (use your prefix + day + a slug).

Label vocabularies (for `labels.expected` blocks on background items you author)
- `type`: human_thread · newsletter · marketing · automated · note · task
- `domain`: work · personal        `intent_primary`: ask · escalation · commitment_update · fyi · social · promotional
- `ball_awaiting`: avery · other · nobody · unclear
- `sender_relationship.category`: family · capital · customer · team · hiring · vendor · network · external_visibility · legal_gov · cold_inbound · automated · unresolved
- about keys: `<kind>:<slug>[:<qualifier>]`, lowercase, hyphens; kind ∈ deal, offer, candidate, rollout, renewal, meeting, report, approval, invoice, incident, pricing, hiring-req, board-update, contract, family, other
- automated `action_kind`: signature · approval · payment_issue · security · none
- `reason` (must-not): use the reason names in background.yaml (newsletter, marketing, automated_fyi, lone_recruiter, routine_pipeline_fyi, internal_fyi, closed_by_courtesy, last_word_avery, handled_by_team, cold_pitch, accepted_meeting_confirmation, social_no_ask, fyi_no_action, …).

When done, reply with: the list of files written, the count of messages per file, and any must_include phrase you could not place (there should be none).
