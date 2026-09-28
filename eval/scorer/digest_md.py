"""Parser for the rendered digest (architecture §9): header, sections, items, citations, action blocks, question cards.

It reads only the markdown, so it scores the pipeline and the naive baseline the same way. Grammar assumed:

    # <title>                                   (optional)
    As of Thu 06:00 PT · inbox synced 05:58 ·…   (header block: every line before the first `## `)
    ## If there is one thing you must do right now
    **<what>.** <why>. *[email: Marcus, Tue 16:42]*
    ## Urgent To-Do Today
    - **<what>.** <why>. *[email: …] [note: …]*
      ↳ Draft to Marcus: > …                     (action lines, indented or not)
      Q1 · <question> (1) … (2) … Default if unanswered: 2 → digest answer Q1 2

Word count (hard rule 9): item and prose text in sections, excluding the header block, headings, action blocks,
citations and `---` rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CITATION_RE = re.compile(r"\[(email|note|cal|calendar|task|tasks|source|event|thread)\s*:\s*([^\]]*)\]", re.I)
QUESTION_RE = re.compile(r"\bQ(\d+)\s*[·:.\-]\s*(.*)")
OPTION_RE = re.compile(r"\((\d)\)\s*([^()]*?)(?=\s*\(\d\)|\s*Default if unanswered|\s*→|$)")
DEFAULT_RE = re.compile(r"Default if unanswered:\s*\**\s*(\d)", re.I)
ACTION_PREFIXES = ("↳", "☐", "☑", "Watching:", "Assumptions:", "Default if unanswered", "→", ">", "Options:",
                   "Recommend", "(1)", "(2)", "(3)", "Draft", "No draft")

SECTION_KEYS = [
    ("one thing", "one_thing"),
    ("urgent", "urgent"),
    ("decision", "decisions"),
    ("news", "news"),
    ("pulse", "pulse"),
    ("calendar", "calendar_personal"),
    ("also pending", "also_pending"),
    ("outside your filter", "outside_filter"),
    ("profile update", "profile_updates"),
]


def section_key(title: str) -> str:
    t = title.lower()
    for needle, key in SECTION_KEYS:
        if needle in t:
            return key
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_") or "unknown"


@dataclass
class Citation:
    kind: str
    body: str

    @property
    def raw(self) -> str:
        return f"[{self.kind}: {self.body}]"


@dataclass
class QuestionCard:
    number: int
    question: str
    options: list[str]
    default: int | None
    section: str
    item_text: str


@dataclass
class MdItem:
    section: str
    line_no: int
    text_lines: list[str] = field(default_factory=list)
    action_lines: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.text_lines)

    @property
    def full_text(self) -> str:
        return " ".join(self.text_lines + self.action_lines)

    @property
    def what(self) -> str:
        m = re.search(r"\*\*(.+?)\*\*", self.text)
        return m.group(1).strip() if m else self.text[:80]


@dataclass
class ParsedDigest:
    title: str | None
    header: str
    sections: dict[str, list[MdItem]]
    section_order: list[str]
    prose: dict[str, list[str]]
    questions: list[QuestionCard]
    word_count: int

    @property
    def items(self) -> list[MdItem]:
        return [i for s in self.section_order for i in self.sections.get(s, [])]

    def items_in(self, *sections: str) -> list[MdItem]:
        return [i for s in sections for i in self.sections.get(s, [])]


def _is_action(line: str) -> bool:
    s = line.strip().lstrip("*_ ").strip()
    return s.startswith(ACTION_PREFIXES) or bool(QUESTION_RE.match(s))


def _words(text: str) -> int:
    text = CITATION_RE.sub(" ", text)
    text = re.sub(r"[*_`#>]", " ", text)
    return len([w for w in text.split() if re.search(r"\w", w)])


def parse_digest(md: str) -> ParsedDigest:
    lines = md.splitlines()
    title: str | None = None
    header_lines: list[str] = []
    sections: dict[str, list[MdItem]] = {}
    prose: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    item: MdItem | None = None
    words = 0

    for n, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("# ") and title is None and current is None:
            title = stripped[2:].strip()
            continue
        if stripped.startswith("## "):
            current = section_key(stripped[3:])
            if current not in sections:
                sections[current] = []
                prose[current] = []
                order.append(current)
            item = None
            continue
        if current is None:
            if stripped:
                header_lines.append(stripped)
            continue
        if not stripped or set(stripped) <= {"-", "*", "_"}:
            if not stripped:
                continue
            item = None  # a `---` rule ends the item
            continue
        starts_item = (not raw.startswith((" ", "\t")) and re.match(r"^[-*]\s+", stripped) is not None) or (
            current == "one_thing" and item is None and stripped.startswith("**"))
        if starts_item:
            item = MdItem(section=current, line_no=n)
            sections[current].append(item)
            body = re.sub(r"^[-*]\s+", "", stripped) if not stripped.startswith("**") else stripped
            item.text_lines.append(body)
            words += _words(body)
        elif _is_action(stripped):
            if item is not None:
                item.action_lines.append(stripped)
            else:
                prose[current].append(stripped)
        elif item is not None:
            item.text_lines.append(stripped)
            words += _words(stripped)
        else:
            prose[current].append(stripped)
            words += _words(stripped)
        if item is not None:
            item.citations = [Citation(k.lower(), b.strip()) for k, b in CITATION_RE.findall(item.text)]

    questions: list[QuestionCard] = []
    for sec in order:
        for it in sections[sec]:
            blob = " ".join(it.action_lines)
            for m in QUESTION_RE.finditer(blob):
                tail = blob[m.start():]
                nxt = QUESTION_RE.search(tail, 2)
                card = tail[: nxt.start()] if nxt else tail
                q_text = re.split(r"\(\d\)|Default if unanswered|→", m.group(2))[0].strip()
                options = [o.strip(" ;,.") for _, o in OPTION_RE.findall(card)]
                dm = DEFAULT_RE.search(card)
                questions.append(QuestionCard(number=int(m.group(1)), question=q_text, options=options,
                                              default=int(dm.group(1)) if dm else None, section=sec,
                                              item_text=it.text))
    return ParsedDigest(title=title, header=" ".join(header_lines), sections=sections, section_order=order,
                        prose=prose, questions=questions, word_count=words)
