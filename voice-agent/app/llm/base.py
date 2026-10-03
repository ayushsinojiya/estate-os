"""Provider-neutral LLM interface. Provider request shapes stay inside provider modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol, Union


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    provider_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallStarted:
    """The model has begun emitting a tool call (name known, arguments still streaming)."""
    name: str


@dataclass
class ToolCallReady:
    call: ToolCall


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class Finished:
    reason: str = "stop"


LLMEvent = Union[TextDelta, ToolCallStarted, ToolCallReady, Usage, Finished]


class LLMError(RuntimeError):
    kind = "error"


class RateLimited(LLMError):
    kind = "rate_limited"


class ProviderUnavailable(LLMError):
    kind = "unavailable"


class InvalidRequest(LLMError):
    kind = "invalid_request"


class LLMProvider(Protocol):
    name: str

    def stream(self, messages: list[Message], tools: list[ToolSpec], *, max_tokens: int = 400,
               temperature: float = 0.3) -> AsyncIterator[LLMEvent]: ...
