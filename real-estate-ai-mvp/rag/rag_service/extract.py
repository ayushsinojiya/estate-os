"""Structured facts from a parsed document, for the CRM's Projects & inventory: the projects it
describes and the listings (units) it offers, with exact prices.

Tables of listings are read in code, row by row, once their columns are known (by name, or by asking
the model which column is which), so their prices are exact. The rest of a page is read by the model,
which copies every value verbatim; figures are then parsed here and a listing is kept only if its price
appears on the page. The model also names the project a page's price table belongs to.
The model never does arithmetic, and a price it did not copy from the page never reaches the CRM.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# The model reads at most this much text at a time; longer text is split at headings.
MODEL_PAGE_CHARS = 12_000

CITIES = ("Pune", "Mumbai", "Navi Mumbai", "Thane", "Ahmedabad", "Bengaluru", "Bangalore", "Hyderabad",
          "Chennai", "Delhi", "New Delhi", "Gurugram", "Gurgaon", "Noida", "Kolkata", "Nagpur", "Nashik",
          "Surat", "Vadodara", "Jaipur", "Indore", "Lucknow", "Kochi", "Goa")

PAGE_PROMPT = """You read one page of a real-estate document and list what it offers, as JSON.

Copy every value exactly as printed, character for character: prices with their units ("₹79.2 lakh",
"₹1.05 crore", "₹22,147/month"), areas with their units ("829 sq ft"). Never calculate, convert,
round, translate, guess or fill in a value that is not printed on this page. Use null when a value
is not printed. If the page offers nothing for sale or rent (a guide, terms, a map), return empty lists.

Return exactly:
{"projects": [{"name": str, "developer": str|null, "location": str|null, "reraId": str|null,
               "possession": str|null, "amenities": [str], "description": str|null}],
 "listings": [{"projectName": str|null, "ref": str|null, "transaction": "SALE"|"RENT"|null,
               "propertyType": str|null, "configuration": str|null, "area": str|null,
               "price": str|null, "locality": str|null, "furnishing": str|null, "facing": str|null,
               "parking": str|null, "availability": str|null, "amenities": [str], "notes": str|null}]}

A project is a named development, building or society; a locality on its own is not a project.
Each row of a configuration or price table is one listing, with the project it belongs to.
"description" is one short sentence taken from the page."""

MAPPING_PROMPT = """These are the first rows of a table from a real-estate document. Say which column
holds each field, using the column names exactly as given, or null when no column holds it.

Return exactly:
{"isListingTable": bool, "columns": {"ref": str|null, "projectName": str|null, "transaction": str|null,
 "locality": str|null, "propertyType": str|null, "configuration": str|null, "area": str|null,
 "price": str|null, "furnishing": str|null, "facing": str|null, "parking": str|null,
 "availability": str|null, "amenities": str|null, "notes": str|null}}

"isListingTable" is true only when each row is a property, unit or configuration with a price."""


class ExtractionModel(Protocol):
    name: str

    async def complete(self, system: str, user: str) -> dict[str, Any]: ...


# ---------------------------------------------------------------- figures


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _squash(text: str) -> str:
    """For checking that a copied value is on the page: no spaces, commas or rupee signs, lower case."""
    return re.sub(r"[\s,₹■]|rs\.?|inr", "", (text or "").lower())


def parse_price(text: Any) -> tuple[int | None, bool]:
    """'₹79.2 lakh' -> (7920000, False); '₹22,147/month' -> (22147, True); '₹1.05 crore' -> 10500000."""
    t = _clean(text).lower().replace(",", "")
    if not t:
        return None, False
    monthly = bool(re.search(r"/\s*(month|mo\b|pm\b)|per\s*month|monthly|p\.\s*m\.", t))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(crores?|cr\b|lakhs?|lacs?|l\b|k\b|thousand)?", t)
    if not m:
        return None, monthly
    number, unit = float(m.group(1)), (m.group(2) or "")
    if unit.startswith("cr"):
        number *= 10_000_000
    elif unit.startswith(("lakh", "lac")) or unit == "l":
        number *= 100_000
    elif unit in ("k", "thousand"):
        number *= 1_000
    return (round(number) if number > 0 else None), monthly


def parse_area(text: Any) -> float | None:
    """Square feet: '829 sq ft' -> 829; '120 sq m' -> 1291.7; '2 acres' -> 87120."""
    t = _clean(text).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    n = float(m.group(1))
    if re.search(r"sq\.?\s*m\b|sqm|square met", t):
        n *= 10.7639
    elif "acre" in t:
        n *= 43_560
    elif "guntha" in t:
        n *= 1_089
    elif "hectare" in t:
        n *= 107_639
    return round(n, 2) if n > 0 else None


def parse_bhk(*texts: Any) -> int:
    for text in texts:
        m = re.search(r"(\d+)\s*(?:\.\s*5\s*)?bhk", _clean(text).lower())
        if m:
            return min(int(m.group(1)), 20)
    return 0  # 1 RK, studio, office, shop, plot: no bedroom count


def parse_transaction(value: Any, monthly: bool) -> str:
    t = _clean(value).lower()
    if monthly or re.search(r"\b(rent|rental|lease|leave and licen[cs]e)\b", t):
        return "RENT"
    return "SALE"


def find_city(*texts: str) -> str | None:
    counts: dict[str, int] = {}
    for text in texts:
        for city in CITIES:
            n = len(re.findall(rf"\b{re.escape(city)}\b", text or "", re.I))
            if n:
                counts[city] = counts.get(city, 0) + n
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return {"Bangalore": "Bengaluru", "Gurgaon": "Gurugram"}.get(best, best)


_PRICE_HINT = re.compile(r"₹|■|\brs\.?\s*\d|\binr\b|\blakh|\blac\b|\bcrore|\bcr\b|/\s*month|per\s+month", re.I)


def offers_something(markdown: str) -> bool:
    """Only pages that quote a price can add inventory; the rest are not sent to the model."""
    return bool(_PRICE_HINT.search(markdown or ""))


# ---------------------------------------------------------------- tables


def tables(markdown: str) -> list[tuple[list[str], list[list[str]], int, int]]:
    """Markdown tables on a page: (header, rows, first line, last line)."""
    lines = (markdown or "").splitlines()
    found, i = [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            start = i
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            found.append((header, rows, start, i - 1))
        else:
            i += 1
    return found


_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ref": ("property id", "listing id", "unit id", "unit no", "unit number", "flat no", "ref", "reference"),
    "projectName": ("project name", "project", "building", "society", "development"),
    "transaction": ("transaction", "listing type", "deal type", "purpose", "sale rent"),
    "locality": ("locality", "location", "neighbourhood", "neighborhood", "micro market", "sector"),
    "propertyType": ("property type", "category", "asset type"),
    "configuration": ("configuration", "config", "bhk", "unit type", "type"),
    "area": ("carpet or plot sqft", "carpet area", "carpet", "area sqft", "area", "size", "plot area",
             "built up area", "super area", "sq ft", "sqft"),
    "price": ("price", "asking price", "starting price", "price inr", "rent", "cost", "amount"),
    "furnishing": ("furnishing", "furnished"),
    "facing": ("facing",),
    "parking": ("parking",),
    "availability": ("availability", "possession", "available from"),
    "amenities": ("amenities",),
    "notes": ("notes", "remarks"),
}


def _norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def map_columns(header: list[str]) -> dict[str, int]:
    """Field -> column index, by column name. Exact names win over partial ones."""
    names = [_norm_header(h) for h in header]
    taken: set[int] = set()
    mapping: dict[str, int] = {}
    for exact in (True, False):
        for field, words in _SYNONYMS.items():
            if field in mapping:
                continue
            for word in words:
                hit = next((i for i, n in enumerate(names) if i not in taken and
                            (n == word if exact else re.search(rf"\b{re.escape(word)}\b", n))), None)
                if hit is not None:
                    mapping[field] = hit
                    taken.add(hit)
                    break
    return mapping


def usable(mapping: dict[str, int]) -> bool:
    return "price" in mapping and bool({"ref", "configuration", "propertyType"} & set(mapping))


# ---------------------------------------------------------------- listings


def _listing(raw: dict[str, Any], page_no: int, *, page_text: str | None, warnings: list[str],
             default_city: str | None, from_model: bool) -> dict[str, Any] | None:
    price_text = _clean(raw.get("price"))
    price, monthly = parse_price(price_text)
    label = _clean(raw.get("ref")) or _clean(raw.get("configuration")) or _clean(raw.get("propertyType"))
    if price is None:
        return None
    if from_model and page_text is not None and _squash(price_text) not in _squash(page_text):
        warnings.append(f"page {page_no}: dropped {label or 'a listing'} — its price {price_text!r} is not on the page")
        return None
    area_text = _clean(raw.get("area"))
    if from_model and area_text and page_text is not None and _squash(area_text) not in _squash(page_text):
        area_text = ""  # an area the model did not copy from the page is left out, not guessed
    amenities = raw.get("amenities")
    if isinstance(amenities, str):
        amenities = [a.strip() for a in amenities.split(",") if a.strip()]
    return {
        "ref": _clean(raw.get("ref")) or None,
        "projectName": _clean(raw.get("projectName")) or None,
        "locality": _clean(raw.get("locality")) or None,
        "city": default_city,
        "transaction": parse_transaction(raw.get("transaction"), monthly),
        "propertyType": _clean(raw.get("propertyType")) or None,
        "configuration": _clean(raw.get("configuration")) or None,
        "bhk": parse_bhk(raw.get("configuration"), raw.get("propertyType")),
        "areaSqft": parse_area(area_text),
        "priceInr": price,
        "priceText": price_text,
        "furnishing": _clean(raw.get("furnishing")) or None,
        "facing": _clean(raw.get("facing")) or None,
        "parking": _clean(raw.get("parking")) or None,
        "availability": _clean(raw.get("availability")) or None,
        "amenities": [_clean(a) for a in (amenities or []) if _clean(a)][:40],
        "notes": _clean(raw.get("notes"))[:500] or None,
        "page": page_no,
    }


def _rows_to_listings(header: list[str], rows: list[list[str]], mapping: dict[str, int], page_no: int,
                      warnings: list[str], city: str | None) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        raw = {field: (row[i] if i < len(row) else "") for field, i in mapping.items()}
        item = _listing(raw, page_no, page_text=None, warnings=warnings, default_city=city, from_model=False)
        if item:
            out.append(item)
    return out


async def _model_mapping(model: ExtractionModel, header: list[str], rows: list[list[str]]) -> dict[str, int]:
    sample = "\n".join(" | ".join(r) for r in [header] + rows[:3])
    reply = await model.complete(MAPPING_PROMPT, sample)
    if not reply.get("isListingTable"):
        return {}
    names = {h: i for i, h in enumerate(header)}
    return {field: names[col] for field, col in (reply.get("columns") or {}).items() if col in names}


async def extract(pages: list[tuple[int, str]], file_name: str, model: ExtractionModel | None) -> dict[str, Any]:
    """Projects and listings in a document (pages are (page_no, markdown))."""
    warnings: list[str] = []
    calls = 0
    city = find_city(re.sub(r"[_\-.]+", " ", file_name), *(md[:3000] for _, md in pages[:3]))
    projects: dict[str, dict[str, Any]] = {}
    listings: list[dict[str, Any]] = []

    for page_no, markdown in pages:
        if not offers_something(markdown):
            continue
        rest = markdown
        page_rows: list[dict[str, Any]] = []
        for header, rows, first, last in reversed(tables(markdown)):
            mapping = map_columns(header)
            # A two-row key/value card ("Price | ₹79 lakh | Area | 829 sq ft") is left to the page read.
            if not usable(mapping) and model is not None and len(rows) >= 3:
                calls += 1
                mapping = await _model_mapping(model, header, rows)
            if not usable(mapping):
                continue
            page_rows.extend(_rows_to_listings(header, rows, mapping, page_no, warnings, city))
            lines = rest.splitlines()
            rest = "\n".join(lines[:first] + lines[last + 1:])
        listings.extend(page_rows)
        named_here: list[str] = []
        # The model reads what is left of the page: text that quotes prices, or text around a price
        # table that may name its project (not a bare sheet heading).
        if model is None or not offers_something(rest) and not (page_rows and len(rest.strip()) > 40):
            _assign_project(page_rows, named_here, projects)
            continue
        for part in _parts(rest, MODEL_PAGE_CHARS):
            known = ", ".join(projects) or "none yet"
            calls += 1
            reply = await model.complete(
                PAGE_PROMPT, f"Document: {file_name}\nProjects named on earlier pages: {known}\n"
                             f"Page {page_no}:\n\n{part}")
            for p in reply.get("projects") or []:
                name = _clean(p.get("name"))
                if not name or len(name) > 200:
                    continue
                entry = projects.setdefault(name, {"name": name})
                if name not in named_here:
                    named_here.append(name)
                for key in ("developer", "location", "reraId", "possession", "description"):
                    value = _clean(p.get(key))
                    if value and not entry.get(key):
                        entry[key] = value[:500]
                entry["amenities"] = sorted({*entry.get("amenities", []),
                                             *(_clean(a) for a in p.get("amenities") or [] if _clean(a))})[:60]
            for raw in reply.get("listings") or []:
                if not isinstance(raw, dict):
                    continue
                item = _listing(raw, page_no, page_text=part, warnings=warnings, default_city=city, from_model=True)
                if item:
                    listings.append(item)
        _assign_project(page_rows, named_here, projects)

    for project in projects.values():
        project["city"] = find_city(project.get("location") or "") or city
    return {"schema": SCHEMA_VERSION, "city": city, "projects": list(projects.values()),
            "listings": _dedupe(listings), "warnings": warnings[:50], "modelCalls": calls,
            "model": getattr(model, "name", None)}


def _assign_project(rows: list[dict[str, Any]], named_here: list[str], projects: dict[str, Any]) -> None:
    """Rows of a price table with no project or locality column belong to the project the page (or,
    failing that, the document) is about, when there is exactly one."""
    owner = named_here[0] if len(named_here) == 1 else (next(iter(projects)) if len(projects) == 1 else None)
    if owner is None:
        return
    for row in rows:
        if not row["projectName"] and not row["locality"]:
            row["projectName"] = owner


def _parts(text: str, limit: int) -> list[str]:
    """Split at headings (then lines) so no part is longer than the limit."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for block in re.split(r"(?m)^(?=#{1,3} )", text):
        while len(block) > limit:
            cut = block.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(block[:cut])
            block = block[cut:]
        if len(current) + len(block) > limit and current:
            parts.append(current)
            current = ""
        current += block
    if current.strip():
        parts.append(current)
    return parts


def _dedupe(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for item in listings:
        key = ("ref", item["ref"].lower()) if item["ref"] else (
            "row", (item["projectName"] or "").lower(), (item["configuration"] or "").lower(),
            item["priceInr"], item["areaSqft"])
        seen.setdefault(key, item)
    return list(seen.values())
