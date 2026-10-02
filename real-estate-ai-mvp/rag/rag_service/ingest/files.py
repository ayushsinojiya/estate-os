"""What an upload is, and how its bytes become pages of Markdown without a model.

Spreadsheets, Word documents, slides and plain text are parsed deterministically here. PDFs and
images go to the vision parser (see parse.py); only their page images are produced here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import PurePath

KINDS = {
    ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx", ".xls": "xls", ".csv": "csv",
    ".txt": "text", ".md": "text", ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image",
}
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel", "csv": "text/csv", "text": "text/plain", "image": "image/*",
}


class UnsupportedFile(ValueError):
    pass


@dataclass
class Detected:
    kind: str
    mime: str
    extension: str


def safe_name(name: str | None) -> str:
    base = PurePath((name or "").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f]", "", base).strip()
    return base[-255:] or "upload"


def detect(file_name: str, data: bytes) -> Detected:
    """Trust the bytes over the declared name where the format has a signature."""
    ext = PurePath(file_name.lower()).suffix
    kind = KINDS.get(ext)
    if kind is None:
        raise UnsupportedFile(f"unsupported file type {ext or '(none)'}")
    if not data:
        raise UnsupportedFile("the file is empty")
    head = data[:8]
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise UnsupportedFile("not a PDF")
    if kind in ("docx", "pptx", "xlsx") and not head.startswith(b"PK"):
        raise UnsupportedFile(f"not a valid {ext} file")
    if kind == "xls" and not head.startswith(b"\xd0\xcf\x11\xe0"):
        raise UnsupportedFile("not a valid .xls file")
    if kind == "image":
        if head.startswith(b"\x89PNG"):
            return Detected(kind, "image/png", ext)
        if head.startswith(b"\xff\xd8"):
            return Detected(kind, "image/jpeg", ext)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return Detected(kind, "image/webp", ext)
        raise UnsupportedFile("not a PNG, JPEG or WEBP image")
    if kind in ("csv", "text"):
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedFile("text files must be UTF-8") from exc
    return Detected(kind, MIME[kind] if kind != "image" else "image/png", ext)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- tables


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    return re.sub(r"\s+", " ", text).replace("|", "\\|")


def markdown_table(header: list[str], rows: list[list[str]]) -> str:
    width = len(header)
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    for row in rows:
        cells = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _table_from_grid(grid: list[list[str]]) -> tuple[list[str], list[list[str]]] | None:
    grid = [row for row in grid if any(c for c in row)]
    if not grid:
        return None
    width = max(len(r) for r in grid)
    grid = [(r + [""] * width)[:width] for r in grid]
    # Drop columns that are empty everywhere.
    keep = [i for i in range(width) if any(r[i] for r in grid)]
    grid = [[r[i] for i in keep] for r in grid]
    header = [h or f"Column {i + 1}" for i, h in enumerate(grid[0])]
    return header, grid[1:]


def sheets_from_workbook(kind: str, data: bytes) -> list[tuple[str, list[str], list[list[str]]]]:
    """(sheet name, header, rows) for every non-empty sheet. Values are read, never formulas."""
    import pandas as pd

    if kind == "csv":
        text = data.decode("utf-8-sig")
        grid = [[_cell(c) for c in row] for row in csv.reader(io.StringIO(text))]
        table = _table_from_grid(grid)
        return [("Sheet1", *table)] if table else []
    engine = "openpyxl" if kind == "xlsx" else "xlrd"
    frames = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, engine=engine, dtype=object)
    out = []
    for name, frame in frames.items():
        grid = [[_cell(v) for v in row] for row in frame.itertuples(index=False, name=None)]
        table = _table_from_grid(grid)
        if table:
            out.append((str(name), *table))
    return out


def workbook_pages(kind: str, data: bytes) -> list[str]:
    """One Markdown page per sheet: a heading with the sheet name, then the sheet as a table."""
    return [f"## {name}\n\n{markdown_table(header, rows)}"
            for name, header, rows in sheets_from_workbook(kind, data)]


# ---------------------------------------------------------------- documents


def docx_pages(data: bytes) -> list[str]:
    """Word documents have no fixed pages; the whole document is one Markdown page."""
    import docx
    from docx.document import Document as _Doc  # noqa: F401
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    parts: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "").lower()
            if style.startswith("heading"):
                level = re.sub(r"\D", "", style) or "2"
                parts.append("#" * min(int(level), 4) + " " + text)
            elif style.startswith("title"):
                parts.append("# " + text)
            elif "list" in style:
                parts.append("- " + text)
            else:
                parts.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            grid = [[_cell(cell.text) for cell in row.cells] for row in table.rows]
            parsed = _table_from_grid(grid)
            if parsed:
                parts.append(markdown_table(*parsed))
    return ["\n\n".join(parts)] if parts else []


def pptx_pages(data: bytes) -> list[str]:
    """One page per slide: the title as a heading, text frames as paragraphs or bullets, tables."""
    from pptx import Presentation

    deck = Presentation(io.BytesIO(data))
    pages: list[str] = []
    for slide in deck.slides:
        parts: list[str] = []
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else ""
        if title:
            parts.append("## " + title)
        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if shape.has_table:
                grid = [[_cell(cell.text) for cell in row.cells] for row in shape.table.rows]
                parsed = _table_from_grid(grid)
                if parsed:
                    parts.append(markdown_table(*parsed))
            elif shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip()
                    if text:
                        parts.append(("- " if para.level > 0 or len(shape.text_frame.paragraphs) > 1 else "") + text)
        pages.append("\n\n".join(parts))
    return pages


def text_pages(data: bytes) -> list[str]:
    return [data.decode("utf-8-sig")]
