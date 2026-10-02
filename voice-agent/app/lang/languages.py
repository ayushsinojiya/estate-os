"""Caller-language detection (spec section 16): follow the caller, never announce it."""

from __future__ import annotations

from typing import Literal

from app.lang.text import devanagari_ratio, gujarati_ratio, tokenize

Lang = Literal["mr", "hi", "en", "gu"]
LANGS: tuple[Lang, ...] = ("mr", "hi", "en", "gu")

_MR = {
    "आहे", "आहेत", "नाही", "मला", "तुम्ही", "आपण", "पाहिजे", "हवं", "हवा", "हवी", "काय", "कसं",
    "कधी", "किती", "बरोबर", "हो", "नको", "मी", "आम्ही", "तुमचं", "माझं", "साठी", "आणि", "पण",
    "येईल", "सांगा", "बघा", "करायचं", "घ्यायचं", "आता", "उद्या", "परवा", "कुठे", "इथे", "तिथे",
}
_HI = {
    "है", "हैं", "नहीं", "मुझे", "आप", "चाहिए", "क्या", "कैसे", "कब", "कितना", "कितने", "ठीक",
    "हाँ", "हां", "मैं", "हम", "के", "का", "की", "में", "से", "को", "रहा", "रही", "और", "लेकिन",
    "बताइए", "कल", "परसों", "कहाँ", "यहाँ", "वहाँ", "था", "थी",
}
_MR_ROMAN = {"aahe", "ahe", "mala", "pahije", "kiti", "kadhi", "barobar", "nako", "tumhi", "aapan", "hava", "havi", "udya", "parva", "kuthe"}
_HI_ROMAN = {"hai", "hain", "mujhe", "chahiye", "kitna", "kitne", "kab", "kya", "aap", "nahin", "theek", "haan", "kal", "parso", "kahan"}
# Gujarati is written in its own script, so script alone is strong evidence; these cover codemix
# transcripts, where Saaras writes Gujarati speech in Latin letters.
_GU = {
    "છે", "નથી", "મને", "તમે", "શું", "કેમ", "ક્યારે", "કેટલા", "કેટલું", "જોઈએ", "હા", "ના", "અને", "પણ",
    "આવતીકાલે", "ક્યાં", "અહીં", "બરાબર",
}
_GU_ROMAN = {"che", "chhe", "nathi", "mane", "tame", "shu", "kem", "ketla", "ketlu", "joie", "joiye", "kyare", "avtikale"}

_STT_HINT = {"mr-IN": "mr", "hi-IN": "hi", "en-IN": "en", "gu-IN": "gu",
             "mr": "mr", "hi": "hi", "en": "en", "gu": "gu"}


def detect_language(text: str, stt_language: str | None = None) -> tuple[Lang | None, float]:
    """Return (language, confidence 0..1). None when there is not enough signal."""
    toks = tokenize(text)
    scores = {"mr": 0.0, "hi": 0.0, "en": 0.0, "gu": 0.0}
    for tok in toks:
        if tok in _MR or tok in _MR_ROMAN:
            scores["mr"] += 1
        if tok in _HI or tok in _HI_ROMAN:
            scores["hi"] += 1
        if tok in _GU or tok in _GU_ROMAN:
            scores["gu"] += 1
    gujarati = gujarati_ratio(text)
    if gujarati >= 0.5:
        scores["gu"] += 2 + len(toks) * 0.5
    if "ळ" in text:
        scores["mr"] += 1.5
    hint = _STT_HINT.get(stt_language or "")
    if hint:
        scores[hint] += 1.5
    dev = devanagari_ratio(text)
    # Latin script is weak evidence for English. Sarvam's codemix mode transcribes Hindi and
    # Marathi speech in Latin too, and a one-word reply ("ok", "hello") carries no language at
    # all — treating either as confident English flips the whole call into the wrong language.
    # So English needs a few words of its own, and never overrides the recogniser's own tag.
    if (dev < 0.2 and gujarati < 0.2 and scores["mr"] == 0 and scores["hi"] == 0 and scores["gu"] == 0
            and len(toks) >= 3 and hint not in ("hi", "mr", "gu")):
        scores["en"] += 1 + min(len(toks), 4) * 0.25
    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    if scores[best] == 0:
        return None, 0.0
    return best, scores[best] / total  # type: ignore[return-value]


class LanguageTracker:
    """Keeps the call language stable; switches only on a confident change.

    Hindi and Marathi share much of their common vocabulary, so a genuine Hindi utterance often
    scores for both and lands near the middle of the confidence range. The threshold is therefore
    configurable, and the STT's own language tag can settle it outright: when the recogniser and
    the wording agree, there is nothing to be gained by waiting for another turn.
    """

    def __init__(self, initial: Lang, switch_confidence: float = 0.6):
        self.current: Lang = initial
        self.switches = 0
        self.used: set[Lang] = {initial}
        self.switch_confidence = switch_confidence

    def observe(self, text: str, stt_language: str | None = None) -> Lang:
        lang, confidence = detect_language(text, stt_language)
        hinted = _STT_HINT.get(stt_language or "")
        # The recogniser identified the language and the wording agrees: switch on this turn.
        decisive = hinted is not None and lang == hinted
        if lang and lang != self.current and (decisive or confidence >= self.switch_confidence):
            self.current = lang
            self.switches += 1
        if lang:
            self.used.add(lang)
        return self.current
