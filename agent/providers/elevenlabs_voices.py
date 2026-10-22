"""ElevenLabs voice id helpers — kept free of LiveKit imports for unit tests / CI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings


def elevenlabs_language(language: str) -> str:
    """Short code ElevenLabs TTS accepts. Product Odia `od-IN` is `or`."""
    short = (language or "en").split("-")[0].lower()
    if short == "od":
        return "or"
    return short or "en"


def scribe_language_hints(language: str) -> tuple[str, list[str]]:
    """Primary + secondary codes for Scribe v2. Odia uses `or` (not `od`)."""
    short = (language or "en-IN").split("-")[0].lower()
    primary = "or" if short == "od" else short
    secondary = ["en"]
    if primary not in ("en", "hi"):
        secondary.append("hi")
    secondary = [code for code in secondary if code != primary]
    return primary, secondary


def _voice_lookup_keys(language: str) -> set[str]:
    full = (language or "").strip().lower()
    short = full.split("-")[0] if full else ""
    spoken = elevenlabs_language(language)
    keys = {key for key in (full, short, spoken) if key}
    if short == "od" or spoken == "or":
        keys.update({"od", "od-in", "or"})
    return keys


def elevenlabs_voice_for(language: str, settings: Settings) -> str:
    """Voice id for this join language.

    `ELEVENLABS_VOICE_BY_LANG` is a comma list of `code:voiceId`. A key may be
    the full code (`te-IN`) or the short code (`te`). Odia matches `od-IN`,
    `od`, or `or`. A missing key falls back to one shared id.
    """
    raw = (getattr(settings, "elevenlabs_voice_by_lang", "") or "").strip()
    if raw:
        wanted = _voice_lookup_keys(language)
        for part in raw.split(","):
            piece = part.strip()
            if ":" not in piece:
                continue
            key, value = piece.split(":", 1)
            if key.strip().lower() in wanted and value.strip():
                return value.strip()
    return settings.elevenlabs_voice_id_local or settings.elevenlabs_voice_id
