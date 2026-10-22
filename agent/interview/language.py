"""Language helpers: script detection, speaker map, switch tooling."""

from __future__ import annotations

from dataclasses import dataclass


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
        f"Write the whole reply in {profile.label} script, including English words such as diaper, comfortable, ICU and hospital. "
        "Do not leave those words in Latin letters — that switches the voice. "
        f"Stay on {profile.label} for the whole call."
    )
