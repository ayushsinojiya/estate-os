"""Keeps identity numbers out of logs and stored transcripts.

Transcripts outlive the call, so this is the last point at which a number the caller should never
have read out can be kept out of storage. The engine only knows that long digit runs are risky;
the domain says which words make shorter runs risky too (see DomainPlugin.is_sensitive).
"""

from __future__ import annotations

import re
from typing import Callable

# A long run of digits is an identity or account-style number being read out. Phone numbers are
# ten digits and are caught too, which is intended: the caller's number is already on the record.
_LONG_DIGITS = re.compile(r"\d(?:[\s-]?\d){8,}")
# Once the domain says the turn names something sensitive, far shorter runs matter as well.
_SHORT_DIGITS = re.compile(r"\d(?:[\s-]?\d){2,}")


def redact(text: str, sensitive: Callable[[str], bool] | None = None) -> str:
    if not text:
        return text
    pattern = _SHORT_DIGITS if sensitive is not None and sensitive(text) else _LONG_DIGITS
    return pattern.sub("[redacted]", text)
