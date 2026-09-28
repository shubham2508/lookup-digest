"""Shared helpers for the Track C tests (not collected: no test_ prefix)."""
from __future__ import annotations

from pathlib import Path

from eval.manifest_schema import Manifest, MessageLabel, load_manifest

ROOT = Path(__file__).resolve().parents[1]
MINI_MANIFEST = ROOT / "tests" / "fixtures" / "mini" / "manifest.yaml"
MINI_RUNS = ROOT / "tests" / "fixtures" / "mini_runs"
DAY = 30

# The fixture manifest labels messages only for the Halberd and Marcus threads. The scorer maps product evidence
# (msg:<Message-ID>) to manifest items through those labels, so the other items get theirs here, taken from the
# fixture's .eml headers. Real manifests must carry them for every item (OPEN_QUESTIONS.md #6).
_EXTRA_MESSAGES = {
    "nl-scbrief-212": ("<20260923-0700.brief@scbrief.example>", 29, "07:00", "brief@scbrief.example"),
    "auto-docusign-mei": ("<20260922-0915.dse@docusign.net>", 28, "09:15", "dse@docusign.net"),
    "mkt-rippleboard": ("<20260921-1000.hello@mail.rippleboard.example>", 27, "10:00", "hello@mail.rippleboard.example"),
    "t-sam-daycare": ("<20260923-2110.sam@parkfamily.example>", 29, "21:10", "sam@parkfamily.example"),
}


def mini_manifest() -> Manifest:
    m = load_manifest(MINI_MANIFEST)
    for item in m.items:
        if not item.messages and item.source_id in _EXTRA_MESSAGES:
            mid, day, t, frm = _EXTRA_MESSAGES[item.source_id]
            item.messages.append(MessageLabel(message_id=mid, day=day, time=t, from_email=frm, to=["avery@tessera.io"]))
    return m


# ----------------------------------------------------------------------------- synthetic runs for checker tests
def make_run(root: Path, manifest: Manifest, day: int, items: list[dict], *, header: str = "As of Thu 06:00 PT · inbox ok",
             suffix: str | None = None, extra_candidates: list[dict] | None = None, header_notes: list[str] | None = None,
             contacts: list[dict] | None = None, extractions: list[dict] | None = None) -> Path:
    """Write a minimal but contract-shaped run dir. Each item dict:
    {id, about, ctype, priority, section, placement: one_thing|section|also_pending, cites: [evidence refs],
     actions: [{type, target, draft?, text?, recipient_name?, recipient_category?}], what, why, confidence,
     times_surfaced, include (default True)}"""
    import json

    from digest.runs import run_dir_name
    from eval.scorer.runner import as_of_for

    d = root / run_dir_name(as_of_for(manifest, day), suffix)
    d.mkdir(parents=True, exist_ok=True)
    cands, tri, red, comp, acts = [], [], [], [], []
    sections: dict[str, list[str]] = {}
    one = None
    overflow = []
    md_sections: dict[str, list[str]] = {}
    for it in items:
        cid = f"c-{it['id']}"
        evid = [{"source_id": s, "quote": "q"} for s in it.get("cites", [])]
        cands.append({"candidate_id": cid, "type": it.get("ctype", "reply_owed"), "about": it["about"],
                      "entities": it.get("entities", []), "facts": it.get("facts", {}), "evidence": evid,
                      "context_refs": [], "source_dependencies": ["email"], "freshness_cap": "none",
                      "times_surfaced": it.get("times_surfaced", 0)})
        pa = [{"type": a["type"], "target": a.get("target"), "brief": "b", "assumptions": [], "watch_trigger": None,
               "read_start": None} for a in it.get("actions", [])]
        tri.append({"candidate_id": cid, "include": it.get("include", True), "section": it.get("section", "urgent"),
                    "priority": it.get("priority", "P1"), "due_today": True, "confidence": it.get("confidence", "high"),
                    "why": "w", "citations": evid, "ambiguity": None, "proposed_actions": pa})
        if not it.get("include", True):
            continue
        red.append({"id": it["id"], "about": it["about"], "candidate_ids": [cid], "priority": it.get("priority", "P1"),
                    "section": it.get("section", "urgent"), "confidence": it.get("confidence", "high"),
                    "citations": evid, "proposed_actions": pa, "entities": it.get("entities", [])})
        comp.append({"id": it["id"], "what": it.get("what", f"Handle {it['about']}"), "why": it.get("why", "because"),
                     "final_actions": pa})
        for a in it.get("actions", []):
            acts.append({"item_id": it["id"], "type": a["type"], "target": a.get("target"),
                         "recipient_name": a.get("recipient_name"), "recipient_category": a.get("recipient_category"),
                         "brief": "b", "brief_assumptions": [], "text": a.get("text", f"↳ {a['type']}"),
                         "draft": a.get("draft"), "assumptions": [], "evidence": evid})
        placement = it.get("placement", "section")
        cite_md = " ".join(f"[email: x, {i}]" for i, _ in enumerate(it.get("cites", []))) if it.get("cites") else ""
        line = f"- **{it.get('what', 'Handle ' + it['about'])}.** {it.get('why', 'because')}. *{cite_md}*" if cite_md else \
               f"- **{it.get('what', 'Handle ' + it['about'])}.** {it.get('why', 'because')}."
        action_lines = [f"  {a.get('text', '↳ ' + a['type'])}" for a in it.get("actions", [])]
        if placement == "one_thing":
            one = it["id"]
            md_sections.setdefault("If there is one thing you must do right now", []).extend([line[2:], *action_lines])
        elif placement == "also_pending":
            overflow.append(it["id"])
            md_sections.setdefault("Also pending", []).append(f"- {it.get('what', it['about'])}")
        else:
            sections.setdefault(it.get("section", "urgent"), []).append(it["id"])
            title = {"urgent": "Urgent To-Do Today", "decisions": "Decisions & Approvals", "news": "AI Industry News",
                     "pulse": "Team & Product Pulse", "calendar_personal": "Calendar & Personal"}[it.get("section", "urgent")]
            md_sections.setdefault(title, []).extend([line, *action_lines])
    for c in extra_candidates or []:
        cands.append({"candidate_id": c.get("candidate_id", f"x-{len(cands)}"), "type": c["type"], "about": c["about"],
                      "entities": [], "facts": c.get("facts", {}), "evidence": c.get("evidence", []), "context_refs": [],
                      "source_dependencies": ["email"], "freshness_cap": "none", "times_surfaced": 0})

    def jl(name: str, rows: list[dict]) -> None:
        (d / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    jl("candidates.jsonl", cands)
    jl("triage.jsonl", tri)
    jl("actions.jsonl", acts)
    jl("extractions.jsonl", extractions or [])
    jl("degradations.jsonl", [])
    (d / "contacts.json").write_text(json.dumps(contacts or []), encoding="utf-8")
    (d / "reduce.json").write_text(json.dumps({"items": red, "overflow": overflow}), encoding="utf-8")
    (d / "compose.json").write_text(json.dumps({
        "one_thing_id": one, "sections": [{"name": k, "item_ids": v} for k, v in sections.items()], "items": comp,
        "header_notes": header_notes or [], "cut_ids": []}), encoding="utf-8")
    (d / "verify.json").write_text(json.dumps({"violations": [], "stats": {}}), encoding="utf-8")
    (d / "cost.json").write_text(json.dumps({"cost_usd": 0.01}), encoding="utf-8")
    md = ["# Daily Digest", "", header, ""]
    for title, lines in md_sections.items():
        md += [f"## {title}", "", *lines, ""]
    (d / "digest.md").write_text("\n".join(md), encoding="utf-8")
    return d
