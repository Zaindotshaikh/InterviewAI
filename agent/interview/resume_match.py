"""Decide whether a resume-mismatch note from the analyst is a real conflict.

The analyst is told that the same place in different words is not a conflict, but it still sometimes flags
"Apollo Hospital" against "Apollo Hospitals, Pune". A wrong flag makes the interviewer stop and ask the
candidate which of two identical things to note. Code checks the note before the question is asked.

A note is dropped only when every distinctive word the candidate said is also in the resume (allowing
plurals, small spelling differences and Devanagari spellings of the same name) and any years they quoted are
within a year of a number in the resume. Anything else stays a real mismatch.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Words that do not identify a workplace.
_GENERIC = frozenset(
    {
        "the", "of", "and", "at", "in", "a", "an", "my", "i", "was", "is", "am", "work", "worked", "working",
        "hospital", "hospitals", "hosp", "clinic", "clinics", "medical", "centre", "center", "pvt", "ltd",
        "private", "limited", "multispeciality", "multispecialty", "speciality", "specialty", "super",
        "institute", "health", "healthcare", "care", "unit", "dept", "department", "ward", "icu", "nicu",
        "picu", "ccu", "ot", "er", "staff", "nurse", "nursing", "years", "year", "months", "month", "saal",
        "sal", "mahine", "में", "का", "की", "के", "है", "हैं", "हूँ", "मैं", "मैंने", "साल", "महीने",
        "अस्पताल", "हॉस्पिटल", "हॉस्पिटल्स", "क्लिनिक", "वार्ड", "आईसीयू", "काम", "किया", "करता", "कर",
        "रहा", "रहे", "था", "थे", "तीन", "दो", "चार", "पांच", "पाँच", "एक",
    }
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"[\w\u0900-\u097f]+", re.UNICODE)
_NOTE = re.compile(r"resume\s+says\s*(?P<resume>.*?)\s*[;:]\s*(?:they|candidate)\s+said\s*(?P<spoken>.*)$", re.I | re.S)

_FUZZY = 0.84

# Rough romanisation so a Devanagari spelling of a Latin name can be compared with the resume.
_INDEPENDENT = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऑ": "o", "ऋ": "ri",
}
_MATRA = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o",
    "ृ": "ri",
}
_CONSONANT = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh",
    "फ़": "f",
}
_HALANT = "्"
_NASAL = {"ं": "n", "ँ": "n"}


def _romanise(word: str) -> str:
    """Approximate Latin spelling of a Devanagari word. Latin text is returned unchanged."""
    if not any("\u0900" <= ch <= "\u097f" for ch in word):
        return word
    out: list[str] = []
    chars = list(word)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in _INDEPENDENT:
            out.append(_INDEPENDENT[ch])
        elif ch in _CONSONANT:
            out.append(_CONSONANT[ch])
            if nxt in _MATRA:
                out.append(_MATRA[nxt])
                i += 1
            elif nxt == _HALANT:
                i += 1
            elif i + 1 < len(chars):
                out.append("a")  # inherent vowel, dropped at the end of a word
        elif ch in _NASAL:
            out.append(_NASAL[ch])
        i += 1
    return "".join(out)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _collapse(word: str) -> str:
    """'apollo' and 'apolo' compare equal: doubled letters are one letter."""
    return re.sub(r"(.)\1+", r"\1", word)


def _distinctive(text: str) -> list[str]:
    words: list[str] = []
    for raw in _WORD.findall(text or ""):
        lowered = raw.casefold()
        if lowered in _GENERIC or raw in _GENERIC or lowered.isdigit():
            continue
        latin = _collapse(_stem(_romanise(lowered)))
        if len(latin) >= 3:
            words.append(latin)
    return words


def _resume_words(resume_text: str) -> set[str]:
    return set(_distinctive(resume_text))


def _word_in_resume(word: str, resume_words: set[str]) -> bool:
    if word in resume_words:
        return True
    return any(SequenceMatcher(None, word, other).ratio() >= _FUZZY for other in resume_words)


def _numbers(text: str) -> list[float]:
    return [float(n) for n in _NUMBER.findall(text or "")]


_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)(?:\s*(?:and\s*)?(\d+)\s*months?)?", re.I)


def _resume_year_figures(resume_text: str) -> list[float]:
    """Experience totals stated in the resume, e.g. '3 years 8 months' becomes 3.67."""
    return [float(y) + (int(m) / 12 if m else 0) for y, m in _YEARS.findall(resume_text or "")]


def _years_agree(spoken_nums: list[float], resume_text: str) -> bool:
    """Spoken years may be rounded: 3 for '3 years 8 months'. Anything else is a real gap."""
    small = [n for n in spoken_nums if 0 < n <= 45]
    if not small:
        return True
    resume_nums = _resume_year_figures(resume_text) or [n for n in _numbers(resume_text) if 0 < n <= 45]
    return all(any(abs(n - r) <= 1.0 for r in resume_nums) for n in small)


def is_false_mismatch(note: str, resume_text: str, utterance: str = "") -> bool:
    """True when the analyst's mismatch note only restates the resume in other words.

    Unknown or unparseable input is never dropped: when we cannot prove the two agree, the question stays.
    """
    note = " ".join((note or "").split())
    resume_text = resume_text or ""
    if not note or not resume_text.strip():
        return False
    parsed = _NOTE.search(note)
    spoken_side = parsed.group("spoken") if parsed else (utterance or "")
    spoken_words = _distinctive(spoken_side)
    spoken_nums = _numbers(spoken_side)
    if not spoken_words and not spoken_nums:
        return False
    resume_words = _resume_words(resume_text)
    if spoken_words and not all(_word_in_resume(w, resume_words) for w in spoken_words):
        return False
    if not spoken_words and not _years_agree(spoken_nums, resume_text):
        return False
    return _years_agree(spoken_nums, resume_text)
