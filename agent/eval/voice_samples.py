"""Render the same interviewer lines through different Google TTS setups for listening tests.

Usage (from agent/):
    python -m eval.voice_samples
Writes WAV files to eval/samples/.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import texttospeech
from livekit import rtc
from livekit.plugins import google

load_dotenv(".env")

OUT_DIR = Path(__file__).parent / "samples"

STYLE_PROMPT = (
    "You are a friendly Indian HR interviewer talking to a nurse candidate. "
    "Speak warmly and conversationally at a relaxed, natural pace, like a real person on a call."
)

LINES = {
    "hi-IN": {
        "formal": "नमस्ते Test Candidate, मैं Aven हूँ Kreeda Labs से। कृपया अपना संक्षिप्त परिचय दें।",
        "spoken": "नमस्ते! मैं Aven, Kreeda Labs से बोल रही हूँ। अच्छा, तो... शुरू करते हैं, अपने बारे में थोड़ा बताइए?",
    },
    "mr-IN": {
        "formal": "नमस्कार Test Candidate, मी Kreeda Labs कडून Aven आहे. कृपया आपला संक्षिप्त परिचय द्या.",
        "spoken": "नमस्कार! मी Aven, Kreeda Labs मधून बोलतेय. बरं, तर... सुरुवात करूया, तुमच्याबद्दल थोडं सांगा ना?",
    },
}


def _chirp(language: str) -> google.TTS:
    return google.TTS(
        language=language,
        voice_name=f"{language}-Chirp3-HD-Kore",
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        use_streaming=False,
    )


def _gemini(language: str) -> google.TTS:
    return google.TTS(
        language=language,
        voice_name="Kore",
        model_name="gemini-2.5-flash-tts",
        prompt=STYLE_PROMPT,
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        use_streaming=False,
    )


async def _render(tts: google.TTS, text: str, path: Path) -> None:
    frames: list[rtc.AudioFrame] = []
    async for ev in tts.synthesize(text):
        frames.append(ev.frame)
    path.write_bytes(rtc.combine_audio_frames(frames).to_wav_bytes())
    print(f"wrote {path.name}")


async def main() -> None:
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT in agent/.env")
    OUT_DIR.mkdir(exist_ok=True)
    for language, lines in LINES.items():
        chirp, gemini = _chirp(language), _gemini(language)
        try:
            await _render(chirp, lines["formal"], OUT_DIR / f"{language}_1_chirp_formal.wav")
            await _render(chirp, lines["spoken"], OUT_DIR / f"{language}_2_chirp_spoken.wav")
            try:
                await _render(gemini, lines["spoken"], OUT_DIR / f"{language}_3_gemini_spoken.wav")
            except Exception as err:  # noqa: BLE001
                print(f"gemini {language} failed: {err}")
        finally:
            await chirp.aclose()
            await gemini.aclose()


if __name__ == "__main__":
    asyncio.run(main())
