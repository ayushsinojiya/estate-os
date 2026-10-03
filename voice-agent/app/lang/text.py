"""Text normalisation shared by the resolver, classifiers and scorers."""

from __future__ import annotations

import re
import unicodedata

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _strip_latin_diacritics(text: str) -> str:
    # Only Latin characters are decomposed: decomposing Devanagari would split nukta letters.
    out = []
    for ch in text:
        if ord(ch) < 0x0250:
            decomposed = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
        else:
            out.append(ch)
    return "".join(out)


def normalize_text(text: str) -> str:
    """Lowercase, ASCII digits, punctuation to spaces (keeps ':' '/' and decimal points)."""
    text = unicodedata.normalize("NFC", text).translate(_DEVANAGARI_DIGITS)
    text = _strip_latin_diacritics(text).lower()
    chars: list[str] = []
    for i, ch in enumerate(text):
        category = unicodedata.category(ch)
        if category.startswith("P") or category.startswith("S"):
            if ch in ":/":
                chars.append(ch)
            elif ch == "." and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
                chars.append(ch)
            else:
                chars.append(" ")
        else:
            chars.append(ch)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


def devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)


def gujarati_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "\u0a80" <= c <= "\u0aff") / len(letters)
