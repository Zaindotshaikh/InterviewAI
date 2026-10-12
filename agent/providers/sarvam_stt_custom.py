"""Optional thin Sarvam realtime STT with keyterms query param.

The official livekit-plugins-sarvam STTStreaming may not expose keyterms yet.
When SARVAM_USE_CUSTOM_STT=1, prefer wiring this class; otherwise providers
use the official plugin and pass a short `prompt` for domain bias.
"""

from __future__ import annotations

# Placeholder for a future custom LiveKit STT implementation using
# wss://api.sarvam.ai/speech-to-text-realtime/ws?model=saaras:v4&keyterms=...
# See docs: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/how-to/keyterms.md

SUPPORTED_MODELS = ("saaras:v4", "saaras:v3-realtime")
DEFAULT_STREAM_TYPE = "fast"
DEFAULT_MODE = "codemix"


def build_keyterms_query(keyterms: list[str]) -> str:
    import json
    import urllib.parse

    clipped = [t[:64] for t in keyterms[:50] if t and t.strip()]
    return urllib.parse.quote(json.dumps(clipped, ensure_ascii=False))
