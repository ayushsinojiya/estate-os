"""Structure-aware chunking of parsed Markdown.

Chunks follow the document's own structure rather than a fixed size:

- Sections split on headings. Small neighbouring sections are packed together (aiming for
  roughly 250–450 tokens) and keep their sub-headings in the text; a long section is split, with
  about 15% overlap, only inside itself.
- A table is never cut through a row and never appears without its header. A table that fits the
  table budget is one TABLE chunk; a longer one becomes several TABLE chunks, each repeating the
  header. Tables with more than a few rows also get one TABLE_ROW chunk per row, written as
  "Header: value; Header: value", so a question about one charge retrieves just that row.
- Each FAQ question and its answer is exactly one chunk.
- Every chunk carries a context header ("Project: … · Brochure · Section: … · Page 4") that is
  embedded together with the content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag_service.tokens import count_tokens

DOC_TYPE_LABEL = {
    "BROCHURE": "Brochure", "PRICE_SHEET": "Price sheet", "PAYMENT_PLAN": "Payment plan", "FAQ": "FAQ",
    "RERA": "RERA", "LEGAL": "Legal", "FLOOR_PLAN": "Floor plan", "OTHER": "Document",
}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^(?:\*\*|__)(.{2,80}?)(?:\*\*|__):?\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•▪◦]|\d{1,2}[.)])\s+")
_QUESTION_PREFIX = re.compile(
    r"^\s*(?:\*\*)?\s*(?:q(?:uestion)?\s*\d*\s*[:.)-]|प्रश्न\s*\d*\s*[:.)-]?|પ્રશ્ન\s*\d*\s*[:.)-]?)", re.I)
_ANSWER_PREFIX = re.compile(r"^\s*(?:\*\*)?\s*(?:a(?:ns(?:wer)?)?\s*\d*\s*[:.)-]|उत्तर\s*[:.)-]?|જવાબ\s*[:.)-]?)\s*(?:\*\*)?\s*", re.I)
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")


@dataclass
class ChunkDraft:
    chunk_type: str
    content: str
    context_header: str
    section_path: str
    page_from: int | None
    page_to: int | None
    language: str
    token_count: int
    ordinal: int = 0

    @property
    def embedding_text(self) -> str:
        return f"{self.context_header}\n\n{self.content}"


@dataclass
class DocContext:
    doc_type: str = "OTHER"
    project_name: str | None = None
    locality: str | None = None
    paged: bool = True  # spreadsheets and Word files have no meaningful page numbers


@dataclass
class ChunkConfig:
    target_tokens: int = 350
    max_tokens: int = 450
    min_tokens: int = 250
    overlap_ratio: float = 0.15
    table_max_tokens: int = 800
    table_row_min_rows: int = 6


# ---------------------------------------------------------------- language


_MR_MARKERS = ("आहे", "आहेत", "नाही", "च्या", "साठी", "मध्ये", "ळ", "आणि")
_HI_MARKERS = ("है", "हैं", "नहीं", " के ", " में ", " की ", " और ")


def detect_language(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    dev = sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)
    guj = sum(1 for c in letters if "઀" <= c <= "૿") / len(letters)
    if guj >= 0.3 and guj >= dev:
        return "gu"
    if dev >= 0.3:
        mr = sum(text.count(m) for m in _MR_MARKERS)
        hi = sum(text.count(m) for m in _HI_MARKERS)
        return "mr" if mr > hi else "hi"
    return "en"


# ---------------------------------------------------------------- blocks


@dataclass
class Block:
    kind: str  # heading | text | table | question
    text: str
    page: int | None
    level: int = 0
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def split_cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.strip() for c in cells]


def _is_question(text: str) -> bool:
    first = text.strip().splitlines()[0] if text.strip() else ""
    if _QUESTION_PREFIX.match(first):
        return True
    plain = first.strip().strip("*_").strip()
    return plain.endswith(("?", "？")) and len(plain) <= 200


def parse_blocks(pages: list[tuple[int | None, str]]) -> list[Block]:
    blocks: list[Block] = []
    for page, markdown in pages:
        lines = markdown.replace("\r\n", "\n").split("\n")
        i, para = 0, []

        def flush_para() -> None:
            if para:
                text = "\n".join(para).strip()
                if text:
                    blocks.append(Block("question" if _is_question(text) else "text", text, page))
                para.clear()

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                flush_para()
                i += 1
                continue
            heading = _HEADING.match(stripped)
            bold = _BOLD_LINE.match(stripped) if not para else None
            if heading or (bold and not bold.group(1).rstrip().endswith("?")):
                flush_para()
                text = (heading.group(2) if heading else bold.group(1)).strip().strip("*_ ").strip()
                if text.endswith(("?", "？")):
                    blocks.append(Block("question", text, page))
                else:
                    blocks.append(Block("heading", text, page, level=len(heading.group(1)) if heading else 3))
                i += 1
                continue
            if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
                flush_para()
                header = split_cells(stripped)
                j = i + 2
                rows = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    cells = split_cells(lines[j])
                    if any(cells):
                        rows.append((cells + [""] * len(header))[:len(header)])
                    j += 1
                blocks.append(Block("table", "", page, header=header, rows=rows))
                i = j
                continue
            if _LIST_ITEM.match(line) and para and not _LIST_ITEM.match(para[-1]) and not _is_question("\n".join(para)):
                flush_para()
            para.append(line.rstrip())
            i += 1
        flush_para()
    return blocks


@dataclass
class Section:
    path: list[str]
    blocks: list[Block]


def group_sections(blocks: list[Block]) -> list[Section]:
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    current = Section([], [])
    for block in blocks:
        if block.kind == "heading":
            if current.blocks:
                sections.append(current)
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.text))
            current = Section([name for _, name in stack], [])
            continue
        current.blocks.append(block)
    if current.blocks:
        sections.append(current)
    return sections


# ---------------------------------------------------------------- packing


def _row_text(header: list[str], row: list[str]) -> str:
    pairs = [f"{h}: {v}" for h, v in zip(header, row) if v]
    return "; ".join(pairs)


def _table_markdown(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    for paragraph in text.split("\n"):
        parts += [s for s in _SENTENCE.split(paragraph) if s.strip()]
    return parts or [text]


def _common_prefix(paths: list[list[str]]) -> list[str]:
    if not paths:
        return []
    prefix = paths[0]
    for path in paths[1:]:
        n = 0
        while n < min(len(prefix), len(path)) and prefix[n] == path[n]:
            n += 1
        prefix = prefix[:n]
    return prefix


class Chunker:
    def __init__(self, ctx: DocContext, cfg: ChunkConfig):
        self.ctx = ctx
        self.cfg = cfg
        self.out: list[ChunkDraft] = []
        self._buf: list[tuple[str, int | None]] = []
        self._buf_paths: list[list[str]] = []
        self._buf_tokens = 0

    # -- headers

    def header(self, path: list[str], page_from: int | None, page_to: int | None) -> str:
        if self.ctx.project_name:
            where = f" ({self.ctx.locality})" if self.ctx.locality else ""
            parts = [f"Project: {self.ctx.project_name}{where}"]
        else:
            parts = ["Workspace knowledge"]
        parts.append(DOC_TYPE_LABEL.get(self.ctx.doc_type, "Document"))
        if path:
            parts.append("Section: " + " > ".join(path))
        if self.ctx.paged and page_from:
            parts.append(f"Page {page_from}" if page_to in (None, page_from) else f"Pages {page_from}–{page_to}")
        return " · ".join(parts)

    def emit(self, chunk_type: str, content: str, path: list[str], pages: list[int | None]) -> None:
        content = content.strip()
        if not content:
            return
        known = [p for p in pages if p is not None]
        page_from, page_to = (min(known), max(known)) if known else (None, None)
        self.out.append(ChunkDraft(chunk_type, content, self.header(path, page_from, page_to),
                                   " > ".join(path), page_from, page_to, detect_language(content),
                                   count_tokens(content), len(self.out)))

    # -- text buffer

    def _buffer_path(self) -> list[str]:
        distinct = []
        for p in self._buf_paths:
            if p not in distinct:
                distinct.append(p)
        if len(distinct) == 1:
            return distinct[0]
        prefix = _common_prefix(distinct)
        return prefix if prefix else distinct[0][:1]

    def flush(self, overlap_into: list[str] | None = None) -> None:
        """Emit the buffer. With overlap_into, the next buffer starts with the tail of this one."""
        if not self._buf:
            return
        text = "\n\n".join(t for t, _ in self._buf)
        pages = [p for _, p in self._buf]
        self.emit("TEXT", text, self._buffer_path(), pages)
        tail: list[tuple[str, int | None]] = []
        if overlap_into is not None:
            budget = max(1, int(self.cfg.target_tokens * self.cfg.overlap_ratio))
            taken: list[str] = []
            for sentence in reversed(_sentences(text)):
                if count_tokens(" ".join([sentence] + taken)) > budget:
                    break
                taken.insert(0, sentence)
            if taken:
                tail = [(" ".join(taken), pages[-1])]
        self._buf = tail
        self._buf_paths = [overlap_into] if tail and overlap_into is not None else []
        self._buf_tokens = sum(count_tokens(t) for t, _ in tail)

    def add_text(self, text: str, page: int | None, path: list[str]) -> None:
        tokens = count_tokens(text)
        if tokens > self.cfg.max_tokens:
            # A single oversized paragraph: split it by sentences, overlapping within the section.
            window: list[str] = []
            for sentence in _sentences(text):
                candidate = " ".join(window + [sentence])
                if window and count_tokens(candidate) > self.cfg.target_tokens:
                    self.add_text(" ".join(window), page, path)
                    window = []
                window.append(sentence)
            if window:
                self.add_text(" ".join(window), page, path)
            return
        if self._buf and self._buf_tokens + tokens > self.cfg.max_tokens:
            within_one_section = all(p == path for p in self._buf_paths)
            self.flush(overlap_into=path if within_one_section else None)
        self._buf.append((text, page))
        self._buf_paths.append(path)
        self._buf_tokens += tokens

    # -- special chunks

    def add_table(self, block: Block, path: list[str]) -> None:
        self.flush()
        header, rows = block.header, block.rows
        if not rows:
            return
        whole = _table_markdown(header, rows)
        if count_tokens(whole) <= self.cfg.table_max_tokens:
            self.emit("TABLE", whole, path, [block.page])
        else:
            group: list[list[str]] = []
            for row in rows:
                if group and count_tokens(_table_markdown(header, group + [row])) > self.cfg.table_max_tokens:
                    self.emit("TABLE", _table_markdown(header, group), path, [block.page])
                    group = []
                group.append(row)
            if group:
                self.emit("TABLE", _table_markdown(header, group), path, [block.page])
        if len(rows) > self.cfg.table_row_min_rows:
            for row in rows:
                line = _row_text(header, row)
                if line:
                    self.emit("TABLE_ROW", line, path, [block.page])

    def add_faq(self, question: str, answer: list[Block], path: list[str]) -> None:
        self.flush()
        q = _QUESTION_PREFIX.sub("", question.strip().strip("*_ ")).strip().strip("*_ ").strip()
        parts = []
        for block in answer:
            if block.kind == "table":
                parts.append(_table_markdown(block.header, block.rows))
            else:
                parts.append(_ANSWER_PREFIX.sub("", block.text, count=1).strip())
        body = "\n".join(p for p in parts if p)
        pages = [b.page for b in answer] or [None]
        self.emit("FAQ", f"Q: {q}\nA: {body}" if body else f"Q: {q}", path, pages)

    # -- driver

    def run(self, sections: list[Section]) -> list[ChunkDraft]:
        for section in sections:
            path = section.path
            heading_line = ("#" * min(len(path) + 1, 4) + " " + path[-1]) if path else ""
            first_text = True
            blocks = section.blocks
            i = 0
            while i < len(blocks):
                block = blocks[i]
                if block.kind == "question" or (self.ctx.doc_type == "FAQ" and _is_question(block.text)):
                    question_lines = block.text.split("\n")
                    answer: list[Block] = []
                    if len(question_lines) > 1 and block.kind != "question":
                        answer.append(Block("text", "\n".join(question_lines[1:]), block.page))
                    elif len(question_lines) > 1:
                        answer.append(Block("text", "\n".join(question_lines[1:]), block.page))
                    j = i + 1
                    while j < len(blocks) and blocks[j].kind in ("text", "table") and not (
                            blocks[j].kind == "text" and _is_question(blocks[j].text)):
                        answer.append(blocks[j])
                        j += 1
                    self.add_faq(question_lines[0], answer, path)
                    i = j
                    continue
                if block.kind == "table":
                    self.add_table(block, path)
                else:
                    text = block.text
                    if first_text and heading_line and len(path) > 0:
                        text = f"{heading_line}\n{text}"
                    first_text = False
                    self.add_text(text, block.page, path)
                i += 1
            # A section big enough to stand alone is emitted on its own; a small one waits to be
            # packed with its neighbours.
            if self._buf_tokens >= self.cfg.min_tokens:
                self.flush()
        self.flush()
        for n, chunk in enumerate(self.out):
            chunk.ordinal = n
        return self.out


def chunk_document(pages: list[tuple[int | None, str]], ctx: DocContext,
                   cfg: ChunkConfig | None = None) -> list[ChunkDraft]:
    blocks = parse_blocks(pages)
    return Chunker(ctx, cfg or ChunkConfig()).run(group_sections(blocks))
