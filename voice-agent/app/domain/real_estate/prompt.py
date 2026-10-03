"""Riya's system prompt, assembled from parts and versioned in code.

Kept compact because every token is paid on every turn of a live call: persona, speaking rules,
guardrails, this call's goal, what is already known, the catalogue, and how to use the tools.
PROMPT_VERSION is logged with every call and sent to the CRM with the call record.
"""

from __future__ import annotations

from typing import Any

from app.lang.languages import Lang

from . import flows
from .sensitive import GUARDRAILS
from .state import CallState

PROMPT_VERSION = "re-2026.10.1"

_LANGUAGE_NAME = {"en": "English", "hi": "Hindi", "mr": "Marathi"}

PERSONA = """You are Riya, a property advisor calling on behalf of {builder}. You are on a phone call.
Speak in a warm, concise, natural Indian conversational style.
- Ask ONE question per turn. Keep every reply under about two short sentences.
- Never read out a list of more than three items.
- Write every number in digits exactly as the tools give them, never as words: "76.5 lakh",
  "1 crore 5 lakh", "720 sq ft", "3 units", "Monday 6 PM". The voice reads them out in words.
  Prices the Indian way with lakh/crore, never as long numbers; times in IST.
- Follow the caller's language and code-mixing; never announce a language switch.
- You already introduced yourself{disclosure}; do not repeat it."""


def language_rule(lang: Lang) -> str:
    if lang in ("hi", "mr"):
        return f"Reply in {_LANGUAGE_NAME[lang]} written in Devanagari; common English property words may stay English."
    return "Reply in English."


TOOLS = """TOOLS:
- Prices/availability: get_price, get_availability, search_properties. These are the only source of prices.
- ask_knowledge: amenities, specifications, payment-plan stages, charges, RERA, location, FAQs. Write
  `question` as short English keywords even when the caller speaks Hindi or Marathi. Answer
  only from the returned chunks; if nothing relevant comes back, say an expert will confirm.
- save_requirements: whenever you learn a requirement (budget in rupees, BHK, locality, timing, purpose).
- Visits: get_visit_slots, offer 2–3 options once, then book_site_visit with one of the offered slot_start values.
  Offer a visit at most once unless the caller raises it again; never repeat the same times.
  "दिखाइए / दिखाओ / show me" means tell them about the options, not a site visit. Ask "would you like to
  visit?" first and look up times only after they say yes.
- schedule_callback: `when` as an ISO date-time in IST (+05:30); callbacks go between 09:00 and 21:00.
- request_human: the caller asks for a person, wants to negotiate, asks about booking amount, agreement or
  legal matters, or you cannot answer a real question.
- send_whatsapp: only after the caller says yes to receiving it on WhatsApp.
- mark_do_not_call: the moment they ask not to be called. end_call: to close politely."""


def _context(state: CallState) -> str:
    lines: list[str] = []
    name = state.lead_name
    if name:
        lines.append(f"Caller: {name}.")
    known = state.requirements.known()
    if known:
        lines.append("Already known (do not ask again): " + ", ".join(f"{k}={v}" for k, v in known.items()) + ".")
    prefs = state.context.get("knownPreferences") or {}
    if prefs:
        lines.append("From the CRM: " + ", ".join(f"{k}={v}" for k, v in prefs.items()) + ".")
    if state.context.get("lastSummary"):
        lines.append(f"Last conversation: {state.context['lastSummary']}")
    visit = state.context.get("visit") or {}
    if visit:
        lines.append(f"Visit: {visit.get('projectName')} on {visit.get('spokenTime')} IST at "
                     f"{visit.get('address')}, with {visit.get('agentName') or 'our property expert'}"
                     f" (status {visit.get('status')}).")
    if state.context.get("projectName"):
        lines.append(f"They enquired about {state.context['projectName']}"
                     + (f" via {state.context['source']}" if state.context.get("source") else "") + ".")
    if state.booked_visit:
        lines.append(f"Booked in this call: {state.booked_visit.get('projectName')} on "
                     f"{state.booked_visit.get('spokenTime')} with {state.booked_visit.get('agentName')}.")
    missing = state.requirements.missing()
    if missing and state.call_type != "VISIT_REMINDER":
        lines.append("Still unknown: " + ", ".join(missing) + ".")
    return "\n".join(lines)


def catalog_summary(catalog: dict[str, Any] | None, limit: int = 30) -> str:
    if not catalog or not catalog.get("projects"):
        return "PROJECTS: (catalogue unavailable; use search_properties)"
    localities = {loc["id"]: loc["name"] for loc in catalog.get("localities", [])}
    parts = []
    for project in catalog["projects"][:limit]:
        aliases = [a for a in project.get("aliases", []) if a.lower() != project["name"].lower()]
        parts.append(f"{project['name']} — {localities.get(project.get('localityId'), '')}"
                     + (f" (also: {', '.join(aliases)})" if aliases else ""))
    return "PROJECTS you sell (only these): " + "; ".join(parts) + "."


def system_prompt(state: CallState, builder: str, lang: Lang, catalog: dict[str, Any] | None,
                  disclosure: bool = True) -> str:
    persona = PERSONA.format(builder=builder, disclosure=" and made the AI/recording disclosure" if disclosure else "")
    sections = [
        persona,
        language_rule(lang),
        GUARDRAILS,
        f"THIS CALL ({state.call_type}, stage {state.stage}): {flows.goal(state)}",
        _context(state),
        catalog_summary(catalog),
        TOOLS,
    ]
    return "\n\n".join(s for s in sections if s)


def probe_prompt(builder: str) -> str:
    return PERSONA.format(builder=builder, disclosure="") + "\n" + language_rule("mr")
