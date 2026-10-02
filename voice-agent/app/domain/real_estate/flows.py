"""Call flows as small stage machines.

The model chooses the words; this module decides what the call is for right now and when it may
move on. Each call type has its own stages. `advance()` is re-evaluated after every caller turn,
tool result and agent reply, and the current stage's goal is what the system prompt asks for.

  INBOUND / OUTBOUND_NEW_LEAD:  OPENING → DISCOVERY → QUALIFY → RECOMMEND → VISIT → WRAP_UP
  VISIT_REMINDER:               OPENING → REMIND → RESOLVE → WRAP_UP
  CALLBACK / RE_ENGAGEMENT:     OPENING → DELTA → QUALIFY → RECOMMEND → VISIT → WRAP_UP
"""

from __future__ import annotations

from .state import CallState

STAGES = {
    "INBOUND": ["OPENING", "DISCOVERY", "QUALIFY", "RECOMMEND", "VISIT", "WRAP_UP"],
    "OUTBOUND_NEW_LEAD": ["OPENING", "DISCOVERY", "QUALIFY", "RECOMMEND", "VISIT", "WRAP_UP"],
    "VISIT_REMINDER": ["OPENING", "REMIND", "RESOLVE", "WRAP_UP"],
    "CALLBACK": ["OPENING", "DELTA", "QUALIFY", "RECOMMEND", "VISIT", "WRAP_UP"],
    "RE_ENGAGEMENT": ["OPENING", "DELTA", "QUALIFY", "RECOMMEND", "VISIT", "WRAP_UP"],
}

GOALS = {
    ("INBOUND", "OPENING"): "Find out how you can help and which project or locality they are calling about "
                            "(an ad, hoarding or portal).",
    ("OUTBOUND_NEW_LEAD", "OPENING"): "Check it is a good time to talk. If not, offer a callback time "
                                      "(schedule_callback) and end the call politely.",
    ("CALLBACK", "OPENING"): "Confirm it is a good time, then pick up from the last conversation.",
    ("RE_ENGAGEMENT", "OPENING"): "Confirm it is a good time, then pick up from the last conversation.",
    ("VISIT_REMINDER", "OPENING"): "Confirm you are speaking to the right person, by name only. Ask for no ID.",
    "DISCOVERY": "Understand what they are looking for and which project or locality interests them.",
    "DELTA": "Ask what has changed since the last conversation and update only that.",
    "QUALIFY": "Fill the missing requirements naturally, one question per turn, never as an interrogation. "
               "Read critical values back once and record the outcome with save_requirements(readback=…).",
    "RECOMMEND": "Use search_properties (or get_price for a named project) and recommend at most two options "
                 "that are available, in their budget.",
    "VISIT": "Offer a site visit: get_visit_slots, offer two or three times, book the one they pick with "
             "book_site_visit, then confirm project, day, time and the agent's name aloud.",
    "REMIND": "Remind them of the visit: project, day and time, address and the agent meeting them.",
    "RESOLVE": "Confirm the visit (confirm_visit), or reschedule it (get_visit_slots, then reschedule_visit), "
               "or cancel it (ask why, offer a later date, cancel_visit).",
    "WRAP_UP": "Offer the brochure or visit details on WhatsApp (ask permission first; send_whatsapp only if "
               "they agree), summarise the next step in one sentence and end_call.",
}


def goal(state: CallState) -> str:
    return GOALS.get((state.call_type, state.stage)) or GOALS.get(state.stage, "")


def _qualified(state: CallState) -> bool:
    r = state.requirements
    budget = r.budget_max is not None or r.budget_min is not None
    return budget and bool(r.bhk) and bool(r.locality or r.project_id)


def advance(state: CallState) -> str:
    """Move forward when the current stage's exit condition holds. Never moves back."""
    stages = STAGES.get(state.call_type, STAGES["INBOUND"])
    current = state.stage if state.stage in stages else stages[0]
    index = stages.index(current)

    def at_least(name: str) -> None:
        nonlocal index
        if name in stages:
            index = max(index, stages.index(name))

    if state.caller_turns >= 1:
        at_least(stages[1])
    if state.call_type == "VISIT_REMINDER":
        if state.identity_confirmed or state.caller_turns >= 1:
            at_least("REMIND")
        if state.caller_turns >= 2:
            at_least("RESOLVE")
        if state.visit_outcome:
            at_least("WRAP_UP")
    else:
        r = state.requirements
        if r.known() or state.recommended:
            at_least("QUALIFY")
        if _qualified(state) or state.recommended:
            at_least("RECOMMEND")
        if state.recommended or state.asked_to_book or state.offered_slots:
            at_least("VISIT")
        if state.booked_visit or state.visit_declined:
            at_least("WRAP_UP")
    if state.callback_at and state.caller_turns <= 2:
        at_least("WRAP_UP")  # "call me later": nothing more to do on this call
    state.stage = stages[index]
    return state.stage
