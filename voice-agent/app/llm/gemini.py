"""Gemini 3.5 Flash-Lite on Vertex AI (fallback LLM, spec section 7).

Gemini 3 attaches thought signatures to function calls that must be sent back in history. Calls
that came from another provider (mid-call failover from Sarvam) carry no signature, so the
documented dummy value is used for them.
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any, AsyncIterator

from app.llm.base import (Finished, InvalidRequest, LLMEvent, Message, ProviderUnavailable, RateLimited, TextDelta,
                          ToolCall, ToolCallReady, ToolSpec, Usage)

SKIP_SIGNATURE = b"skip_thought_signature_validator"
SIGNATURE_KEY = "gemini_thought_signature"


def _as_object(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        return {"result": content}
    return value if isinstance(value, dict) else {"result": value}


def to_contents(messages: list[Message]) -> tuple[str, list[Any]]:
    from google.genai import types

    system: list[str] = []
    contents: list[Any] = []
    pending_responses: list[Any] = []

    def flush() -> None:
        if pending_responses:
            contents.append(types.Content(role="user", parts=list(pending_responses)))
            pending_responses.clear()

    for m in messages:
        if m.role == "system":
            system.append(m.content)
            continue
        if m.role == "tool":
            pending_responses.append(types.Part.from_function_response(name=m.name or "tool", response=_as_object(m.content)))
            continue
        flush()
        if m.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m.content)]))
        else:
            parts: list[Any] = []
            if m.content:
                parts.append(types.Part.from_text(text=m.content))
            for i, call in enumerate(m.tool_calls):
                encoded = call.provider_meta.get(SIGNATURE_KEY)
                signature = base64.b64decode(encoded) if encoded else (SKIP_SIGNATURE if i == 0 else None)
                parts.append(types.Part(
                    function_call=types.FunctionCall(name=call.name, args=_as_object(call.arguments)),
                    thought_signature=signature,
                ))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
    flush()
    return "\n\n".join(system), contents


class GeminiLLM:
    def __init__(self, model: str, project: str, location: str, thinking_level: str = "MINIMAL", client: Any = None):
        self.name = "gemini"
        self.model = model
        self.project = project
        self.location = location
        self.thinking_level = thinking_level
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=self.project, location=self.location)
        return self._client

    def _config(self, system: str, tools: list[ToolSpec], max_tokens: int, temperature: float) -> Any:
        from google.genai import types

        config: dict[str, Any] = {
            "system_instruction": system or None,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            "thinking_config": types.ThinkingConfig(thinking_level=types.ThinkingLevel(self.thinking_level)),
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if tools:
            config["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
                for t in tools
            ])]
        return types.GenerateContentConfig(**config)

    async def stream(self, messages: list[Message], tools: list[ToolSpec], *, max_tokens: int = 400,
                     temperature: float = 0.3) -> AsyncIterator[LLMEvent]:
        from google.genai import errors

        system, contents = to_contents(messages)
        config = self._config(system, tools, max_tokens, temperature)
        finish = "stop"
        try:
            stream = await self._get_client().aio.models.generate_content_stream(model=self.model, contents=contents, config=config)
            async for chunk in stream:
                for candidate in chunk.candidates or []:
                    if candidate.finish_reason:
                        finish = str(candidate.finish_reason)
                    for part in (candidate.content.parts if candidate.content and candidate.content.parts else []):
                        if part.thought:
                            continue
                        if part.text:
                            yield TextDelta(part.text)
                        if part.function_call:
                            fc = part.function_call
                            meta = {SIGNATURE_KEY: base64.b64encode(part.thought_signature).decode()} if part.thought_signature else {}
                            yield ToolCallReady(ToolCall(id=fc.id or f"call_{uuid.uuid4().hex[:8]}", name=fc.name or "",
                                                         arguments=json.dumps(dict(fc.args or {}), ensure_ascii=False),
                                                         provider_meta=meta))
                usage = chunk.usage_metadata
                if usage and usage.candidates_token_count:
                    yield Usage(usage.prompt_token_count or 0, usage.candidates_token_count or 0,
                                usage.cached_content_token_count or 0)
        except errors.APIError as exc:
            if exc.code == 429:
                raise RateLimited(str(exc)) from exc
            if exc.code and exc.code >= 500:
                raise ProviderUnavailable(str(exc)) from exc
            raise InvalidRequest(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - e.g. missing Google credentials, network errors
            raise ProviderUnavailable(f"gemini unavailable: {exc!r}") from exc
        yield Finished(finish)
