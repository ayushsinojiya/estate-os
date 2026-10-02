"""Bytes → pages of Markdown.

PDFs and images are rendered to page images and transcribed by a vision model, a few pages at a
time. Spreadsheets, Word documents, slides and text are parsed deterministically and never sent
to a model. When vision parsing of a page fails after its retries, the PDF's own text layer is
used instead and the page is marked low-confidence, so one bad page never fails a whole brochure.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from rag_service.ingest import files, render
from rag_service.providers.llm import PageParse, PageParser

log = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    page_no: int
    markdown: str
    provider: str
    confidence: float
    image_sha256: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


async def _vision_pages(images: list[tuple[int, bytes, str | None]], parser: PageParser | None,
                        concurrency: int) -> list[ParsedPage]:
    """images: (page_no, png, text_layer_fallback)."""
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(page_no: int, png: bytes, fallback: str | None) -> ParsedPage:
        digest = render.image_hash(png)
        if parser is None:
            return _fallback(page_no, fallback, digest, "no vision parser configured")
        async with semaphore:
            try:
                result: PageParse = await parser.parse_image(png, page_no)
            except Exception as exc:  # noqa: BLE001 - one page must not fail the document
                log.warning("vision parse failed for page %d: %r", page_no, exc)
                return _fallback(page_no, fallback, digest, repr(exc))
        return ParsedPage(page_no, result.markdown, result.provider, result.confidence, digest,
                          result.input_tokens, result.output_tokens)

    return list(await asyncio.gather(*(one(*item) for item in images)))


def _fallback(page_no: int, text: str | None, digest: str | None, why: str) -> ParsedPage:
    if text:
        # A text layer has words but no layout: tables lose their columns, so flag it.
        return ParsedPage(page_no, text, "pdf-text-layer", 0.5, digest)
    return ParsedPage(page_no, "", f"unparsed ({why[:80]})", 0.0, digest)


async def parse_document(kind: str, data: bytes, parser: PageParser | None, *, dpi: int = 144,
                         concurrency: int = 4, prefer_text_layer: bool = False) -> list[ParsedPage]:
    if kind == "pdf":
        count = await asyncio.to_thread(render.pdf_page_count, data)
        texts = [await asyncio.to_thread(render.pdf_text_layer, data, i) for i in range(count)]
        if prefer_text_layer or parser is None:
            return [ParsedPage(i + 1, t, "pdf-text-layer", 0.75 if t else 0.0) for i, t in enumerate(texts)]
        images = [(i + 1, await asyncio.to_thread(render.render_pdf_page, data, i, dpi), texts[i])
                  for i in range(count)]
        return await _vision_pages(images, parser, concurrency)
    if kind == "image":
        png = await asyncio.to_thread(render.image_to_png, data)
        return await _vision_pages([(1, png, None)], parser, concurrency)
    if kind in ("xlsx", "xls", "csv"):
        pages = await asyncio.to_thread(files.workbook_pages, kind, data)
        return [ParsedPage(i + 1, md, "spreadsheet", 1.0) for i, md in enumerate(pages)]
    if kind == "docx":
        pages = await asyncio.to_thread(files.docx_pages, data)
        return [ParsedPage(i + 1, md, "docx", 1.0) for i, md in enumerate(pages)]
    if kind == "pptx":
        pages = await asyncio.to_thread(files.pptx_pages, data)
        return [ParsedPage(i + 1, md, "pptx", 0.9) for i, md in enumerate(pages)]
    if kind == "text":
        return [ParsedPage(1, files.text_pages(data)[0], "text", 1.0)]
    raise files.UnsupportedFile(kind)
