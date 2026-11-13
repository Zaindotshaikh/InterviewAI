"""Deterministic cross-checks of what the candidate said against the resume and against common sense.

Pure functions, no model call. The flow decides what to say; these only decide whether a spoken fact
needs one verification question. Unknown or unparseable input never raises an issue: when we cannot
prove a conflict, the interview carries on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# Spoken years may be rounded ("three" for 3 years 8 months). A gap of a year or more is a real conflict.
EXPERIENCE_TOLERANCE_YEARS = 1.0

# Height and weight each pass their own range check. Together they still have to be a human body.
BMI_MIN = 13.0
BMI_MAX = 50.0

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_RANGE = re.compile(
    rf"({_MONTH})\s*,?\s*((?:19|20)\d{{2}})\s*(?:-|–|—|to|till|until)\s*"
    rf"(?:({_MONTH})\s*,?\s*((?:19|20)\d{{2}})|(present|current|till\s*date|ongoing|now|date))",
    re.IGNORECASE,
)
_YEARS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)(?:\s*(?:and\s*)?(\d+)\s*(?:months?|mos?))?",
    re.IGNORECASE,
)
_EXP_WORD = re.compile(r"experience|exp\b|clinical|worked|working|nursing career|in the field", re.IGNORECASE)
_NOT_EXPERIENCE = re.compile(r"\bage\b|years?\s*old|\|\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ResumeFacts:
    years: float | None = None
    qualifications: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Issue:
    """A spoken fact that needs one verification question."""

    field: str
    kind: str  # resume_mismatch | not_nursing | implausible_body
    spoken: str
    expected: str = ""
    note: str = ""


# ------------------------------------------------------------------------------------------ qualification

# Canonical nursing qualifications. Order matters: the most specific pattern first.
QUAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:post\s*basic\s*(?:b\.?\s*sc|bsc|diploma)?|pbbsc|pb\s*b\.?\s*sc)\b|पोस्ट\s*बेसिक", re.I), "Post Basic B.Sc Nursing"),
    (re.compile(r"\b(?:m\.?\s*sc|msc)\s*(?:nursing)?\b|एमएससी|एम\s*एस\s*सी", re.I), "M.Sc Nursing"),
    (re.compile(r"\b(?:b\.?\s*sc|bsc|b\.?\s*s\.?\s*c|bachelor\s*of\s*science)\b|बीएससी|बी\s*एस\s*सी", re.I), "B.Sc Nursing"),
    (re.compile(r"\b(?:gnm|g\s*n\s*m|general\s*nursing(?:\s*and\s*midwifery)?)\b|जीएनएम|जी\s*एन\s*एम", re.I), "GNM"),
    (re.compile(r"\b(?:anm|a\s*n\s*m|auxiliary\s*nursing(?:\s*midwifery)?)\b|एएनएम|ए\s*एन\s*एम", re.I), "ANM"),
    (re.compile(r"\b(?:diploma\s*(?:in)?\s*nursing|nursing\s*diploma)\b|डिप्लोमा", re.I), "Diploma in Nursing"),
]

# Qualifications that count as the same level for a mismatch check.
_COMPATIBLE: dict[str, frozenset[str]] = {
    "B.Sc Nursing": frozenset({"B.Sc Nursing", "Post Basic B.Sc Nursing"}),
    "Post Basic B.Sc Nursing": frozenset({"B.Sc Nursing", "Post Basic B.Sc Nursing"}),
    "GNM": frozenset({"GNM", "Diploma in Nursing"}),
    "Diploma in Nursing": frozenset({"GNM", "Diploma in Nursing"}),
    "M.Sc Nursing": frozenset({"M.Sc Nursing"}),
    "ANM": frozenset({"ANM"}),
}

NURSING_QUALIFICATIONS = ("GNM", "ANM", "B.Sc Nursing", "Post Basic B.Sc Nursing", "Diploma in Nursing")


def nursing_qualification(text: Any) -> str | None:
    """Canonical nursing qualification named in the text, or None (B.Tech, BCA, 12th, ...)."""
    s = " ".join(str(text or "").split())
    if not s:
        return None
    for pat, canonical in QUAL_PATTERNS:
        if pat.search(s):
            return canonical
    return None


def resume_qualifications(resume_text: str) -> frozenset[str]:
    found: set[str] = set()
    for line in (resume_text or "").splitlines():
        canonical = nursing_qualification(line)
        if canonical:
            found.add(canonical)
    return frozenset(found)


def check_qualification(spoken: Any, facts: ResumeFacts) -> Issue | None:
    said = " ".join(str(spoken or "").split())
    if not said:
        return None
    canonical = nursing_qualification(said)
    if canonical is None:
        expected = " / ".join(sorted(facts.qualifications))
        return Issue("qualification", "not_nursing", said[:80], expected, "not a nursing qualification")
    if facts.qualifications:
        ok = set()
        for q in facts.qualifications:
            ok |= _COMPATIBLE.get(q, frozenset({q}))
        if canonical not in ok:
            expected = " / ".join(sorted(facts.qualifications))
            return Issue("qualification", "resume_mismatch", canonical, expected, "differs from the resume")
    return None


# ----------------------------------------------------------------------------------------------- experience


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _date_range_months(resume_text: str, today: date) -> float | None:
    """Total months across the work-experience date ranges, overlaps counted once."""
    text = resume_text or ""
    section = re.search(r"(?im)^\s*(?:work\s+)?(?:experience|employment)[^\n]*$", text)
    scope = text[section.end():] if section else text
    nxt = re.search(r"(?m)^\s*[A-Z][A-Z &/]{5,}\s*$", scope)
    if section and nxt:
        scope = scope[: nxt.start()]
    spans: list[tuple[int, int]] = []
    for m in _RANGE.finditer(scope):
        start = _month_index(int(m.group(2)), _MONTHS[m.group(1)[:3].lower()])
        if m.group(4):
            end = _month_index(int(m.group(4)), _MONTHS[m.group(3)[:3].lower()])
        else:
            end = _month_index(today.year, today.month)
        if end >= start:
            spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged) / 12.0


def _stated_total_years(resume_text: str) -> float | None:
    """'3 years 8 months clinical experience' -> 3.67. Ages and course lengths are ignored."""
    text = " ".join((resume_text or "").split())
    for m in _YEARS.finditer(text):
        before = text[max(0, m.start() - 70): m.start()]
        after = text[m.end(): m.end() + 70]
        around = f"{before} {m.group(0)} {after}"
        if _NOT_EXPERIENCE.search(after[:12]) or re.search(r"\bage\b\s*[:\-]?\s*$", before, re.I):
            continue
        if not _EXP_WORD.search(around):
            continue
        # "about 2 years 3 months" inside one job line is a part, not the total: totals sit in the summary.
        if re.search(r"\b(?:at|since|from)\b[^.]{0,40}$", before, re.I) and "|" in before[-60:]:
            continue
        years = float(m.group(1)) + (int(m.group(2)) / 12.0 if m.group(2) else 0.0)
        if 0 < years <= 45:
            return round(years, 2)
    return None


def resume_experience_years(resume_text: str, today: date | None = None) -> float | None:
    stated = _stated_total_years(resume_text)
    if stated is not None:
        return stated
    computed = _date_range_months(resume_text, today or date.today())
    return round(computed, 2) if computed else None


def resume_facts(resume_text: str, today: date | None = None) -> ResumeFacts:
    text = resume_text or ""
    if not text.strip():
        return ResumeFacts()
    return ResumeFacts(
        years=resume_experience_years(text, today),
        qualifications=resume_qualifications(text),
    )


_PLACE_NAME = re.compile(
    r"\b([A-Z][A-Za-z&.']+(?:\s+[A-Z][A-Za-z&.']+)*)\s+(Hospitals?|Clinic|Nursing Home)\b"
)
_PLACE_GENERIC = frozenset(
    {"hospital", "hospitals", "clinic", "nursing", "home", "ward", "medical", "general", "staff"}
)


def resume_workplaces(resume_text: str) -> list[str]:
    found: list[str] = []
    for match in _PLACE_NAME.finditer(resume_text or ""):
        name = f"{match.group(1)} {match.group(2)}"
        if name not in found:
            found.append(name)
    return found


def workplace_conflict(spoken: str, resume_text: str) -> str:
    """Resume workplaces when the spoken place is a different one.

    Empty when the names agree, or when the utterance names no place we can compare.
    """
    tokens = [
        word
        for word in re.findall(r"[A-Za-z]{4,}", spoken or "")
        if word.lower() not in _PLACE_GENERIC
    ]
    if not tokens:
        return ""
    blob = (resume_text or "").lower()
    if any(word.lower() in blob for word in tokens):
        return ""
    return ", ".join(resume_workplaces(resume_text))


def format_years(years: float) -> str:
    whole = int(years)
    months = round((years - whole) * 12)
    if months == 12:
        whole, months = whole + 1, 0
    parts = []
    if whole:
        parts.append(f"{whole} year{'s' if whole != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts) or "no experience"


def check_experience(spoken_years: Any, facts: ResumeFacts) -> Issue | None:
    if facts.years is None:
        return None
    try:
        said = float(spoken_years)
    except (TypeError, ValueError):
        return None
    if abs(said - facts.years) < EXPERIENCE_TOLERANCE_YEARS:
        return None
    return Issue(
        "experience_years",
        "resume_mismatch",
        format_years(said),
        format_years(facts.years),
        "differs from the resume",
    )


# ------------------------------------------------------------------------------------------------- body


def body_issue(height_cm: Any, weight_kg: Any) -> Issue | None:
    try:
        h = float(height_cm)
        w = float(weight_kg)
    except (TypeError, ValueError):
        return None
    if h <= 0 or w <= 0:
        return None
    bmi = w / ((h / 100.0) ** 2)
    if BMI_MIN <= bmi <= BMI_MAX:
        return None
    return Issue(
        "body",
        "implausible_body",
        f"{round(h)} cm, {round(w)} kg",
        "",
        f"height and weight do not fit together (BMI {bmi:.0f})",
    )
