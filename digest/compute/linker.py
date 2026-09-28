"""The linker: LLM decisions for "do these two descriptions name the same real thing?".

It replaces word-similarity thresholds in compute (OPEN_QUESTIONS #16). Code still narrows the options with hard
facts first (same people, dates within a week, later in time, same topic kind); the LLM only decides sameness among
those, and gives a one-line reason that is logged. Calls are batched (one per question type per run) and cached
like every other LLM call, so reruns are free and repeatable.

Without an LLM (unit tests, or the call failed twice) the linker answers "no match" and compute falls back to exact
key equality: a missed link is visible in the digest; an invented link would not be.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import Field

from ..llm import LLM, LLMError
from ..prompts import load_prompt
from ..schemas import Model


class LinkOption(Model):
    id: str
    text: str


class LinkQuestion(Model):
    id: str
    item: str
    options: list[LinkOption]


class LinkAnswer(Model):
    question_id: str
    matches: list[str] = Field(description="ids of the options that name the same real thing; empty if none")
    reason: str = Field(description="one line: what makes them the same, or why none is")


class LinkBatch(Model):
    answers: list[LinkAnswer]


class TopicGroup(Model):
    members: list[str] = Field(description="topic keys that name one and the same thing; at least two")
    reason: str


class TopicGroups(Model):
    groups: list[TopicGroup]


TASKS = {
    "topics": ("Each item is a topic key with what a document said about it. Options are other keys of the same kind. "
               "Pick the one that names exactly the same concrete thing (same deal step, same person's hiring loop, same "
               "incident, same rollout), or none. A general topic and a specific part of it are different things."),
    "promise_in_tasks": ("Each item is a promise Avery made. Options are Avery's open tasks and todo lines. Match an option only "
                         "if it tracks the same deliverable to the same person (sending the cap table ≠ reviewing the cap table)."),
    "fulfilled_elsewhere": ("Each item is an open promise Avery made. Options are later messages, in other threads, where Avery "
                            "delivered something. Match only if the option delivers exactly what was promised."),
    "task_done_in_email": ("Each item is an open task on Avery's list. Options are things email or notes show as already done. "
                           "Match only if the option completes that same task."),
    "email_meeting_to_event": ("Each item is a meeting mentioned in an email (moved, confirmed). Options are calendar events with the "
                               "same people on nearby dates. Match the one event that is the same meeting, or none."),
    "declined_meeting_fallout": ("Each item is a meeting Avery declined. Options are decisions, agreements and requests dated after it. "
                                 "Match the ones that came out of that meeting or need Avery's sign-off because of it."),
    "role_at_org": ("Each item is a sender (name, email, signature title, organization). Options are roles at named "
                    "organizations from the owner's profile. Match only if the sender holds that role at one of those "
                    "organizations (an acting or new holder of the role counts; a colleague in a different role does not)."),
    "net_covers_finding": ("Each item is a fact a code check computed (a message waiting N business days for Avery, a "
                           "meeting inside a protected block, a family event over a work meeting, an automated request to "
                           "sign or approve). Options are issues that readers found in the same thread, event or with the "
                           "same people, or the reader's own summary of the thread the fact is about. Match the option that "
                           "already accounts for the fact: the same issue (the same unanswered message, meeting or request), "
                           "or a reader summary showing the thread needs nothing more from Avery (a thank-you, a confirmation, "
                           "an FYI, something a teammate handled). The bracket before each option is a fact code checked: "
                           "[same message] means the option cites the very message the fact is about, so it accounts for "
                           "it even when the reader split that message into several issues (pick one); [same event] "
                           "likewise; [same thread] and [same person] only say where to look. Match none when the fact may "
                           "still need Avery and no option is about it. Another issue with the same person is not the "
                           "same issue."),
    "news_to_open_item": ("Each item is a newsletter story. Options are things Avery is dealing with right now. Match only if the "
                          "story changes what Avery should do or say about that item (a price change on a cost Avery is deciding, "
                          "a customer's public statement before a reply to that customer). General industry or fundraising news "
                          "matches nothing."),
}


@dataclass
class Linker:
    llm: LLM | None
    ctx: object | None = None
    log: list[dict] = field(default_factory=list)
    decider: object | None = None   # compute/jev.JevDecider: Jev answers first; the LLM is the fallback
    jev_min_p: float = 0.0          # pick-one questions where Jev's top probability is below this go to the LLM

    def _jev(self, task: str, questions: list[LinkQuestion], min_p: float = 0.0) -> tuple[dict[str, list[str]], list[LinkQuestion]] | None:
        """Jev's picks, plus the questions it was unsure of (top probability below min_p) for the LLM to decide."""
        if self.decider is None:
            return None
        from .jev import JevError

        try:
            picks = self.decider.pick(task, TASKS[task], questions)
        except JevError as e:
            if self.ctx is not None:
                self.ctx.degrade("compute", f"link:{task}", "jev_failed_fallback_llm", detail=str(e)[:200])
            return None
        out: dict[str, list[str]] = {}
        unsure: list[LinkQuestion] = []
        for q in questions:
            choice, prob = picks.get(q.id, (None, 0.0))
            if prob < min_p:
                unsure.append(q)
                continue
            out[q.id] = [choice] if choice else []
            self.log.append({"task": task, "question": q.id, "matches": out[q.id], "reason": f"jev p={prob:.2f}", "by": "jev"})
        return out, unsure

    def match(self, task: str, questions: list[LinkQuestion]) -> dict[str, list[str]]:
        """{question id → option ids judged the same thing}. Only options offered can come back."""
        questions = [q for q in questions if q.options]
        if not questions:
            return {}
        jev = self._jev(task, questions, self.jev_min_p)
        done: dict[str, list[str]] = {}
        if jev is not None:
            done, questions = jev
            if not questions:
                return done
        if self.llm is None:
            return done
        prompt = load_prompt("linker")
        text = prompt.render(task=TASKS[task], questions=json.dumps([q.model_dump() for q in questions], ensure_ascii=False))
        try:
            r = self.llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": text}], LinkBatch,
                                  tag=f"link:{task}")
        except LLMError as e:
            if self.ctx is not None:
                self.ctx.degrade("compute", f"link:{task}", type(e).__name__, detail=str(e)[:200])
            return done
        offered = {q.id: {o.id for o in q.options} for q in questions}
        out: dict[str, list[str]] = dict(done)
        for a in r.output.answers:
            ok = [m for m in a.matches if m in offered.get(a.question_id, set())]
            if a.question_id in offered:
                out[a.question_id] = ok
                self.log.append({"task": task, "question": a.question_id, "matches": ok, "reason": a.reason,
                                 **({"by": "llm_after_unsure_jev"} if jev is not None else {})})
        return out

    def group_topics(self, by_kind: dict[str, list[dict]]) -> list[list[str]]:
        """Groups of topic keys naming the same thing. by_kind: kind → [{key, text}]. Only same-kind keys group
        (plus offer/candidate for one person's loop), and every member must be a key that was offered."""
        payload = {k: v for k, v in by_kind.items() if len(v) >= 2}
        if not payload:
            return []
        if self.decider is not None:
            # Jev: one pick-one question per key ("which other key of this kind is the same thing, or none?")
            qs, ids = [], {}
            for _kind, rows in payload.items():
                for i, row in enumerate(rows):
                    opts = []
                    for j, other in enumerate(rows):
                        if j != i:
                            oid = f"k{len(ids)}"
                            ids[oid] = other["key"]
                            opts.append(LinkOption(id=oid, text=f"{other['key']}: {other['text']}"))
                    qs.append(LinkQuestion(id=f"q{len(qs)}|{row['key']}", item=f"{row['key']}: {row['text']}", options=opts))
            res = self._jev("topics", qs)   # topic grouping keeps every Jev pick (no unsure fallback)
            if res is not None:
                jev = res[0]
                groups = []
                for q in qs:
                    for m in jev.get(q.id, []):
                        groups.append([q.id.split("|", 1)[1], ids[m]])
                return groups
        if self.llm is None:
            return []
        prompt = load_prompt("topic_grouper")
        text = prompt.render(topics=json.dumps(payload, ensure_ascii=False))
        try:
            r = self.llm.complete(prompt.model_role, prompt.version_tag, [{"role": "system", "content": text}], TopicGroups,
                                  tag="link:topics")
        except LLMError as e:
            if self.ctx is not None:
                self.ctx.degrade("compute", "link:topics", type(e).__name__, detail=str(e)[:200])
            return []
        known = {row["key"]: kind for kind, rows in by_kind.items() for row in rows}
        groups: list[list[str]] = []
        for g in r.output.groups:
            members = [m for m in dict.fromkeys(g.members) if m in known]
            kinds = {known[m] for m in members}
            if len(members) < 2 or not (len(kinds) == 1 or kinds == {"offer", "candidate"}):
                continue
            groups.append(members)
            self.log.append({"task": "topics", "matches": members, "reason": g.reason})
        return groups
