"""Render candidate in-sentence fillers with the real interview voice and measure them.

Usage (from agent/):  python -m eval.filler_probe
Writes eval/samples/filler_<lang>_<variant>.wav. "added" is how much longer the line got versus the
no-filler baseline: a natural filled pause adds ~0.2-0.6s; a stretched moan adds well over 0.8s.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(".env")

from livekit import rtc  # noqa: E402

from config import get_settings  # noqa: E402
from interview.fillers import acks_for  # noqa: E402
from providers import build_tts  # noqa: E402

OUT_DIR = Path(__file__).parent / "samples"

# {filler} sits where a person hesitates: after the opening connector, before the specific detail.
LINES = {
    "mr-IN": "बरं, तर {filler}तुम्ही ICU मध्ये किती वर्षं काम केलं?",
    "hi-IN": "अच्छा, तो {filler}आपने ICU में कितने साल काम किया?",
    "ta-IN": "சரி, {filler}நீங்க ICU-ல எத்தனை வருஷம் வேலை பார்த்தீங்க?",
    "en-IN": "Okay, so {filler}how long were you in the ICU?",
}
VARIANTS = {
    "none": "",
    "umm_latin": "umm, ",
}


async def _render(tts, text: str) -> rtc.AudioFrame:
    stream = tts.stream()
    stream.push_text(text)
    stream.end_input()
    frames = [ev.frame async for ev in stream]
    await stream.aclose()
    return rtc.combine_audio_frames(frames)


def _speech_seconds(frame: rtc.AudioFrame) -> float:
    """Duration between first and last audible 20ms window (ignores leading/trailing silence)."""
    audio = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32)
    win = frame.sample_rate // 50
    n = len(audio) // win
    if n == 0:
        return 0.0
    rms = np.sqrt((audio[: n * win].reshape(n, win) ** 2).mean(axis=1))
    loud = np.nonzero(rms > 300)[0]
    return 0.0 if len(loud) == 0 else (loud[-1] - loud[0] + 1) * 0.02


async def main() -> None:
    settings = get_settings()
    OUT_DIR.mkdir(exist_ok=True)
    for language, line in LINES.items():
        tts = build_tts(language, settings)
        base = None
        for name, filler in VARIANTS.items():
            text = line.format(filler=filler)
            secs = []
            for _ in range(3):  # Chirp varies take to take; use the median
                audio = await _render(tts, text)
                secs.append(_speech_seconds(audio))
            secs.sort()
            med = secs[1]
            if name == "none":
                base = med
            (OUT_DIR / f"filler_{language}_{name}.wav").write_bytes(audio.to_wav_bytes())
            added = med - (base or med)
            print(f"{language} {name:10s} speech={med:.2f}s added={added:+.2f}s  takes={secs}")
        for i, ack in enumerate(acks_for(language)):
            audio = await _render(tts, ack)
            (OUT_DIR / f"ack_{language}_{i}.wav").write_bytes(audio.to_wav_bytes())
            print(f"{language} ack {ack!r:14s} speech={_speech_seconds(audio):.2f}s")
        await tts.aclose()


if __name__ == "__main__":
    asyncio.run(main())
