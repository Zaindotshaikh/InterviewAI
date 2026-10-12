"""Render one interviewer reply with and without phrase pauses through the live TTS path.

Usage (from agent/):  python -m eval.pause_samples
Writes eval/samples/pause_<lang>_A_before.wav and pause_<lang>_B_after.wav and prints the exact text sent to TTS.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")

from livekit import rtc  # noqa: E402

from config import get_settings  # noqa: E402
from interview.disfluency import Disfluency  # noqa: E402
from providers import build_tts  # noqa: E402

OUT_DIR = Path(__file__).parent / "samples"

# Written the way the updated prompt asks the LLM to write: commas at breath points.
REPLIES = {
    "hi-IN": [
        "अच्छा, तो आप ICU में काम करती हैं और night shift भी करती हैं। ",
        "मुझे बताइए, जब कोई patient अचानक critical हो जाए, तब आप सबसे पहले क्या करती हैं? ",
        "और उस वक़्त team के साथ कैसे बात करती हैं?",
    ],
    "mr-IN": [
        "बरं, म्हणजे तुम्ही ICU मध्ये काम करता आणि night shift सुद्धा करता. ",
        "मला सांगा, एखादा patient अचानक critical झाला, तर तुम्ही सगळ्यात आधी काय करता? ",
        "आणि त्या वेळी team सोबत कसं बोलता?",
    ],
}


async def _stream(chunks):
    for c in chunks:
        yield c


async def _shape(chunks: list[str], language: str, phrase_rate: float, seed: int) -> list[str]:
    d = Disfluency(0.5, True, random.Random(seed), phrase_pause_rate=phrase_rate)
    return [s async for s in d.apply(_stream(chunks), language)]


async def _render(tts, text: str) -> rtc.AudioFrame:
    stream = tts.stream()
    stream.push_text(text)
    stream.end_input()
    frames = [ev.frame async for ev in stream]
    await stream.aclose()
    return rtc.combine_audio_frames(frames)


async def main() -> None:
    settings = get_settings()
    OUT_DIR.mkdir(exist_ok=True)
    for language, chunks in REPLIES.items():
        tts = build_tts(language, settings)
        for label, rate in (("A_before", 0.0), ("B_after", 1.0)):
            shaped = await _shape(chunks, language, rate, seed=7)
            text = "".join(shaped)
            print(f"\n[{language} {label}] {text}")
            audio = await _render(tts, text)
            secs = audio.samples_per_channel / audio.sample_rate
            path = OUT_DIR / f"pause_{language}_{label}.wav"
            path.write_bytes(audio.to_wav_bytes())
            print(f"  -> {path.name} ({secs:.1f}s)")
        await tts.aclose()


if __name__ == "__main__":
    asyncio.run(main())
