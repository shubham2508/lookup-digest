"""Validator (data_generation §9). Refuses generation on any failure; returns the list of problems."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from eval.manifest_schema import Manifest

from .render_eml import RenderedMessage
from .timeline import TZ, Timeline
from .world import World

LABEL_WORDS = re.compile(r"\b(trap|P0|P1|P2|P3|storyline|storylines|answer key)\b")
LABEL_WORD_EXPECTED = re.compile(r"\bexpected\b", re.IGNORECASE)
GENDERED = re.compile(r"\b(he|she|him|her|his|hers|himself|herself)\b", re.IGNORECASE)
NAME = re.compile(r"\b(Avery|Sam)\b")
INJECTION_ALLOWED = {"t-cloudledger-injection"}


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def ok(self) -> bool:
        return not self.problems


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?\n])\s+", text)


def check_reviewed(w: World, rep: Report) -> None:
    for s in w.storylines:
        if s.get("reviewed") is not True:
            rep.problems.append(f"{s['id']}: reviewed is not true — generation blocked")


def check_must_include(w: World, rendered: dict[str, list[RenderedMessage]], bulk: dict[str, RenderedMessage],
                       notes: list[dict], rep: Report) -> None:
    by_beat: dict[str, RenderedMessage] = {}
    for msgs in rendered.values():
        for m in msgs:
            if m.beat_ref:
                by_beat[m.beat_ref] = m
    note_text = {n["file"]: n["text"] for n in notes}
    for s in w.storylines:
        for b in s.get("beats", []):
            phrases = b.get("must_include") or []
            src = b.get("source")
            if src == "email":
                m = by_beat.get(b["ref"])
                if m is None:
                    rep.problems.append(f"{s['id']} {b['ref']}: no rendered message carries this beat_ref (thread {b.get('thread')})")
                    continue
                text = m.new_text + "\n" + "\n".join(x.get("body", "") for x in m.forwarded)
                for ph in phrases:
                    if ph not in text:
                        rep.problems.append(f"{s['id']} {b['ref']}: must_include {ph!r} missing in {m.source_id}/{m.local_id}")
                if b.get("thread") and m.source_id != b["thread"]:
                    rep.problems.append(f"{s['id']} {b['ref']}: rendered in {m.source_id}, spec says {b['thread']}")
                if (m.day, m.time) != (b["day"], b["time"]):
                    rep.problems.append(f"{s['id']} {b['ref']}: rendered at day {m.day} {m.time}, spec says day {b['day']} {b['time']}")
            elif src == "note":
                text = note_text.get(b["note"], "")
                if not text:
                    rep.problems.append(f"{s['id']} {b['ref']}: note {b['note']} not rendered")
                for ph in phrases:
                    if ph not in text:
                        rep.problems.append(f"{s['id']} {b['ref']}: must_include {ph!r} missing in note {b['note']}")
            elif src in ("newsletter", "automated"):
                iid = b.get("newsletter") or b.get("automated")
                m = bulk.get(iid)
                if m is None:
                    rep.problems.append(f"{s['id']} {b['ref']}: bulk item {iid} not rendered")
                    continue
                for ph in phrases:
                    if ph not in m.new_text and ph not in m.subject:
                        rep.problems.append(f"{s['id']} {b['ref']}: must_include {ph!r} missing in {iid}")
                if (m.day, m.time) != (b["day"], b["time"]):
                    rep.problems.append(f"{s['id']} {b['ref']}: {iid} at day {m.day} {m.time}, spec says day {b['day']} {b['time']}")
    # notes.yaml must_include
    for n in w.notes["notes"]:
        text = note_text.get(n["file"], "")
        for ph in n.get("must_include", []):
            if ph not in text:
                rep.problems.append(f"note {n['file']}: must_include {ph!r} missing")
    # background planted items with must_include
    pp = w.background.get("planted_patterns", {})
    planted = []
    inj = pp.get("injection", {}).get("item")
    if inj:
        planted.append(inj)
    sp = pp.get("stripe_payout", {}).get("item")
    if sp:
        planted.append(sp)
    for it in planted:
        m = bulk.get(it["id"])
        if m is None and it["id"] in rendered:
            m = rendered[it["id"]][0]
        if m is None:
            rep.problems.append(f"planted item {it['id']} not rendered")
            continue
        for ph in it.get("must_include", []):
            if ph not in m.new_text and ph not in m.subject:
                rep.problems.append(f"planted item {it['id']}: must_include {ph!r} missing")
    for case in w.background.get("classification_cases", []):
        for b in case.get("beats", []):
            tid = (case.get("thread") or {}).get("id")
            if not tid or not b.get("must_include"):
                continue
            msgs = rendered.get(tid)
            if not msgs:
                rep.problems.append(f"classification case {case['id']}: thread {tid} not rendered")
                continue
            text = "\n".join(m.new_text for m in msgs)
            for ph in b["must_include"]:
                if ph not in text:
                    rep.problems.append(f"classification case {case['id']} ({tid}): must_include {ph!r} missing")
    for pattern_key in ("talentbridge",):
        for it in pp.get(pattern_key, {}).get("items", []):
            if it["id"] not in rendered and it["id"] not in bulk:
                rep.problems.append(f"planted {pattern_key} item {it['id']} not rendered")
    for it in pp.get("expense_reports", {}).get("items", []):
        if it["id"] not in bulk:
            rep.problems.append(f"planted expense item {it['id']} not rendered")
    for nl in pp.get("newsletters", {}).get("decoy", []):
        if nl["id"] not in bulk:
            rep.problems.append(f"newsletter decoy {nl['id']} not rendered")


def check_inbox(inbox: Path, tl: Timeline, rep: Report) -> tuple[int, set[str]]:
    ids: set[str] = set()
    parsed = []
    for p in sorted(inbox.glob("*.eml")):
        with open(p, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        mid = msg["Message-ID"]
        if not mid:
            rep.problems.append(f"{p.name}: no Message-ID")
            continue
        if mid in ids:
            rep.problems.append(f"{p.name}: duplicate Message-ID {mid}")
        ids.add(mid)
        try:
            when = parsedate_to_datetime(msg["Date"])
        except (TypeError, ValueError):
            rep.problems.append(f"{p.name}: bad Date header {msg['Date']!r}")
            continue
        expected_offset = when.astimezone(TZ).utcoffset()
        if when.utcoffset() != expected_offset:
            rep.problems.append(f"{p.name}: Date offset {when.utcoffset()} is not the PT offset {expected_offset}")
        if not tl.in_window(when):
            rep.problems.append(f"{p.name}: Date {when.isoformat()} outside the 30-day window")
        parsed.append((p.name, msg))
    for name, msg in parsed:
        irt = msg["In-Reply-To"]
        if irt and irt not in ids:
            rep.problems.append(f"{name}: In-Reply-To {irt} does not resolve")
        refs = (msg["References"] or "").split()
        for r in refs:
            if r not in ids:
                rep.problems.append(f"{name}: References {r} does not resolve")
    return len(parsed), ids


def check_prose_words(rendered: dict[str, list[RenderedMessage]], bulk: dict[str, RenderedMessage], notes: list[dict], rep: Report) -> None:
    def scan(source: str, text: str, allow_injection: bool) -> None:
        for m in LABEL_WORDS.finditer(text):
            if allow_injection and m.group(0) == "P0":
                continue
            rep.problems.append(f"{source}: label word {m.group(0)!r} in prose")
        for sent in _sentences(text):
            for nm in NAME.finditer(sent):
                after = sent[nm.end():]
                g = GENDERED.search(after)
                if not g:
                    continue
                between = after[:g.start()]
                # another capitalised name between "Avery"/"Sam" and the pronoun → it refers to that person
                if re.search(r"\b[A-Z][a-z]+\b", between):
                    rep.warnings.append(f"{source}: pronoun after another name: {sent.strip()[:120]!r}")
                elif len(between.split()) <= 12:
                    rep.problems.append(f"{source}: gendered pronoun for {nm.group(0)}: {sent.strip()[:140]!r}")
                else:
                    rep.warnings.append(f"{source}: possible gendered pronoun near {nm.group(0)}: {sent.strip()[:120]!r}")
    for tid, msgs in rendered.items():
        for m in msgs:
            scan(f"{tid}/{m.local_id}", m.new_text + "\n" + "\n".join(x.get("body", "") for x in m.forwarded) + "\n" + m.subject, tid in INJECTION_ALLOWED)
    for iid, m in bulk.items():
        scan(iid, m.new_text + "\n" + m.subject, iid in INJECTION_ALLOWED)
    for n in notes:
        scan(f"note:{n['file']}", n["text"], False)


def check_counts(w: World, items_by_category: dict[str, int], rep: Report) -> None:
    targets = w.background["targets"]["categories"]
    for cat, spec in targets.items():
        target = spec["full"]
        got = items_by_category.get(cat, 0)
        rep.counts[cat] = got
        if abs(got - target) > max(1, round(0.10 * target)):
            rep.problems.append(f"category {cat}: {got} emails, target {target} ±10%")


def check_manifest_refs(manifest: Manifest, rep: Report) -> None:
    ids = {i.source_id for i in manifest.items}
    def ref_ok(sid: str) -> bool:
        return sid in ids

    def walk_args(owner: str, args: dict) -> None:
        for key in ("source_id",):
            v = args.get(key)
            if isinstance(v, str) and not ref_ok(v):
                rep.problems.append(f"assertion {owner}: {key} {v!r} is not a manifest item")
        for v in args.get("cites_any") or []:
            if not ref_ok(v):
                rep.problems.append(f"assertion {owner}: cites_any {v!r} is not a manifest item")

    for rd in manifest.run_days:
        for it in rd.items:
            for c in it.cites_any:
                if not ref_ok(c):
                    rep.problems.append(f"run_day {rd.run_day} item {it.about}: cites_any {c!r} is not a manifest item")
        if rd.one_thing:
            for c in rd.one_thing.cites_any:
                if not ref_ok(c):
                    rep.problems.append(f"run_day {rd.run_day} one_thing: cites_any {c!r} is not a manifest item")
    for a in manifest.assertions:
        walk_args(a.id, a.args)
    for v in manifest.variants:
        for a in v.assertions:
            walk_args(a.id, a.args)
        for rd in v.run_days:
            for it in rd.items:
                for c in it.cites_any:
                    if not ref_ok(c):
                        rep.problems.append(f"variant {v.id} run_day {rd.run_day}: cites_any {c!r} is not a manifest item")
    emails = {c.email for c in manifest.contacts}
    for a in manifest.assertions:
        e = a.args.get("email")
        if isinstance(e, str) and e not in emails:
            rep.problems.append(f"assertion {a.id}: contact {e!r} is not in the manifest")


def check_storyline_coverage(w: World, rendered: dict[str, list[RenderedMessage]], rep: Report) -> None:
    for s in w.storylines:
        for t in s.get("threads", []):
            if t["id"] not in rendered:
                rep.problems.append(f"{s['id']}: thread {t['id']} has no prose file")
