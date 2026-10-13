"""Render whitelist tone samples for human listening (Phase 4 harness)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import get_settings  # noqa: E402
from interview.voice_tone import TONE_TAG  # noqa: E402
from providers import build_tts  # noqa: E402

LINES = {
    "warm": "नमस्ते, मैं Aven बोल रही हूँ Kreeda Labs से।",
    "curious": "आपने ICU में day to day क्या handle किया?",
    "gentle": "कोई बात नहीं, धीरे से बताइए diaper care के बारे में।",
    "reassuring": "घबराइए मत, जल्दी नहीं है।",
    "matter_of_fact": "Height और weight बताइए, बस profile के लिए।",
    "thoughtful": "अगर dose ज्यादा लगे तो आप क्या करते हैं?",
    "plain": "आप किस शहर में apply कर रहे हैं?",
}

OUT = Path(__file__).resolve().parent / "audio_ab" / "out"


async def _synth(tts, text: str) -> bytes:
    stream = tts.stream()
    try:
        stream.push_text(text)
        stream.end_input()
        frames = [ev.frame async for ev in stream]
    finally:
        await stream.aclose()
    # Concatenate PCM to a minimal WAV via livekit if available
    from livekit import rtc

    if not frames:
        return b""
    sample_rate = frames[0].sample_rate
    import numpy as np
    import wave
    import io

    audio = np.concatenate([np.frombuffer(f.data, dtype=np.int16) for f in frames])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


async def main() -> None:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise SystemExit("ELEVENLABS_API_KEY required")
    OUT.mkdir(parents=True, exist_ok=True)
    tts = build_tts("hi-IN", settings, provider="elevenlabs")
    print("model", settings.elevenlabs_model, "voice", settings.elevenlabs_voice_id_local)
    print("NOTE: verify VoiceSettings fields for eleven_v4_turbo in ElevenLabs docs before A/B.")
    for name, line in LINES.items():
        tag = TONE_TAG.get(name)
        text = f"{tag} {line}" if tag else line
        wav = await _synth(tts, text)
        path = OUT / f"{name}.wav"
        path.write_bytes(wav)
        print("wrote", path, "bytes", len(wav), "text=", text[:60])


if __name__ == "__main__":
    asyncio.run(main())
