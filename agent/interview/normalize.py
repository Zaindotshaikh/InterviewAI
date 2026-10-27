"""Validate and normalise screening values that came out of noisy speech-to-text.

Speech is a bad channel for numbers. Everything the analyst extracts is re-validated here so a mis-heard phone
number or an impossible height is asked again instead of being silently stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

_DIGITS = re.compile(r"\d+")

# Words that are not a city. "उन्हें location." is a failed hearing, not a place.
_CITY_NOISE = {
    "location", "city", "place", "the", "a", "an", "my", "is", "in", "at", "for",
    "to", "of", "and", "work", "working", "apply", "applying", "hai", "hoon", "ji",
    "mein", "me", "wala", "wali", "शहर", "उन्हें", "उन्हे", "उन्होंने", "उनका",
    "उनकी", "उनके", "unhe", "unka", "unki", "unke", "में", "का", "की", "के", "है",
    "हूँ", "जी", "लोकेशन", "लोकैशन", "location.", "यहाँ", "वहाँ", "वहा", "यहा",
}


@dataclass(frozen=True)
class Normalized:
    ok: bool
    value: Any = None
    reason: str = ""


def _fail(reason: str) -> Normalized:
    return Normalized(False, None, reason)


def normalize_phone(raw: Any) -> Normalized:
    """Keep the digits that were heard, including a short or not-yet-valid mobile.

    A 10-digit number starting 6-9 is a real mobile. Shorter hearings are still
    returned so the interviewer can read them back and reject them after a yes.
    """
    from interview.phone_speech import parse_spoken_phone, trunk_prefix

    digits = trunk_prefix(parse_spoken_phone(str(raw or "")))
    if not digits:
        return _fail("no digits heard")
    if len(digits) > 13:
        return _fail(f"heard {len(digits)} digits, need 10")
    return Normalized(True, digits)


def spoken_groups(phone: str) -> str:
    """9876543210 -> '9, 8, 7, 6, 5, 4, 3, 2, 1, 0'. One digit at a time, nothing added."""
    digits = "".join(_DIGITS.findall(str(phone or "")))
    return ", ".join(digits)


def plausible_city(raw: Any) -> tuple[bool, str]:
    """True when the text names a place. Failed hearings like 'उन्हें location.' are not."""
    text = " ".join(str(raw or "").replace("।", " ").replace(".", " ").split())
    words = [w.strip(".,।!?;:'\"") for w in text.split()]
    content = [w for w in words if w and w.casefold() not in _CITY_NOISE and w not in _CITY_NOISE]
    cleaned = " ".join(content)[:160]
    if len(cleaned) < 2:
        return False, ""
    return True, cleaned


def _feet_inches_to_cm(feet: int, inches: int) -> Normalized:
    if inches > 11:
        return _fail("inches must be below 12")
    if not 4 <= feet <= 7:
        return _fail("feet outside believable range")
    return _check_height(round((feet * 12 + inches) * 2.54))


def _parse_feet_inches(text: str) -> tuple[int, int] | None:
    """Return (feet, inches) when the text is a feet-inches height, else None."""
    raw = str(text or "").lower().replace("’", "'").replace("”", '"')
    if re.search(r"\bcm\b|सेंटीमीटर|सेमी", raw, re.IGNORECASE):
        return None
    m = re.search(r"(\d)\s*(?:'|ft|feet|foot|फुट|फीट)\s*(\d{1,2})?\s*(?:\"|in|inch|inches|इंच)?", raw)
    if m:
        feet, inches = int(m.group(1)), int(m.group(2) or 0)
        return (feet, inches) if inches <= 11 and 4 <= feet <= 7 else None
    m = re.search(r"\b([4-7])\s+(\d{1,2})\b(?:\s*(?:\"|in|inch|inches|इंच))?", raw)
    if m:
        feet, inches = int(m.group(1)), int(m.group(2))
        return (feet, inches) if inches <= 11 else None
    nums = re.findall(r"\d+(?:\.\d+)?", raw)
    if not nums:
        return None
    n = float(nums[0])
    if not (3.5 <= n <= 7.5):
        return None
    # Plain "162" is cm, not feet. Only treat decimals / short feet forms here.
    if n >= 8 and "." not in nums[0]:
        return None
    feet = int(n)
    frac = n - feet
    two_digit = round(frac * 100)
    one_digit = round(frac * 10)
    inches = two_digit if 10 <= two_digit <= 11 else one_digit
    if inches > 11 or not (4 <= feet <= 7):
        return None
    # Bare integer 5 alone is too ambiguous; need inches or an explicit unit (handled above).
    if frac == 0 and not re.search(r"(?:'|ft|feet|foot|फुट|फीट)", raw):
        return None
    return feet, inches


def height_said_in_feet(raw: Any) -> bool:
    return _parse_feet_inches(str(raw or "")) is not None


def spoken_height_phrase(raw: Any, height_cm: int | str) -> str:
    """Read-back phrase in the unit the candidate used. Slots stay stored as cm."""
    cm = int(height_cm)
    parsed = _parse_feet_inches(str(raw or ""))
    if parsed is not None:
        feet, inches = parsed
        if inches:
            return f"{feet} feet {inches} inches"
        return f"{feet} feet"
    return f"{cm} centimetres"


def normalize_height_cm(raw: Any) -> Normalized:
    text = str(raw or "").lower().replace("’", "'").replace("”", '"')
    feet_pair = _parse_feet_inches(text)
    if feet_pair is not None:
        return _feet_inches_to_cm(*feet_pair)
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return _fail("no number heard")
    n = float(nums[0])
    if "m" in text and "cm" not in text and 1.0 <= n <= 2.3:
        return _check_height(round(n * 100))
    return _check_height(round(n))


def _check_height(cm: int) -> Normalized:
    if not 120 <= cm <= 210:
        return _fail(f"{cm} cm is outside the believable range")
    return Normalized(True, cm)


_HEIGHT_UNIT = re.compile(
    r"\b(?:cm|cms|centimet(?:er|re)s?|height)\b|सेंटीमीटर|सेन्टीमीटर|सेमी|कद|ऊंचाई|ऊँचाई",
    re.IGNORECASE,
)
_WEIGHT_UNIT = re.compile(
    r"\b(?:kg|kgs|kilo|kilos|kilograms?|weight)\b|किलो|किलोग्राम|वजन",
    re.IGNORECASE,
)
_FEET_UNIT = re.compile(r"\b(?:feet|foot|ft)\b|फुट|फीट|'", re.IGNORECASE)
_BODY_SPLIT = re.compile(r"\b(?:and|aur)\b|और|,|।", re.IGNORECASE)


def _chunk_measure(chunk: str) -> tuple[str, int | None]:
    """('height'|'weight'|'', number) from one part of a sentence."""
    from interview.phone_speech import parse_spoken_phone

    text = chunk.strip()
    if not text:
        return "", None
    kind = "height" if _HEIGHT_UNIT.search(text) else "weight" if _WEIGHT_UNIT.search(text) else ""
    # Feet/inches with or without the word "feet" ("5 ft 11", bare "5 11")
    if _FEET_UNIT.search(text) or re.search(r"\b[4-7]\s+\d{1,2}\b", text):
        height = normalize_height_cm(text)
        if height.ok:
            return "height", int(height.value)
    spoken = parse_spoken_phone(text)
    if spoken.isdigit() and 1 <= len(spoken) <= 3:
        return kind, int(spoken)
    nums = re.findall(r"\d+", text)
    if len(nums) == 1:
        return kind, int(nums[0])
    return kind, None


def _near_kind(text: str, start: int, end: int) -> str:
    after = text[end : end + 18]
    before = text[max(0, start - 18) : start]
    if _HEIGHT_UNIT.search(after):
        return "height"
    if _WEIGHT_UNIT.search(after):
        return "weight"
    if _HEIGHT_UNIT.search(before):
        return "height"
    if _WEIGHT_UNIT.search(before):
        return "weight"
    return ""


def _assign_bare_body_numbers(
    bare: list[int],
    *,
    height: int | None,
    weight: int | None,
) -> tuple[int | None, int | None]:
    """Map bare numbers to height/weight. Order in the sentence does not matter."""
    unused = [n for n in bare if 30 <= n <= 210]
    if height is not None and weight is not None:
        return height, weight
    if height is None and weight is None and len(unused) >= 2:
        a, b = unused[0], unused[1]
        lo, hi = (a, b) if a <= b else (b, a)
        # Two numbers: larger is height when both look like cm, smaller is kg.
        if 120 <= hi <= 210 and 30 <= lo <= 200 and lo != hi:
            return hi, lo
    for number in unused:
        if height is None and 120 <= number <= 210:
            height = number
        elif weight is None and 30 <= number < 120:
            weight = number
        elif weight is None and height is not None and 30 <= number <= 200 and number != height:
            weight = number
        elif height is None and weight is not None and 120 <= number <= 210 and number != weight:
            height = number
    return height, weight


def parse_height_and_weight(text: str) -> tuple[int | None, int | None]:
    """Pull height in cm and weight in kg out of one answer.

    Handles cm/kg in either order, and feet-inches as '5 feet 11', '5\'11',
    bare '5 11', or '5.11'. Bare '70 165' still maps by size when no feet pattern.
    """
    raw = str(text or "")
    height: int | None = None
    weight: int | None = None
    bare: list[int] = []

    # Prefer an explicit feet-inches height before bare cm heuristics eat "5 11".
    feet_height = normalize_height_cm(raw)
    if feet_height.ok and (
        _FEET_UNIT.search(raw)
        or re.search(r"\b[4-7]\s+\d{1,2}\b", raw)
        or re.search(r"\b[4-7]\.\d{1,2}\b", raw)
    ):
        # Only trust solo normalize when the text looks like feet, not plain cm.
        if not re.search(r"\bcm\b|सेंटीमीटर|सेमी", raw, re.IGNORECASE):
            height = int(feet_height.value)

    for match in re.finditer(r"\d{2,3}", raw):
        number = int(match.group(0))
        kind = _near_kind(raw, match.start(), match.end())
        if kind == "height" and height is None and 120 <= number <= 210:
            height = number
        elif kind == "weight" and weight is None and 30 <= number <= 200:
            weight = number
        elif kind == "" and 30 <= number <= 210:
            # Skip digits that belong to a feet-inches pair already used as height.
            if height is not None and number <= 11:
                continue
            bare.append(number)
    if height is not None and weight is not None:
        return height, weight
    parts = [p for p in _BODY_SPLIT.split(raw) if p.strip()] or [raw]
    for part in parts:
        kind, number = _chunk_measure(part)
        if number is None:
            continue
        if kind == "height" and height is None and 120 <= number <= 210:
            height = number
        elif kind == "weight" and weight is None and 30 <= number <= 200:
            weight = number
        elif kind == "" and number not in bare and number >= 30:
            bare.append(number)
    return _assign_bare_body_numbers(bare, height=height, weight=weight)


def normalize_weight_kg(raw: Any) -> Normalized:
    text = str(raw or "").lower()
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return _fail("no number heard")
    n = float(nums[0])
    if any(u in text for u in ("lb", "pound")):
        n = n * 0.4536
    kg = round(n)
    if not 30 <= kg <= 200:
        return _fail(f"{kg} kg is outside the believable range")
    return Normalized(True, kg)


def normalize_year(raw: Any, *, today: date | None = None) -> Normalized:
    today = today or date.today()
    m = re.search(r"(19|20)\d{2}", str(raw or ""))
    if not m:
        two = re.fullmatch(r"\s*(\d{2})\s*", str(raw or ""))
        if not two:
            return _fail("no four-digit year heard")
        yy = int(two.group(1))
        year = 2000 + yy if yy <= today.year % 100 + 1 else 1900 + yy
    else:
        year = int(m.group(0))
    if year < 1970 or year > today.year + 1:
        return _fail(f"{year} is not a believable year of passing")
    return Normalized(True, year)


def normalize_years_experience(raw: Any) -> Normalized:
    text = str(raw or "").lower()
    if any(w in text for w in ("fresher", "no experience", "none")):
        return Normalized(True, 0.0)
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return _fail("no number heard")
    n = float(nums[0])
    if "month" in text and "year" not in text:
        n = round(n / 12, 1)
    if not 0 <= n <= 45:
        return _fail(f"{n} years is not believable")
    return Normalized(True, n)


def normalize_text(raw: Any) -> Normalized:
    text = " ".join(str(raw or "").split())
    if len(text) < 2:
        return _fail("empty")
    return Normalized(True, text[:160])


_BY_KIND = {
    "phone": normalize_phone,
    "height": normalize_height_cm,
    "weight": normalize_weight_kg,
    "year": normalize_year,
    "years": normalize_years_experience,
    "text": normalize_text,
}


def normalize_field(kind: str, raw: Any) -> Normalized:
    return _BY_KIND.get(kind, normalize_text)(raw)
