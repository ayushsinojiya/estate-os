"""Speech text for Marathi and Hindi TTS: Devanagari only, numbers as words (CL-010).

The prompt already asks the LLM for this. This is the deterministic safety net applied to every spoken LLM
clause and backend-rendered sentence: digits become number words, common English property terms and the
known project/locality names get their Devanagari spelling, short capitalised acronyms are spelled out, and
₹ / % are spoken. Unknown English words are left as they are rather than guessed.
"""

from __future__ import annotations

import re
from datetime import time
from collections.abc import Mapping

from app.lang import spoken
from app.lang.languages import Lang

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

_LETTERS = {
    "a": "ए", "b": "बी", "c": "सी", "d": "डी", "e": "ई", "f": "एफ", "g": "जी", "h": "एच", "i": "आय", "j": "जे",
    "k": "के", "l": "एल", "m": "एम", "n": "एन", "o": "ओ", "p": "पी", "q": "क्यू", "r": "आर", "s": "एस", "t": "टी",
    "u": "यू", "v": "व्ही", "w": "डब्ल्यू", "x": "एक्स", "y": "वाय", "z": "झेड",
}
_HI_LETTERS = {"i": "आई", "v": "वी"}

# English words common in property calls: (Marathi, Hindi) spelling
_WORDS: dict[str, tuple[str, str]] = {
    "apartment": ("अपार्टमेंट", "अपार्टमेंट"), "property": ("प्रॉपर्टी", "प्रॉपर्टी"), "properties": ("प्रॉपर्टीज", "प्रॉपर्टीज"),
    "site": ("साइट", "साइट"), "visit": ("व्हिजिट", "विज़िट"), "project": ("प्रोजेक्ट", "प्रोजेक्ट"),
    "projects": ("प्रोजेक्ट्स", "प्रोजेक्ट्स"), "phase": ("फेज", "फेज़"), "tower": ("टॉवर", "टावर"), "floor": ("फ्लोअर", "फ्लोर"),
    "amenities": ("सुविधा", "सुविधाएं"), "clubhouse": ("क्लबहाऊस", "क्लबहाउस"), "club": ("क्लब", "क्लब"), "gym": ("जिम", "जिम"),
    "pool": ("पूल", "पूल"), "swimming": ("स्विमिंग", "स्विमिंग"), "garden": ("गार्डन", "गार्डन"), "parking": ("पार्किंग", "पार्किंग"),
    "lift": ("लिफ्ट", "लिफ्ट"), "security": ("सिक्युरिटी", "सिक्योरिटी"), "school": ("स्कूल", "स्कूल"),
    "hospital": ("हॉस्पिटल", "हॉस्पिटल"), "mall": ("मॉल", "मॉल"), "office": ("ऑफिस", "ऑफिस"), "location": ("लोकेशन", "लोकेशन"),
    "area": ("एरिया", "एरिया"), "carpet": ("कार्पेट", "कार्पेट"), "sqft": ("स्क्वेअर फूट", "स्क्वायर फुट"),
    "budget": ("बजेट", "बजट"), "price": ("किंमत", "कीमत"),
    "payment": ("पेमेंट", "पेमेंट"), "plan": ("प्लॅन", "प्लान"), "offer": ("ऑफर", "ऑफर"), "discount": ("डिस्काउंट", "डिस्काउंट"),
    "possession": ("पझेशन", "पज़ेशन"), "ready": ("रेडी", "रेडी"), "sample": ("सॅम्पल", "सैंपल"), "rera": ("रेरा", "रेरा"),
    "lakh": ("लाख", "लाख"), "lakhs": ("लाख", "लाख"), "crore": ("कोटी", "करोड़"), "crores": ("कोटी", "करोड़"),
    "available": ("उपलब्ध", "उपलब्ध"), "booking": ("बुकिंग", "बुकिंग"), "book": ("बुक", "बुक"), "call": ("कॉल", "कॉल"),
    "team": ("टीम", "टीम"), "number": ("नंबर", "नंबर"), "details": ("डिटेल्स", "डिटेल्स"), "line": ("लाईन", "लाइन"),
    "connected": ("कनेक्टेड", "कनेक्टेड"), "connection": ("कनेक्शन", "कनेक्शन"), "realty": ("रिअल्टी", "रियल्टी"),
    "ok": ("ओके", "ओके"), "okay": ("ओके", "ओके"), "sir": ("सर", "सर"), "madam": ("मॅडम", "मैडम"),
    "hello": ("हॅलो", "हैलो"), "thank": ("थँक", "थैंक"), "thanks": ("थँक्स", "थैंक्स"), "you": ("यू", "यू"),
}

_MONEY_RE = re.compile(
    r"(?:₹|\b(?:rs|inr)\.?)\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(\s*(?:lakhs?|crores?|लाख|करोड़|कोटी)\b)?", re.I)
# Codes mixing letters and digits (RERA P52100012345) are read character by character, zeros included.
_CODE_RE = re.compile(r"(?<![A-Za-z0-9])(?=(?:[A-Za-z0-9]*[A-Za-z]){2})(?=(?:[A-Za-z0-9]*\d){2})[A-Za-z0-9]+(?![A-Za-z0-9])")
# Phone numbers written in groups: 1800-419-2266, 020-2544-3390, 1800 419 2266.
_PHONE_RE = re.compile(r"(?<![\d.,])\d{2,5}(?:[ -]\d{2,5}){1,3}(?![\d.,])")
# Unformatted runs of 6+ digits (PIN codes, codes) and anything with a leading zero are read digit by digit.
_DIGITS_RE = re.compile(r"(?<![\d.,])(?:0\d+|\d{6,})(?![\d.,])")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)(?:\s*(AM|PM|am|pm)\b)?(?:\s*(?:बजे|वाजता))?")
_HOUR_RE = re.compile(r"(?<![\d.:])(\d{1,2})\s*(AM|PM|am|pm)\b(?:\s*(?:बजे|वाजता))?")
# Number units are always spoken in the call language, even inside an English-heavy sentence.
_UNIT_RE = re.compile(r"\b(lakhs?|crores?)\b", re.I)
_ROUND_THE_CLOCK_RE = re.compile(r"\b24\s*[x×]\s*7\b", re.I)
_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_LATIN_RE = re.compile(r"[A-Za-z]+")
# "8.65% – 9.75%", "7–45 days": spoken as a range, or the dash is lost and the two figures run together.
_RANGE_RE = re.compile(r"(?<=[\d%])\s*[–—-]\s*(?=[₹\d])")
# A dash left between spoken words ("एक लाख रुपये – दस लाख रुपये", "दस बजे–चार बजे") is also a
# range. An English hyphenated word (toll-free) is left alone.
_SPOKEN_RANGE_RE = re.compile(r"(?<=[ऀ-ॿ0-9%])\s*[–—]\s*(?=[ऀ-ॿ0-9₹])|(?<=[ऀ-ॿ0-9%])\s+-\s+(?=[ऀ-ॿ0-9₹])")

_name_patterns: dict[int, list[tuple[re.Pattern[str], str]]] = {}


def _names(names: Mapping[str, str]) -> list[tuple[re.Pattern[str], str]]:
    """Latin name -> its Devanagari spelling, e.g. {"Kothrud": "कोथरूड"}.

    Proper nouns a caller hears — the builder's name, its projects — should be spoken in the script
    of the conversation rather than spelled out letter by letter.
    """
    key = id(names)
    if key not in _name_patterns:
        pairs = [(latin, dev) for latin, dev in names.items()
                 if re.fullmatch(r"[A-Za-z0-9 ]+", latin) and _DEVANAGARI.search(dev)]
        pairs.sort(key=lambda p: -len(p[0]))
        _name_patterns[key] = [
            (re.compile(r"(?<![A-Za-z])" + r"\s+".join(map(re.escape, name.split())) + r"(?![A-Za-z])", re.I), dev)
            for name, dev in pairs
        ]
    return _name_patterns[key]


def _number_words(raw: str, lang: Lang) -> str:
    value = raw.replace(",", "")
    if "." in value:
        whole_s, frac = value.split(".", 1)
        whole = int(whole_s or 0)
        if frac.rstrip("0") == "5":
            if whole == 0:
                return "अर्धा" if lang == "mr" else "आधा"
            return spoken.half_words(whole, lang)
        if not frac.strip("0"):
            return spoken.integer_words(whole, lang)
        point = " पूर्णांक " if lang == "mr" else " दशमलव "
        return spoken.integer_words(whole, lang) + point + " ".join(spoken.below_100(int(d), lang) for d in frac)
    if len(value) >= 10:  # phone-like: digit by digit
        return " ".join(spoken.below_100(int(d), lang) for d in value)
    return spoken.integer_words(int(value), lang)


_DAY_PARTS = ("सुबह", "दोपहर", "शाम", "रात", "सकाळी", "दुपारी", "संध्याकाळी", "रात्री")


def _clock(match: re.Match[str], minute: int, meridiem: str | None, lang: Lang) -> str:
    # "सुबह 10 AM": the sentence already says the time of day, so it is not said twice.
    if match.string[:match.start()].rstrip().endswith(_DAY_PARTS):
        meridiem = None
    return _clock_words(int(match.group(1)), minute, meridiem, lang)


def _clock_words(hour: int, minute: int, meridiem: str | None, lang: Lang) -> str:
    """"10 AM" -> "सुबह दस बजे", "2 PM" -> "दोपहर दो बजे", "6:30 PM" -> "शाम साढ़े छह बजे"."""
    if meridiem and 1 <= hour <= 12 and 0 <= minute < 60:
        h24 = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
        return spoken.time_words(time(h24, minute), lang)
    return _time_words(hour, minute, lang)


def _clock_digits(match: re.Match[str], minute: int | None, meridiem: str | None, lang: Lang) -> str:
    """"4 PM" -> "शाम 4 बजे", "6:30 PM" -> "शाम 6:30 बजे", "10 AM" -> "सुबह 10 बजे" (digits kept)."""
    hour = int(match.group(1))
    clock = f"{hour}:{minute:02d}" if minute else str(hour)
    suffix = "वाजता" if lang == "mr" else "बजे"
    if not meridiem or not 1 <= hour <= 12:
        return f"{clock} {suffix}"
    part = spoken._day_part(hour % 12 + (12 if meridiem.lower() == "pm" else 0), lang)
    if match.string[:match.start()].rstrip().endswith(_DAY_PARTS):
        return f"{clock} {suffix}"
    return f"{part} {clock} {suffix}"


def _digits_speech(out: str, lang: Lang) -> str:
    """Numbers stay digits (chosen by ear for Rumik: "76.5 लाख", "640 sq ft", "शाम 4 बजे"); only the
    units, times and symbols around them are put in Hindi/Marathi."""
    unit = lambda word: _WORDS[word.lower()][0 if lang == "mr" else 1]  # noqa: E731
    out = _RANGE_RE.sub(" ते " if lang == "mr" else " से ", out)
    out = _MONEY_RE.sub(lambda m: _money_digits(m, lang), out)
    out = _PERCENT_RE.sub(lambda m: f"{m.group(1)} {'टक्के' if lang == 'mr' else 'प्रतिशत'}", out)
    out = _TIME_RE.sub(lambda m: _clock_digits(m, int(m.group(2)), m.group(3), lang), out)
    out = _HOUR_RE.sub(lambda m: _clock_digits(m, 0, m.group(2), lang), out)
    out = _UNIT_RE.sub(lambda m: unit(m.group(1)), out)
    out = re.sub(r"(बजे|वाजता)\s+को(?=[\s,।?!]|$)", r"\1", out)  # "Sunday 4 PM को" -> "शाम 4 बजे"
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def _money_digits(match: re.Match[str], lang: Lang) -> str:
    """"₹85,00,000" -> "85 लाख"; "₹1,20,00,000" -> "1.2 करोड़"; "Rs 85 lakh" -> "85 लाख"."""
    raw, unit_word = match.group(1), (match.group(2) or "").strip()
    value = float(raw.replace(",", ""))
    lakh, crore = _WORDS["lakh"][0 if lang == "mr" else 1], _WORDS["crore"][0 if lang == "mr" else 1]
    if unit_word:
        return f"{_trim_number(value)} {lakh if unit_word.lower().startswith(('lakh', 'लाख')) else crore}"
    if value >= 10_000_000:
        return f"{_trim_number(value / 10_000_000)} {crore}"
    if value >= 100_000:
        return f"{_trim_number(value / 100_000)} {lakh}"
    return f"{_trim_number(value)} {'रुपये' if lang == 'hi' else 'रुपये'}"


def _trim_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _time_words(hour: int, minute: int, lang: Lang) -> str:
    h = spoken.integer_words(hour, lang)
    if lang == "mr":
        return f"{h} वाजता" if minute == 0 else f"{h} वाजून {spoken.integer_words(minute, lang)} मिनिटांनी"
    return f"{h} बजे" if minute == 0 else f"{h} बजकर {spoken.integer_words(minute, lang)} मिनट"


def _latin_word(word: str, lang: Lang) -> str:
    low = word.lower()
    if low in _WORDS:
        return _WORDS[low][0 if lang == "mr" else 1]
    if (word.isupper() and len(word) <= 5) or len(word) == 1:
        letters = {**_LETTERS, **(_HI_LETTERS if lang == "hi" else {})}
        return " ".join(letters[c] for c in low)
    return word


def _digit_words(digits: str, lang: Lang) -> str:
    return " ".join(spoken.below_100(int(d), lang) for d in digits if d.isdigit())


def _code_words(code: str, lang: Lang) -> str:
    letters = {**_LETTERS, **(_HI_LETTERS if lang == "hi" else {})}
    return " ".join(spoken.below_100(int(c), lang) if c.isdigit() else letters[c.lower()] for c in code)


def _phone(match: re.Match[str], lang: Lang) -> str:
    raw = match.group(0)
    if sum(c.isdigit() for c in raw) < 10:
        return raw
    return ", ".join(_digit_words(group, lang) for group in re.split(r"[ -]", raw))


def _money(match: re.Match[str], lang: Lang) -> str:
    unit = (match.group(2) or "").strip().lower()
    unit_word = {"lakh": "लाख", "lakhs": "लाख", "crore": "कोटी" if lang == "mr" else "करोड़",
                 "crores": "कोटी" if lang == "mr" else "करोड़"}.get(unit, unit)
    amount = _number_words(match.group(1), lang)
    return " ".join(part for part in (amount, unit_word, "रुपये") if part)


def to_devanagari_speech(text: str, lang: Lang, names: "Mapping[str, str] | None" = None,
                         english_words: bool = True, number_words: bool = True) -> str:
    """english_words=False keeps English words (and project names) in Latin letters and converts only
    numbers, times and lakh/crore: Rumik reads Hinglish best that way (measured: Hindi script with
    English words in Latin 30/34 key words recognised, everything in Devanagari 28/34)."""
    if lang not in ("mr", "hi") or not text:
        return text
    out = text.translate(_DEV_DIGITS)
    # An all-English sentence is left to the TTS. A Hinglish one ("Sunday 10 AM, Monday 2 PM, या
    # Tuesday 6 PM", "1 crore 5 lakh से 1 crore 15 lakh") still has its numbers, times and lakh/crore
    # spoken in Hindi/Marathi words, computed here rather than by the model (which wrote 76.5 lakh as
    # "सात सौ पैंसठ" and 6 PM as "पाँच बजे"). Its English words are left as they are.
    if not _DEVANAGARI.search(out):
        return out
    english_heavy = (len(_DEVANAGARI.findall(out)) < len(_LATIN_RE.sub("", out)) * 0.2) or not english_words
    if names and english_words:
        for pattern, dev in _names(names):
            out = pattern.sub(dev, out)
    if not number_words:
        return _digits_speech(out, lang)
    out = _ROUND_THE_CLOCK_RE.sub("चोवीस तास" if lang == "mr" else "चौबीसों घंटे", out)
    out = _CODE_RE.sub(lambda m: _code_words(m.group(0), lang), out)
    out = _PHONE_RE.sub(lambda m: _phone(m, lang), out)
    # After phone numbers: 1800-419-2266 is not a range.
    out = _RANGE_RE.sub(" ते " if lang == "mr" else " से ", out)
    out = _MONEY_RE.sub(lambda m: _money(m, lang), out)
    out = _DIGITS_RE.sub(lambda m: _digit_words(m.group(0), lang), out)
    out = _PERCENT_RE.sub(lambda m: f"{_number_words(m.group(1), lang)} {'टक्के' if lang == 'mr' else 'प्रतिशत'}", out)
    out = _TIME_RE.sub(lambda m: _clock(m, int(m.group(2)), m.group(3), lang), out)
    out = _HOUR_RE.sub(lambda m: _clock(m, 0, m.group(2), lang), out)
    out = _NUMBER_RE.sub(lambda m: _number_words(m.group(0), lang), out)
    if english_heavy:
        out = _UNIT_RE.sub(lambda m: _WORDS[m.group(1).lower()][0 if lang == "mr" else 1], out)
    else:
        out = _LATIN_RE.sub(lambda m: _latin_word(m.group(0), lang), out)
    out = _SPOKEN_RANGE_RE.sub(" ते " if lang == "mr" else " से ", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()
