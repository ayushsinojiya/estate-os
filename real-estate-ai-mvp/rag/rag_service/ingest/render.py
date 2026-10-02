"""Page images for the vision parser."""

from __future__ import annotations

import hashlib
import io


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


def render_pdf_page(data: bytes, index: int, dpi: int = 144) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[index]
        image = page.render(scale=dpi / 72).to_pil()
        page.close()
    finally:
        pdf.close()
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def pdf_text_layer(data: bytes, index: int) -> str:
    """The text a PDF carries, if any. Used offline and when vision parsing fails."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[index]
        text = page.get_textpage().get_text_range()
        page.close()
        return text.replace("\r\n", "\n").strip()
    finally:
        pdf.close()


def image_to_png(data: bytes, max_side: int = 2400) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image.load()
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def image_hash(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()
