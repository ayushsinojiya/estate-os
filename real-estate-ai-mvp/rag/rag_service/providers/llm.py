"""Model calls the pipeline makes: page parsing (vision), JSON classification and query rewriting.

Providers are swapped by configuration: OpenAI (default) or Mistral OCR for parsing, OpenAI for
classification and rewriting. In fake mode nothing leaves the process.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from rag_service.providers.http import post_json

# The parse prompt is the contract with the vision model: faithful transcription, never invention.
PARSE_PROMPT = """You are transcribing one page of a real-estate document (brochure, price sheet,
payment plan, FAQ, RERA certificate, legal document or floor plan) into Markdown.

Rules:
- Transcribe faithfully. Never add, infer, summarise or correct anything that is not printed.
- Keep the reading order. Use #, ## and ### for headings as they appear on the page.
- Bulleted or numbered content becomes a Markdown list.
- Every table becomes a Markdown table with its header row; keep every row and every figure
  exactly as printed (₹, commas, units, "sq ft", "%"). Merge visually split header cells.
- Keep Devanagari (Hindi, Marathi) and Gujarati text in its original script. Do not translate.
- For a floor plan or image, transcribe its printed labels and dimensions only.
- If part of the page is illegible, write [illegible] in its place.
- Output only the Markdown. On the very last line write CONFIDENCE: <0.0-1.0> for how legible
  and complete your transcription is."""


@dataclass
class PageParse:
    markdown: str
    confidence: float
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class PageParser(Protocol):
    name: str

    async def parse_image(self, image_png: bytes, page_no: int) -> PageParse: ...


_CONFIDENCE = re.compile(r"\n?\s*CONFIDENCE:\s*([01](?:\.\d+)?)\s*$", re.I)


def split_confidence(text: str) -> tuple[str, float]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text).strip()
    match = _CONFIDENCE.search(text)
    if not match:
        return text, 0.8
    return text[:match.start()].rstrip(), max(0.0, min(1.0, float(match.group(1))))


class OpenAIVisionParser:
    def __init__(self, api_key: str, model: str, base_url: str, retries: int = 3,
                 client: httpx.AsyncClient | None = None):
        self.name = f"openai:{model}"
        self.model = model
        self.retries = retries
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient()

    async def parse_image(self, image_png: bytes, page_no: int) -> PageParse:
        data_url = "data:image/png;base64," + base64.b64encode(image_png).decode()
        payload = {"model": self.model, "temperature": 0, "max_tokens": 4096, "messages": [
            {"role": "system", "content": PARSE_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Page {page_no}. Transcribe it."},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}]}]}
        data = await post_json(self._client, self._url, headers=self._headers, payload=payload,
                               retries=self.retries, timeout_s=120)
        markdown, confidence = split_confidence(data["choices"][0]["message"]["content"] or "")
        usage = data.get("usage") or {}
        return PageParse(markdown, confidence, self.name, int(usage.get("prompt_tokens", 0)),
                         int(usage.get("completion_tokens", 0)))


class MistralOCRParser:
    """Mistral OCR returns Markdown per page directly. It reports no confidence, so text density
    stands in for one: a page that came back nearly empty is flagged for review."""

    def __init__(self, api_key: str, model: str, base_url: str, retries: int = 3,
                 client: httpx.AsyncClient | None = None):
        self.name = f"mistral:{model}"
        self.model = model
        self.retries = retries
        self._url = base_url.rstrip("/") + "/ocr"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient()

    async def parse_image(self, image_png: bytes, page_no: int) -> PageParse:
        data_url = "data:image/png;base64," + base64.b64encode(image_png).decode()
        payload = {"model": self.model, "document": {"type": "image_url", "image_url": data_url}}
        data = await post_json(self._client, self._url, headers=self._headers, payload=payload,
                               retries=self.retries, timeout_s=120)
        pages = data.get("pages") or []
        markdown = "\n\n".join(p.get("markdown", "") for p in pages).strip()
        confidence = 0.9 if len(markdown) >= 40 else 0.4
        usage = data.get("usage_info") or {}
        # Mistral OCR is billed per page, not per token; page counts are recorded on the document.
        return PageParse(markdown, confidence, self.name)


class JsonModel(Protocol):
    async def complete_json(self, system: str, user: str, schema_name: str,
                            schema: dict[str, Any]) -> dict[str, Any]: ...


class ChatJsonModel:
    """Any OpenAI-compatible chat API in JSON mode; Groq by default (structured extraction)."""

    def __init__(self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None,
                 timeout_s: float = 90.0, retries: int = 8, max_tokens: int = 8192):
        self.name = model
        self.model = model
        self.timeout_s = timeout_s
        self.retries = retries
        self.max_tokens = max_tokens
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient()

    async def complete(self, system: str, user: str) -> dict[str, Any]:
        payload = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        data = await post_json(self._client, self._url, headers=self._headers, payload=payload,
                               retries=self.retries, timeout_s=self.timeout_s)
        text = data["choices"][0]["message"]["content"] or "{}"
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        value = json.loads(text)
        return value if isinstance(value, dict) else {}


class OpenAIJsonModel:
    def __init__(self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None,
                 timeout_s: float = 20.0, retries: int = 2):
        self.model = model
        self.timeout_s = timeout_s
        self.retries = retries
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient()

    async def complete_json(self, system: str, user: str, schema_name: str,
                            schema: dict[str, Any]) -> dict[str, Any]:
        payload = {"model": self.model, "temperature": 0, "max_tokens": 400,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": schema_name, "strict": True, "schema": schema}}}
        data = await post_json(self._client, self._url, headers=self._headers, payload=payload,
                               retries=self.retries, timeout_s=self.timeout_s)
        return json.loads(data["choices"][0]["message"]["content"])
