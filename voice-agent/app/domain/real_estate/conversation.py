"""One call, from the real-estate side."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.base import CallerTurnAction, CallInfo, CallRecord, Tool
from app.lang.languages import Lang
from app.llm.base import Message

from .prompt import system_prompt

if TYPE_CHECKING:
    from .plugin import RealEstatePlugin


class RealEstateConversation:
    def __init__(self, plugin: "RealEstatePlugin", info: CallInfo):
        self.plugin = plugin
        self.info = info
        s = plugin.settings
        self.initial_language: Lang = info.language_hint or (
            s.default_outbound_language if info.direction == "outbound" else s.default_inbound_language)

    async def start(self) -> None:
        return None

    def opening(self, lang: Lang) -> tuple[str, str | None]:
        return self.plugin.phrases.render("greeting_inbound", lang), "greeting_inbound"

    def messages(self, lang: Lang) -> list[Message]:
        return [Message("system", system_prompt(self.plugin.phrases.builder_name, lang))]

    def tools(self) -> list[Tool]:
        return []

    def screen_caller(self, text: str, lang: Lang) -> CallerTurnAction | None:
        return None

    def screen_reply(self, sentence: str, lang: Lang) -> str:
        return sentence

    def on_agent_reply(self, text: str) -> None:
        return None

    async def finish(self, record: CallRecord) -> None:
        return None
