"""Reconcile safety nets with reader/sweep findings, and group findings by topic (specs/PIVOT_SPEC.md §5.3–§5.4).

No string similarity anywhere (MIGRATION_PLAN.md §2): code narrows the options with hard facts (a shared citation, the
same thread, a shared person or org, the reader's own summary of the net's thread), and the linker (Jev first, the LLM
when Jev is unsure) decides sameness. Without
a linker nothing matches: every net stays a rescue and no topics merge, so a missed link shows up in the digest
instead of hiding something.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable

from ..findings import about_key
from ..schemas import AboutMerge, Finding
from .linker import LinkOption, LinkQuestion

Log = Callable[[str, dict], None] | None
PASS_THROUGH = ("stale_source",)     # a freshness fact no reader can cover; never counted as a rescue
THREAD_NETS = ("quiet_thread", "reply_owed")   # one unanswered message in one thread
_NEEDS = {"yes": 0, "unsure": 1, "no": 2}


def thread_of(f: Finding, msg_thread: dict[str, str]) -> str | None:
    """The thread a finding is about: the thread of its first message citation."""
    return next((msg_thread[e.source_id] for e in f.citations if e.source_id in msg_thread), None)


def _threads(f: Finding, msg_thread: dict[str, str]) -> set[str]:
    return {msg_thread[e.source_id] for e in f.citations if e.source_id in msg_thread}


def _options(net: Finding, pool: list[Finding], msg_thread: dict[str, str], ignore: set[str]) -> list[tuple[Finding, str]]:
    """(finding, the hard fact that makes it an option), strongest first: it cites the same message or event, or a
    message of the same thread; only when there are none, it shares a person or org."""
    cites = {e.source_id for e in net.citations}
    threads = _threads(net, msg_thread)
    close = []
    for f in pool:
        shared = cites & {e.source_id for e in f.citations}
        if shared:
            close.append((f, "same event" if all(x.startswith("event:") for x in shared) else "same message"))
        elif threads & _threads(f, msg_thread):
            close.append((f, "same thread"))
    if close:
        return close
    ents = set(net.entities) - ignore
    return [(f, "same person") for f in pool if ents & (set(f.entities) - ignore)]


def _covered_by_report(net: Finding, findings: list[Finding]) -> Finding | None:
    """A suspicious-content net built from a reader's own suspicious_instructions is that reader finding's flag."""
    if net.kind != "suspicious_content":
        return None
    for f in findings:
        if f.suspicious_instructions and all(e in f.suspicious_instructions for e in net.citations):
            return f
    return None


def _attach(f: Finding, net: Finding) -> Finding:
    cits = list(f.citations) + [e for e in net.citations if e not in f.citations]
    return f.model_copy(update={"why": f"{f.why.rstrip()} (computed: {net.why.rstrip()})", "citations": cits[:8],
                                "freshness_caveat": f.freshness_caveat or net.freshness_caveat})


def reconcile(findings: list[Finding], nets: list[Finding], linker, *, msg_thread: dict[str, str] | None = None,
              summaries: dict[str, str] | None = None, ignore_entities: Iterable[str] = (),
              log: Log = None) -> tuple[list[Finding], list[dict]]:
    """→ (reader/sweep findings with covered nets' facts attached, plus every uncovered net), rescue log.

    A waiting-on-Avery net (one unanswered message) is covered outright by a finding that cites that same message.
    Otherwise code offers the options (hard facts, strongest first): the findings that cite the same message, event or
    thread; else the findings that share a person or org. When a waiting-on-Avery net's thread was read and the reader
    raised nothing on it, the reader's own summary of that thread is the option ("read:<thread id>"); aggregate nets
    (a recruiter pattern across threads) never get one. The linker picks the option that is the
    same issue, or none. A picked finding gets the net's computed fact appended to its `why` (the net is dropped); a
    picked reader summary means the reader judged the thread and it needs nothing (the net is dropped, logged); no pick
    keeps the net, and the rescue log names it ({net, finding_id, title, why, options}): the caller marks those
    `rescued_by_safety_net`. `msg_thread` (msg:<id> → thread id) and `summaries` (thread id → the reader's summary,
    digest.read.ReadResult.summaries) make those two tests possible; without them only shared citations and entities
    narrow. `ignore_entities` removes entities every finding shares (Avery's own company). Finding ids must be unique."""
    msg_thread = msg_thread or {}
    summaries = summaries or {}
    ignore = set(ignore_entities)
    out = list(findings)
    idx = {f.finding_id: i for i, f in enumerate(out)}
    pool = [f for f in out if f.origin != "safety_net"]
    rescues: list[dict] = []
    kept: list[Finding] = []
    questions: list[LinkQuestion] = []
    asked: dict[str, Finding] = {}
    for net in nets:
        if net.kind in PASS_THROUGH:
            kept.append(net)
            continue
        owner = _covered_by_report(net, out)
        if owner is not None:
            if log:
                log("net_covered", {"net": net.kind, "net_id": net.finding_id, "finding": owner.finding_id, "by": "reported_quote"})
            continue
        opts = _options(net, pool, msg_thread, ignore)
        same = [f for f, label in opts if label == "same message"]
        if net.kind in THREAD_NETS and same:
            # identity, not similarity: the reader turned this very message into an issue (spec §5.3 "overlapping
            # citations"); the fact goes to the most pressing of the findings that cite it
            f = min(same, key=lambda x: (_NEEDS[x.needs_avery], x.priority))
            if log:
                log("net_covered", {"net": net.kind, "net_id": net.finding_id, "finding": f.finding_id, "by": "same_message",
                                    "finding_needs_avery": f.needs_avery})
            out[idx[f.finding_id]] = _attach(out[idx[f.finding_id]], net)
            continue
        options = [LinkOption(id=f.finding_id, text=f"[{label}] {f.kind}: {f.title}. {f.why}") for f, label in opts]
        read = sorted(t for t in _threads(net, msg_thread) if t in summaries)
        if net.kind in THREAD_NETS and len(read) == 1 and not any(_threads(net, msg_thread) & _threads(f, msg_thread) for f in pool):
            options = [LinkOption(id=f"read:{t}", text=f"[same thread] the reader read this whole thread and raised nothing for Avery; its summary: "
                                                      f"{summaries[t]}") for t in read]
        if not options:
            rescues.append({"net": net.kind, "finding_id": net.finding_id, "title": net.title, "why": net.why, "options": 0})
            kept.append(net)
            continue
        qid = f"n{len(questions)}"
        asked[qid] = net
        questions.append(LinkQuestion(id=qid, item=f"{net.kind}: {net.title}. {net.why}", options=options))
    answers = linker.match("net_covers_finding", questions) if (linker is not None and questions) else {}
    for q in questions:
        net = asked[q.id]
        picks = [p for p in answers.get(q.id, []) if p in idx or p.startswith("read:")]
        if picks and picks[0].startswith("read:"):
            if log:
                log("net_covered", {"net": net.kind, "net_id": net.finding_id, "thread": picks[0][5:], "by": "reader_summary"})
        elif picks:
            i = idx[picks[0]]
            if log:
                log("net_covered", {"net": net.kind, "net_id": net.finding_id, "finding": picks[0], "by": "linker",
                                    "finding_needs_avery": out[i].needs_avery})
            out[i] = _attach(out[i], net)
        else:
            rescues.append({"net": net.kind, "finding_id": net.finding_id, "title": net.title, "why": net.why,
                            "options": len(q.options)})
            kept.append(net)
    return out + kept, rescues


# ----------------------------------------------------------------------------- topic groups
def _key(f: Finding) -> str:
    return about_key(f.about[0] if f.about else "", f.title)


def group_findings(findings: list[Finding], linker) -> list[AboutMerge]:
    """Topic keys (each surfacing finding's first `about` tag, normalized as to_candidate does) that the linker judges
    to name the same thing; only same-kind keys group (Linker.group_topics). Canonical = the key most findings use,
    then the shorter one."""
    uses: Counter[str] = Counter()
    texts: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        if f.needs_avery == "no":
            continue
        k = _key(f)
        uses[k] += 1
        if f.title not in texts[k]:
            texts[k].append(f.title)
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for k in sorted(uses):
        by_kind[k.split(":", 1)[0]].append({"key": k, "text": "; ".join(texts[k][:3])})
    groups = linker.group_topics(dict(by_kind)) if linker is not None else []
    parent = {k: k for k in uses}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for g in groups:
        members = [m for m in g if m in parent]
        for m in members[1:]:
            ra, rb = find(members[0]), find(m)
            if ra != rb:
                parent[rb] = ra
    clusters: dict[str, list[str]] = defaultdict(list)
    for k in uses:
        clusters[find(k)].append(k)
    merges: list[AboutMerge] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        canonical = max(members, key=lambda k: (uses[k], -len(k), k))
        merges.append(AboutMerge(canonical=canonical, merged=sorted(m for m in members if m != canonical), reason="linker"))
    return sorted(merges, key=lambda m: m.canonical)


def apply_merges(findings: list[Finding], merges: list[AboutMerge]) -> list[Finding]:
    """Rewrite each finding's first about tag to its group's canonical key, so to_candidate gives merged findings one
    about key and reduce joins them."""
    mapping = {m: g.canonical for g in merges for m in g.merged}
    out = []
    for f in findings:
        k = _key(f)
        if k in mapping:
            f = f.model_copy(update={"about": [mapping[k], *f.about[1:]]})
        out.append(f)
    return out


__all__ = ["PASS_THROUGH", "apply_merges", "group_findings", "reconcile", "thread_of"]
