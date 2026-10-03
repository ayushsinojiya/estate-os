"""Short, query-focused content for the live-call path.

A chunk can hold ~450 tokens; the voice model needs only the part that answers. Cutting the head
of the chunk loses answers that sit further down a packed section, so instead the sentences (or
table rows) that share the most words with the query are kept, in document order, within the
character budget. A table keeps its header so the kept rows still say what their columns are.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[0-9a-zऀ-ॿ઀-૿]+", re.I)
_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 1}


def _overlap(query: set[str], text: str) -> float:
    words = _words(text)
    # Prefix match catches "charge"/"charges" and "floor"/"flooring".
    hits = sum(1 for q in query if any(w.startswith(q[:5]) for w in words))
    return hits / (1 + len(query))


def focus(content: str, query: str, limit: int, chunk_type: str = "TEXT") -> str:
    if len(content) <= limit:
        return content
    q = _words(query)
    lines = content.splitlines()
    if chunk_type == "TABLE" and len(lines) > 2:
        head, rows = lines[:2], lines[2:]
        ranked = sorted(range(len(rows)), key=lambda i: (-_overlap(q, rows[i]), i))
        keep, size = [], sum(len(h) + 1 for h in head)
        for i in ranked:
            if size + len(rows[i]) + 1 > limit:
                continue
            keep.append(i)
            size += len(rows[i]) + 1
        return "\n".join(head + [rows[i] for i in sorted(keep)])
    pieces = [p.strip() for p in _SPLIT.split(content) if p and p.strip()]
    ranked = sorted(range(len(pieces)), key=lambda i: (-_overlap(q, pieces[i]), i))
    keep, size = [], 0
    for i in ranked:
        if size + len(pieces[i]) + 1 > limit:
            continue
        keep.append(i)
        size += len(pieces[i]) + 1
    if not keep:
        return content[:limit]
    return " ".join(pieces[i] for i in sorted(keep))
