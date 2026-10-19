"""ElevenLabs voice id helpers — kept free of LiveKit imports for unit tests / CI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings


def elevenlabs_language(language: str) -> str:
    """ElevenLabs wants a short language code (hi, mr, en), not a BCP-47 locale."""
    return (language or "en").split("-")[0].lower()


def elevenlabs_voice_for(language: str, settings: Settings) -> str:
    """One ElevenLabs voice for every language (Sujata by default) — no EN/Indic switch.

    Optional ELEVENLABS_VOICE_BY_LANG still wins when set; otherwise prefer
    ELEVENLABS_VOICE_ID_LOCAL, then ELEVENLABS_VOICE_ID.
    """
    code = elevenlabs_language(language)
    raw = (getattr(settings, "elevenlabs_voice_by_lang", "") or "").strip()
    if raw:
        wanted = (language or "").strip().lower()
        wanted_code = code
        for part in raw.split(","):
            piece = part.strip()
            if ":" not in piece:
                continue
            k, v = piece.split(":", 1)
            k = k.strip().lower()
            if (k == wanted or k == wanted_code) and v.strip():
                return v.strip()
    return settings.elevenlabs_voice_id_local or settings.elevenlabs_voice_id
