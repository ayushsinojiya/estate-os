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
