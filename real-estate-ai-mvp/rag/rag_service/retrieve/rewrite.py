"""Query rewriting for the CRM path: Hinglish, Marathi or Gujarati in, short English search out."""

from __future__ import annotations

import logging

from rag_service.providers.llm import JsonModel

log = logging.getLogger(__name__)

_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["query", "paraphrases"],
    "properties": {"query": {"type": "string"},
                   "paraphrases": {"type": "array", "items": {"type": "string"}}},
}

_SYSTEM = """Rewrite a real-estate question as a short English keyword search query for a document
search engine (brochures, price sheets, payment plans, FAQs, RERA). The question may be in English,
Hindi, Marathi, Gujarati or a mix written in any script. Keep project names, place names, numbers
and units exactly. Add up to 2 paraphrases using different likely document wording (e.g.
"floor rise charge" / "floor-wise premium"). Never answer the question."""


async def rewrite(model: JsonModel | None, question: str) -> list[str]:
    """[english_query, *paraphrases]; just the question itself when no model is available."""
    if model is None:
        return [question]
    try:
        result = await model.complete_json(_SYSTEM, question, "search_query", _SCHEMA)
    except Exception as exc:  # noqa: BLE001 - search still works on the original wording
        log.warning("query rewrite failed: %r", exc)
        return [question]
    queries = [result.get("query", "").strip()] + [p.strip() for p in result.get("paraphrases", [])[:2]]
    out: list[str] = []
    for q in queries:
        if q and q.lower() not in (x.lower() for x in out):
            out.append(q)
    return out or [question]
