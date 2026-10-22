"""Provider package.

Heavy LiveKit factories live in ``providers.factory`` and load lazily so
``from providers.elevenlabs_voices import ...`` stays free of LiveKit for CI.
"""

from __future__ import annotations

from typing import Any

# Pure helpers — safe without LiveKit
from providers.elevenlabs_voices import elevenlabs_language, elevenlabs_voice_for

__all__ = [
    "elevenlabs_language",
    "elevenlabs_voice_for",
    "build_fallback_stt",
    "build_llm",
    "build_noise_cancellation",
    "build_stt",
    "build_tts",
    "build_vad",
    "SessionRefused",
    "google_voice_for",
    "openai_stt_languages",
    "uses_gemini_tts",
    "_scribe_language_hints",
]


def __getattr__(name: str) -> Any:
    if name in __all__ and name not in {"elevenlabs_language", "elevenlabs_voice_for"}:
        from providers import factory

        return getattr(factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
