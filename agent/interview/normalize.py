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

# Spoken digit words the STT sometimes leaves unconverted (English only; the analyst converts the rest).
_WORD_DIGITS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


@dataclass(frozen=True)
class Normalized:
    ok: bool
    value: Any = None
    reason: str = ""


def _fail(reason: str) -> Normalized:
    return Normalized(False, None, reason)


def normalize_phone(raw: Any) -> Normalized:
    text = str(raw or "").lower()
    for word, digit in _WORD_DIGITS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    digits = "".join(_DIGITS.findall(text))
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        return _fail(f"heard {len(digits)} digits, need 10")
    if digits[0] not in "6789":
        return _fail("Indian mobile numbers start with 6, 7, 8 or 9")
    return Normalized(True, digits)


def spoken_groups(phone: str) -> str:
    """98765 43210 -> '98765, 43210' so the voice reads it in two breaths."""
    return f"{phone[:5]}, {phone[5:]}"


def normalize_height_cm(raw: Any) -> Normalized:
    text = str(raw or "").lower().replace("’", "'").replace("”", '"')
    # 5'4", 5 ft 4 in, 5 feet 4 inches, 5.4 (feet.inches as people say it)
    m = re.search(r"(\d)\s*(?:'|ft|feet|foot|फुट|फीट)\s*(\d{1,2})?\s*(?:\"|in|inch|inches|इंच)?", text)
    if m:
        feet, inches = int(m.group(1)), int(m.group(2) or 0)
        if inches > 11:
            return _fail("inches must be below 12")
        cm = round((feet * 12 + inches) * 2.54)
        return _check_height(cm)
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return _fail("no number heard")
    n = float(nums[0])
    if "m" in text and "cm" not in text and 1.0 <= n <= 2.3:
        return _check_height(round(n * 100))
    if 3.5 <= n <= 7.5:  # "5.4" meaning 5 ft 4 in
        feet = int(n)
        inches = round((n - feet) * 10)
        if inches > 11:
            return _fail("ambiguous height")
        return _check_height(round((feet * 12 + inches) * 2.54))
    return _check_height(round(n))


def _check_height(cm: int) -> Normalized:
    if not 120 <= cm <= 210:
        return _fail(f"{cm} cm is outside the believable range")
    return Normalized(True, cm)


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
