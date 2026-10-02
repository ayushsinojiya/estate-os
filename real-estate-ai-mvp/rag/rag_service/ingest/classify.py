"""Document type and language, from the first pages and the filename.

The CRM's own metadata wins when it supplies a type. Otherwise one cheap model call classifies
the document; without a model (fake mode, or the call fails) filename and content keywords decide.
"""

from __future__ import annotations

import logging
import re

from rag_service.ingest.chunk import detect_language
from rag_service.providers.llm import JsonModel

log = logging.getLogger(__name__)

DOC_TYPES = ("BROCHURE", "PRICE_SHEET", "PAYMENT_PLAN", "FAQ", "RERA", "LEGAL", "FLOOR_PLAN", "OTHER")
LANGS = ("en", "hi", "mr", "gu")

_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["doc_type", "languages"],
    "properties": {
        "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
        "languages": {"type": "array", "items": {"type": "string", "enum": list(LANGS)}},
    },
}

_SYSTEM = """Classify a real-estate document from its filename and first pages.
doc_type: BROCHURE (marketing overview, amenities, location), PRICE_SHEET (unit prices, charges),
PAYMENT_PLAN (payment stages / schedule), FAQ (questions and answers), RERA (registration
certificate or RERA details), LEGAL (agreement, title, approvals), FLOOR_PLAN (unit layouts),
OTHER. languages: every language the text is written in (en, hi, mr, gu)."""

_KEYWORDS = [
    ("FAQ", r"\bfaqs?\b|frequently asked|questions"),
    ("PRICE_SHEET", r"price|pricing|cost sheet|rate card|charges|tariff"),
    ("PAYMENT_PLAN", r"payment\s*(plan|schedule)|installment|instalment|construction linked|clp"),
    ("RERA", r"\brera\b|registration certificate|maharera"),
    ("FLOOR_PLAN", r"floor\s*plan|layout|unit plan|typical floor"),
    ("LEGAL", r"agreement|legal|title deed|sale deed|noc|approval|allotment"),
    ("BROCHURE", r"brochure|e-?brochure|overview|amenit|project highlights"),
]


def heuristic(file_name: str, text: str) -> str:
    name = file_name.lower()
    for doc_type, pattern in _KEYWORDS:
        if re.search(pattern, name):
            return doc_type
    sample = text[:4000].lower()
    scores = {doc_type: len(re.findall(pattern, sample)) for doc_type, pattern in _KEYWORDS}
    if sum(1 for line in sample.splitlines() if line.strip().endswith("?")) >= 3:
        scores["FAQ"] += 3
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "OTHER"


def languages_of(text: str) -> list[str]:
    found = []
    for paragraph in [p for p in re.split(r"\n\s*\n", text) if p.strip()][:200]:
        lang = detect_language(paragraph)
        if lang not in found:
            found.append(lang)
    return found or ["en"]


async def classify(file_name: str, pages: list[str], model: JsonModel | None) -> tuple[str, list[str]]:
    sample = "\n\n".join(pages[:2])[:6000]
    if model is not None and sample.strip():
        try:
            result = await model.complete_json(
                _SYSTEM, f"Filename: {file_name}\n\nFirst pages:\n{sample}", "classification", _SCHEMA)
            doc_type = result.get("doc_type") if result.get("doc_type") in DOC_TYPES else "OTHER"
            langs = [lang for lang in result.get("languages", []) if lang in LANGS]
            return doc_type, langs or languages_of(sample)
        except Exception as exc:  # noqa: BLE001 - classification is best effort
            log.warning("classification call failed (%r); using keywords", exc)
    return heuristic(file_name, sample), languages_of("\n\n".join(pages)[:20000])
