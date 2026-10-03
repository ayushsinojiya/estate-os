"""IST time: the TRAI calling window and spoken day/time phrases ("kal shaam", "parva sakali")."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def within_calling_hours(at: datetime, start: str = "09:00", end: str = "21:00") -> bool:
    local = at.astimezone(IST).time()
    return parse_hhmm(start) <= local < parse_hhmm(end)


def clamp_to_calling_hours(at: datetime, start: str = "09:00", end: str = "21:00",
                           resume: str = "09:30") -> datetime:
    """`at` itself inside 09:00–21:00 IST, otherwise the next 09:30 (same rule as the CRM)."""
    local = at.astimezone(IST)
    if within_calling_hours(local, start, end):
        return local
    day = local.date() if local.time() < parse_hhmm(start) else local.date() + timedelta(days=1)
    return datetime.combine(day, parse_hhmm(resume), IST)


_DAY_WORDS = [
    (0, ["today", "aaj", "aj", "आज", "આજે", "aaje"]),
    (2, ["day after tomorrow", "parso", "parson", "परसों", "परवा", "parva", "પરમદિવસે", "parmdivase"]),
    (1, ["tomorrow", "kal", "कल", "उद्या", "udya", "udyaa", "આવતીકાલે", "kaale", "avtikale"]),
]
_WEEKDAYS = [
    ["monday", "somvar", "सोमवार", "સોમવાર"], ["tuesday", "mangalvar", "मंगलवार", "मंगळवार", "મંગળવાર"],
    ["wednesday", "budhvar", "बुधवार", "બુધવાર"], ["thursday", "guruvar", "गुरुवार", "ગુરુવાર"],
    ["friday", "shukravar", "शुक्रवार", "શુક્રવાર"], ["saturday", "shanivar", "शनिवार", "શનિવાર"],
    ["sunday", "ravivar", "रविवार", "રવિવાર", "itvaar", "इतवार"],
]
_PARTS = [
    (time(10, 0), ["morning", "subah", "सुबह", "सकाळी", "sakali", "सकाळ", "સવારે", "savare"]),
    (time(14, 0), ["afternoon", "dopahar", "dopehar", "दोपहर", "दुपारी", "dupari", "બપોરે", "bapore"]),
    (time(18, 0), ["evening", "shaam", "sham", "शाम", "संध्याकाळी", "sandhyakali", "સાંજે", "saanje", "sanje"]),
    (time(20, 0), ["night", "raat", "रात", "रात्री", "ratri", "રાત્રે", "ratre"]),
]
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje|बजे|वाजता|vajta|વાગ્યે|vagye)?\b", re.I)
_IN_HOURS = re.compile(r"\b(?:in\s+)?(\d{1,2})\s*(?:hours?|ghante|घंटे|तास|tas|કલાક)\s*(?:baad|बाद|नंतर|nantar|પછી|later)?", re.I)


def parse_when(text: str | None, now: datetime | None = None) -> datetime | None:
    """A callback time from what the caller said, or None when nothing usable was said."""
    if not text:
        return None
    now = (now or now_ist()).astimezone(IST)
    raw = text.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)
    except ValueError:
        pass
    lowered = raw.lower()
    if (m := _IN_HOURS.search(lowered)):
        return now + timedelta(hours=int(m.group(1)))
    day: date | None = None
    for offset, words in _DAY_WORDS:
        if any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", lowered) for w in words):
            day = now.date() + timedelta(days=offset)
            break
    if day is None:
        for index, words in enumerate(_WEEKDAYS):
            if any(w in lowered for w in words):
                ahead = (index - now.weekday()) % 7 or 7
                day = now.date() + timedelta(days=ahead)
                break
    at: time | None = None
    for part, words in _PARTS:
        if any(w in lowered for w in words):
            at = part
            break
    if (m := _CLOCK.search(lowered)) and (m.group(3) or at is not None or day is not None):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        suffix = (m.group(3) or "").lower()
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif not suffix or suffix not in ("am",):
            if at is not None and at.hour >= 14 and hour < 12:
                hour += 12
            elif at is None and hour < 8:
                hour += 12  # "5 baje" on a sales call means 5 PM
        if 0 <= hour < 24 and 0 <= minute < 60:
            at = time(hour, minute)
    if day is None and at is None:
        return None
    if day is None:
        day = now.date() if datetime.combine(now.date(), at, IST) > now else now.date() + timedelta(days=1)
    return datetime.combine(day, at or time(11, 0), IST)


def as_utc_iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def spoken_time(at: datetime) -> str:
    """"Saturday 6 PM", "Saturday 6:30 PM", in IST."""
    local = at.astimezone(IST)
    hour = local.hour % 12 or 12
    minutes = "" if local.minute == 0 else f":{local.minute:02d}"
    return f"{local.strftime('%A')} {hour}{minutes} {'AM' if local.hour < 12 else 'PM'}"
