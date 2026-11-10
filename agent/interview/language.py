"""Language helpers: script detection, speaker map, switch tooling."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Candidate clearly asked to change language — not English job words in a Hindi answer.
_EXPLICIT_LANGUAGE_SWITCH = re.compile(
    r"\b(?:speak|talk|switch|change)\b.{0,24}\b(?:language|english|hindi|tamil|telugu|"
    r"kannada|malayalam|marathi|bengali|gujarati|punjabi|odia|oriya)\b|"
    r"\b(?:english|hindi|tamil|telugu)\s+(?:please|bolo|में बोल)|"
    r"(?:भाषा\s*बदल|भाषा\s*चेंज|अंग्रेजी\s*में\s*बोल|हिंदी\s*में\s*बोल|"
    r"इंग्लिश\s*में|english\s*mein|hindi\s*mein)",
    re.I,
)


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    label: str
    stt_mode: str
    tts_speaker: str
    script_ranges: tuple[tuple[int, int], ...] = ()


PROFILES: dict[str, LanguageProfile] = {
    "en-IN": LanguageProfile("en-IN", "English", "transcribe", "ishita"),
    "hi-IN": LanguageProfile(
        "hi-IN",
        "Hindi",
        "codemix",
        "priya",
        ((0x0900, 0x097F),),
    ),
    "ta-IN": LanguageProfile(
        "ta-IN",
        "Tamil",
        "codemix",
        "ishita",
        ((0x0B80, 0x0BFF),),
    ),
    "te-IN": LanguageProfile(
        "te-IN",
        "Telugu",
        "codemix",
        "priya",
        ((0x0C00, 0x0C7F),),
    ),
    "kn-IN": LanguageProfile(
        "kn-IN",
        "Kannada",
        "codemix",
        "ishita",
        ((0x0C80, 0x0CFF),),
    ),
    "ml-IN": LanguageProfile(
        "ml-IN",
        "Malayalam",
        "codemix",
        "pooja",
        ((0x0D00, 0x0D7F),),
    ),
    "mr-IN": LanguageProfile(
        "mr-IN",
        "Marathi",
        "codemix",
        "priya",
        ((0x0900, 0x097F),),
    ),
    "bn-IN": LanguageProfile(
        "bn-IN",
        "Bengali",
        "codemix",
        "roopa",
        ((0x0980, 0x09FF),),
    ),
    "gu-IN": LanguageProfile(
        "gu-IN",
        "Gujarati",
        "codemix",
        "priya",
        ((0x0A80, 0x0AFF),),
    ),
    "pa-IN": LanguageProfile(
        "pa-IN",
        "Punjabi",
        "codemix",
        "roopa",
        ((0x0A00, 0x0A7F),),
    ),
    "od-IN": LanguageProfile(
        "od-IN",
        "Odia",
        "codemix",
        "ritu",
        ((0x0B00, 0x0B7F),),
    ),
}


def get_profile(code: str) -> LanguageProfile:
    return PROFILES.get(code) or PROFILES["en-IN"]


def detect_script_language(text: str) -> str | None:
    """Return a language code if a dominant Indic script is detected."""
    counts: dict[str, int] = {code: 0 for code in PROFILES}
    for ch in text:
        cp = ord(ch)
        for code, profile in PROFILES.items():
            for start, end in profile.script_ranges:
                if start <= cp <= end:
                    counts[code] += 1
                    break
    # Prefer south languages over Hindi when Devanagari isn't the only match
    best = max(counts.items(), key=lambda kv: kv[1])
    if best[1] < 4:
        return None
    # Marathi and Hindi share Devanagari — default to hi-IN
    if best[0] == "mr-IN" and counts["hi-IN"] == counts["mr-IN"]:
        return "hi-IN"
    return best[0]


def explicit_language_switch_request(text: str | None) -> bool:
    """True only when the candidate asked to change language, not when they used English terms."""
    return bool(_EXPLICIT_LANGUAGE_SWITCH.search(str(text or "")))


def native_script_reminder(language: str) -> str:
    profile = get_profile(language)
    if language == "en-IN":
        return (
            "Respond in clear Indian English only. Do not switch into Hindi. "
            "Never say kar raha hoon, kar rahi hoon, karta hoon, or karti hoon. "
            "You are a woman; refer to yourself in English. Keep this same voice for the whole call."
        )
    return (
        f"Respond in everyday spoken {profile.label}, not formal written {profile.label}. "
        f"Write ordinary words in {profile.label} script. "
        "Keep clinical and drug names in English Latin letters, the way a nurse says them: "
        "insulin, potassium chloride, high-alert medicine, ICU, ventilator, bed bath, bedpan, diaper, hygiene, hospital. "
        "Do not translate those into pure or textbook words and do not rewrite them into the local script "
        "(not उच्च-सतर्क, not इंसुलिन, not पोटैशियम क्लोराइड). "
        f"Stay on {profile.label} for the rest of the sentence."
    )
