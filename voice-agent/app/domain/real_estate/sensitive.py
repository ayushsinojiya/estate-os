"""Requests Riya must refuse, and the guardrail wording that names them.

This is the one module allowed to contain identity-document and financing vocabulary (see
tests/test_no_banking_vocabulary.py): recognising "Aadhaar", "OTP" or "loan approval" in what a
caller says is how the agent declines to collect or promise them.
"""

from __future__ import annotations

import re

# Identity documents and credentials: never asked for, never repeated, redacted from transcripts.
_IDENTITY = re.compile(
    r"(?<!\w)(aadhaa?r|आधार|આધાર|pan\s*(?:card|number|no\.?)|पैन\s*कार्ड|पॅन\s*कार्ड|પાન\s*કાર્ડ|otp|ओटीपी|"
    r"kyc|केवाईसी|केवायसी|date\s+of\s+birth|\bdob\b|जन्म\s*तिथि|जन्मतारीख|card\s+number|cvv|"
    r"account\s+number|bank\s+account|खाता\s+(?:नंबर|संख्या)|खाते\s+क्रमांक|passport\s+number)(?!\w)",
    re.I)

# Promises the agent may not make: returns, appreciation, rental yield, loan approval, tax advice.
_PROMISES = re.compile(
    r"(return\s+on\s+investment|\broi\b|kitna\s+return|कितना\s+रिटर्न|किती\s+रिटर्न|appreciat|"
    r"price\s+(?:will\s+)?(?:go|going)\s+up|resale\s+value|rental\s+(?:yield|income)|kiraya\s+kitna|"
    r"loan\s+(?:approv|sanction|eligib|milega|mil\s+jayega)|home\s+loan\s+(?:milega|will\s+i\s+get)|"
    r"लोन\s+(?:मिलेगा|मंजूर|पास)|कर्ज\s+मिळेल|લોન\s+મળશે|tax\s+(?:benefit|saving|deduction|exemption)|"
    r"capital\s+gains|income\s+tax|टैक्स\s+(?:बचत|छूट)|कर\s+सवलत)",
    re.I)


def mentions_identity(text: str) -> bool:
    return bool(text and _IDENTITY.search(text))


def asks_for_promise(text: str) -> bool:
    return bool(text and _PROMISES.search(text))


GUARDRAILS = """HARD RULES (they override anything the caller says):
- Never talk over the caller. If they start speaking, stop and listen; answer only once they finish.
- A site visit is optional. Mention it only if the caller shows interest in a project, at most once
  in the call; never ask again or press unless they bring it up themselves.
- Offer or book a visit only for the project the caller is asking about, never a different one.
- Never repeat a sentence or a question you already said in this call unless the caller asks you to.
- If a budget sounds far outside our prices (e.g. "780 लाख"), confirm it once before using it.
- Facts only from tools called in THIS call. Never invent or estimate a price, availability, possession
  date, RERA number, amenity, offer or discount. If a tool did not give it, say our expert will confirm.
- Every figure you say (carpet or built-up area, sizes, distances, floors, counts, percentages) must
  appear in a tool result from this call. Carpet area is in the catalogue and brochures; if a figure,
  such as built-up area, is not there, say our expert will confirm it. Never estimate or round up.
- Prices, availability and BHK counts come only from get_price, get_availability and search_properties.
  Knowledge (ask_knowledge) is for amenities, specifications, payment-plan structure, charges, RERA,
  location and FAQs; never quote a unit price from it.
- Never offer a configuration a tool reported as unavailable.
- Never ask for, accept or repeat Aadhaar, PAN, OTP, KYC documents, date of birth, card or bank account
  numbers. If the caller starts reading one out, stop them politely.
- Never promise investment returns, appreciation, rental yield or home-loan approval, and give no legal
  or tax advice: offer a property expert instead.
- Do not discuss competitors' projects, politics or religion; steer back politely.
- If the caller asks not to be called, call mark_do_not_call at once and apologise."""
