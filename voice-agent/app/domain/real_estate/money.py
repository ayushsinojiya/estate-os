"""Rupees as they are said on the phone, and rupee amounts found in what the model wrote."""

from __future__ import annotations

import re

_DEV_DIGITS = str.maketrans("०१२३४५६७८९૦૧૨૩૪૫૬૭૮૯", "01234567890123456789")
LAKH, CRORE = 100_000, 10_000_000


def _trim(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def spoken_inr(amount: int | float) -> str:
    """₹1,20,00,000 → "1 crore 20 lakh"; ₹85,00,000 → "85 lakh"; ₹2,50,000 → "2.5 lakh"."""
    amount = int(round(amount))
    if amount >= CRORE:
        crore, rest = divmod(amount, CRORE)
        lakh = int(round(rest / LAKH))
        if lakh == 100:
            crore, lakh = crore + 1, 0
        return f"{crore} crore" + (f" {lakh} lakh" if lakh else "")
    if amount >= LAKH:
        return f"{_trim(amount / LAKH)} lakh" if amount % (LAKH // 10) == 0 else f"{_trim(round(amount / LAKH, 1))} lakh"
    return f"{amount:,} rupees"


def spoken_range(low: int | float, high: int | float) -> str:
    a, b = spoken_inr(low), spoken_inr(high)
    return a if a == b else f"{a} to {b}"


_CRORE = r"(?:crores?|cr\b|करोड़|करोड|कोटी|કરોડ)"
_LAKH = r"(?:lakhs?|lacs?|लाख|લાખ)"
_THOUSAND = r"(?:thousand|k\b|हज़ार|हजार|હજાર)"
_NUM = r"\d+(?:\.\d+)?"
_PATTERNS = [
    (re.compile(rf"({_NUM})\s*{_CRORE}(?:\s*(?:and\s+)?({_NUM})\s*{_LAKH})?", re.I),
     lambda m: float(m.group(1)) * CRORE + (float(m.group(2)) * LAKH if m.group(2) else 0)),
    (re.compile(rf"({_NUM})\s*{_LAKH}", re.I), lambda m: float(m.group(1)) * LAKH),
    (re.compile(rf"({_NUM})\s*{_THOUSAND}", re.I), lambda m: float(m.group(1)) * 1000),
    (re.compile(r"(?:₹|\brs\.?|\binr\b|rupees?\s)\s*(\d[\d,]*(?:\.\d+)?)", re.I),
     lambda m: float(m.group(1).replace(",", ""))),
    (re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:rupees|रुपये|रुपए|रुपया|रुपयांना|રૂપિયા)", re.I),
     lambda m: float(m.group(1).replace(",", ""))),
]


def amounts_in(text: str) -> list[int]:
    """Every rupee amount written in the text, in whole rupees. Bare numbers are not money."""
    text = (text or "").translate(_DEV_DIGITS)
    found: list[int] = []
    taken: list[tuple[int, int]] = []
    for pattern, value in _PATTERNS:
        for match in pattern.finditer(text):
            if any(start < match.end() and match.start() < end for start, end in taken):
                continue
            try:
                found.append(int(round(value(match))))
            except ValueError:
                continue
            taken.append((match.start(), match.end()))
    return found


# ---- the caller's own figures, as they are spoken ("साठ से अस्सी लाख", "sixty to eighty lakh")

_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
             "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_FRACTIONS = {"डेढ़": 1.5, "डेढ": 1.5, "दीड": 1.5, "ढाई": 2.5, "अडीच": 2.5}
_HALF_PLUS = ("साढ़े", "साढे", "साडे", "साडेत")


def _word_values() -> dict[str, int]:
    from app.lang.spoken import HI_0_99, MR_0_99
    values: dict[str, int] = {}
    for table in (HI_0_99, MR_0_99):
        for n, word in enumerate(table):
            values.setdefault(word, n)
    for n, word in enumerate(_EN_UNITS):
        values[word] = n
    for t, tens in enumerate(_EN_TENS):
        if tens:
            values[tens] = t * 10
    # Common alternative spellings heard from speech recognition.
    values.update({"पांच": 5, "छः": 6, "छे": 6, "सौ": 100, "hundred": 100})
    return values


_WORDS: dict[str, int] | None = None


def words_to_digits(text: str) -> str:
    """Number words to digits: "साठ से अस्सी लाख" -> "60 से 80 लाख", "seventy six" -> "76",
    "डेढ़ करोड़" -> "1.5 करोड़", "साढ़े आठ लाख" -> "8.5 लाख". Other words are left alone."""
    global _WORDS
    if _WORDS is None:
        _WORDS = _word_values()
    out: list[str] = []
    half = False
    for token in (text or "").split():
        word = token.strip(".,?!।").lower()
        if word in _HALF_PLUS:
            half = True
            continue
        if word in _FRACTIONS:
            out.append(_trim(_FRACTIONS[word]))
        elif word in _WORDS:
            value = _WORDS[word]
            # "seventy six": an English tens word followed by a unit word is one number.
            if out and value < 10 and word in _EN_UNITS and out[-1].isdigit() and int(out[-1]) % 10 == 0 \
                    and 20 <= int(out[-1]) <= 90:
                value += int(out.pop())
            out.append(_trim(value + 0.5) if half else str(value))
        else:
            out.append(token)
        half = False
    return " ".join(out)


# One stray word is allowed between the two figures: speech recognition keeps stumbles ("60 से अठ्ठे 80 लाख").
_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:से|ते|to|-|–|or|या)\s*(?:[^\d\s]+\s+)?(\d+(?:\.\d+)?)\s*"
                    r"(lakhs?|लाख|crores?|करोड़|कोटी)", re.I)


def caller_amounts(text: str) -> list[int]:
    """Every amount the caller said, words included, with both ends of a range ("60 से 80 लाख")."""
    digits = words_to_digits(text)
    found = amounts_in(digits)
    for low, _high, unit in _RANGE.findall(digits.translate(_DEV_DIGITS)):
        found.extend(amounts_in(f"{low} {unit}"))
    return found
