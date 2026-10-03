"""Token estimates for chunk sizing and cost accounting.

An exact tokenizer (tiktoken) downloads its vocabulary on first use, which a sealed container or
an offline test run cannot do. Chunk sizing only needs to be roughly right, so this estimates from
UTF-8 length: about four bytes per token for Latin text, and Devanagari/Gujarati (three bytes per
character, roughly one token per one to two characters) land close to the real count too.
"""

from __future__ import annotations

import math


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))
