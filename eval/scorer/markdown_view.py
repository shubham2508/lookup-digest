"""Score a digest from its markdown alone (eval.md §8: the naive baseline writes only digest.md).

The pipeline's items carry ids, about keys and evidence ids in compose/reduce/actions; the baseline's do not. Here
each markdown item becomes a RenderedItem by:
- resolving its citations (`[email: Marcus, Tue 16:42]`, `[note: sprint-week.md]`, `[task: …]`) to manifest
  sources through the message labels (sender name + time, then weekday/date to break ties);
- inferring an about key from the item text against the day's labeled keys (slug tokens found in the text, plus
  a bonus when a cited source is labeled with that key); unique best score ≥ 0.5, else None;
- parsing action lines by their §9.3 prefixes (draft text, targets, assumptions).
The same matching rules then apply as for the pipeline (fuzzy about or cites_any; claimed keys are not stolen).
"""
from __future__ import annotations

import re

from eval.manifest_schema import Manifest

from .artifacts import RenderedItem
from .common import about_tokens
from .digest_md import Citation, MdItem, ParsedDigest
from .match import SourceIndex, norm_text, split_about

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
WEEKDAY_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b", re.I)
MONTH_DAY_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

ACTION_TYPES = [
    (re.compile(r"^↳\s*Draft to\s+([^:]+):?\s*(.*)$", re.I), "reply"),
    (re.compile(r"^↳\s*Forward to\s+(.+?)\s+with:?\s*(.*)$", re.I), "forward_delegate"),
    (re.compile(r"^↳\s*Propose\b:?\s*(.*)$", re.I), "calendar_response"),
    (re.compile(r"^↳\s*Approve\b\s*(.*)$", re.I), "approve"),
    (re.compile(r"^↳\s*Open\b\s*(.*)$", re.I), "read"),
    (re.compile(r"^↳\s*(?:Message|Text)\s+(\S+)\s*(.*)$", re.I), "message_person"),
    (re.compile(r"^☐\s*(.*)$"), "task"),
    (re.compile(r"^Q\d+\s*[·:.\-]\s*(.*)$"), "question"),
    (re.compile(r"^Watching:\s*(.*)$", re.I), "watch"),
    (re.compile(r"^(?:↳\s*Decide|Options|Recommend\w*)\b:?\s*(.*)$", re.I), "decide"),
]


# ----------------------------------------------------------------------------- citations
def _name_matches(name: str, email: str, manifest: Manifest, is_avery: bool) -> bool:
    n = norm_text(name).replace(" fwd", "").strip()
    if not n:
        return False
    if is_avery:
        return n in ("avery", "avery chen", "you")
    tokens = set(n.split())
    local = email.split("@", 1)[0].lower()
    if any(t in local for t in tokens if len(t) >= 3):
        return True
    for c in manifest.contacts:
        if c.email.lower() == email.lower():
            parts = set(norm_text(c.name).split()) | ({norm_text(c.org)} if c.org else set())
            return bool(tokens & parts) or n in norm_text(c.org or "")
    return n in email.lower()


def resolve_citation(cite: Citation, index: SourceIndex, manifest: Manifest) -> set[str]:
    kind, body = cite.kind, cite.body
    if kind in ("note",):
        sid = index.resolve("note:" + body.strip())
        return {sid} if sid else set()
    if kind in ("task", "tasks"):
        slug = re.sub(r"[^a-z0-9]+", "-", body.lower()).strip("-")
        sid = index.resolve("task:" + slug)
        return {sid} if sid else set()
    if kind not in ("email", "thread"):
        return set()
    name = body.split(",", 1)[0]
    tm = TIME_RE.search(body)
    wd = WEEKDAY_RE.search(body)
    md = MONTH_DAY_RE.search(body)
    iso = ISO_DATE_RE.search(body)
    hits: set[str] = set()
    for mid, label in index.msg_label.items():
        sid = index.by_msg[mid]
        if tm and label.time != f"{int(tm.group(1)):02d}:{tm.group(2)}":
            continue
        if not _name_matches(name, label.from_email, manifest, label.is_from_avery):
            continue
        d = manifest.meta.day_to_date(label.day)
        if wd and d.strftime("%a").lower() != wd.group(1)[:3].lower():
            continue
        if md and (MONTHS.index(md.group(1)[:3].lower()) + 1, int(md.group(2))) != (d.month, d.day):
            continue
        if iso and (int(iso.group(1)), int(iso.group(2)), int(iso.group(3))) != (d.year, d.month, d.day):
            continue
        hits.add(sid)
    return hits


# ----------------------------------------------------------------------------- actions
def parse_actions(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for raw in lines:
        line = raw.strip().lstrip("*_ ").strip()
        if line.lower().startswith("assumptions:") and out:
            out[-1]["assumptions"] = [a.strip() for a in line.split(":", 1)[1].split(";") if a.strip()]
            continue
        if line[:1] in ('"', "“") and out and out[-1]["type"] in ("reply", "forward_delegate", "decide") and not out[-1]["draft"]:
            out[-1]["draft"] = line.strip('"“” ')
            continue
        if line.startswith(">") and out:
            prev = out[-1]
            prev["draft"] = ((prev.get("draft") or "") + " " + line.lstrip("> ").strip()).strip()
            continue
        if re.match(r"^(Default if unanswered|→|\(\d\))", line) and out:
            out[-1]["text"] += " " + line
            continue
        for rx, typ in ACTION_TYPES:
            m = rx.match(line)
            if not m:
                continue
            act = {"type": typ, "text": line, "target": None, "recipient_name": None, "draft": None, "assumptions": []}
            if typ in ("reply", "forward_delegate"):
                act["recipient_name"] = act["target"] = m.group(1).strip()
                draft = m.group(2).strip().strip('"“”')
                act["draft"] = draft or None
            elif typ == "message_person":
                act["recipient_name"] = act["target"] = m.group(1).strip(" :,.")
            out.append(act)
            break
    return out


# ----------------------------------------------------------------------------- about inference
def day_keys(manifest: Manifest, day: int | None) -> list[str]:
    try:
        rd = manifest.run_day(day) if day is not None else None
    except KeyError:
        rd = None
    keys: list[str] = []
    if rd:
        keys += [ei.about for ei in rd.items] + list(rd.absent) + ([rd.one_thing.about] if rd.one_thing else [])
    for it in manifest.items:
        if it.expected:
            keys += it.expected.about
    return list(dict.fromkeys(keys))


def infer_about(text: str, source_ids: set[str], keys: list[str], manifest: Manifest) -> str | None:
    t = norm_text(text)
    labeled: set[str] = set()
    for sid in source_ids:
        exp = manifest.item(sid).expected
        if exp:
            labeled |= set(exp.about)
    scored = []
    for k in keys:
        toks = about_tokens(k)
        if not toks:
            continue
        s = sum(1 for tok in toks if re.search(rf"\b{re.escape(tok)}", t)) / len(toks)
        if k in labeled:
            s += 0.5
        scored.append((s, k))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 0.5:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0] and split_about(scored[1][1]) != split_about(scored[0][1]):
        return None
    return scored[0][1]


# ----------------------------------------------------------------------------- the view
def rendered_from_markdown(parsed: ParsedDigest, index: SourceIndex, manifest: Manifest, day: int | None) -> list[RenderedItem]:
    keys = day_keys(manifest, day)
    out: list[RenderedItem] = []
    pos = 0
    for sec in parsed.section_order:
        if sec in ("profile_updates",):
            continue
        for it in parsed.sections.get(sec, []):
            pos += 1
            out.append(_item(it, sec, pos, index, manifest, keys))
    return out


def _item(it: MdItem, sec: str, pos: int, index: SourceIndex, manifest: Manifest, keys: list[str]) -> RenderedItem:
    sources: set[str] = set()
    for c in it.citations:
        sources |= resolve_citation(c, index, manifest)
    placement = {"one_thing": "one_thing", "also_pending": "also_pending", "outside_filter": "also_pending"}.get(sec, "section")
    why = re.sub(r"^\*\*.+?\*\*\s*", "", it.text)
    return RenderedItem(
        id=f"md-L{it.line_no}", about=infer_about(it.full_text, sources, keys, manifest), placement=placement,
        section=None if placement != "section" else sec, priority=None, confidence=None, what=it.what, why=why,
        candidate_ids=[], candidate_types=[], citations=[c.raw for c in it.citations], source_ids=sources,
        actions=parse_actions(it.action_lines), position=pos, is_one_thing=(sec == "one_thing"),
    )
