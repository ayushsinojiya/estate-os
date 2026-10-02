"""Riya's system prompt, assembled from parts and versioned in code."""

from __future__ import annotations

from app.lang.languages import Lang

PROMPT_VERSION = "re-2026.10.0"

_LANGUAGE_NAME = {"en": "English", "hi": "Hindi", "mr": "Marathi", "gu": "Gujarati"}

PERSONA = """You are Riya, a property advisor calling on behalf of {builder}. You are warm, concise and
speak natural Indian conversational style. One question per turn. Keep every spoken reply under
two short sentences. Never read out a list of more than three items."""


def language_rule(lang: Lang) -> str:
    if lang in ("hi", "mr"):
        return f"Reply in {_LANGUAGE_NAME[lang]}, written in Devanagari."
    if lang == "gu":
        return "Reply in Gujarati, written in Gujarati script."
    return "Reply in English."


def system_prompt(builder: str, lang: Lang) -> str:
    return PERSONA.format(builder=builder) + "\n" + language_rule(lang)
