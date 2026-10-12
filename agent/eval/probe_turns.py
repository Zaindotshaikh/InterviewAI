"""Integration probe: real AgentSession with the turn policy, and which languages the cloud EOT model covers.

Run from agent/:  python -m eval.probe_turns
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(".env")
os.environ.setdefault("LIVEKIT_DEV_MODE", "1")  # what `python main.py dev` sets

import main  # noqa: E402,F401  (registers plugins on the main thread)
from livekit import rtc  # noqa: E402
from livekit.agents import AgentSession  # noqa: E402

from config import get_settings  # noqa: E402
from interview.turns import build_turn_detector, build_turn_handling  # noqa: E402
from providers import build_llm, build_stt, build_tts, build_vad  # noqa: E402


async def run() -> None:
    s = get_settings()
    vad = build_vad(s)
    detector = build_turn_detector(s)
    print("detector:", getattr(detector, "model", None))

    handling = build_turn_handling("mr-IN", s, has_vad=True, detector=detector)
    session = AgentSession(
        stt=build_stt("mr-IN", s),
        llm=build_llm(s),
        tts=build_tts("mr-IN", s),
        vad=vad,
        turn_handling=handling,
        transcription_timeout=s.transcription_timeout_seconds,
    )
    o = session.options
    print("endpointing  :", dict(o.endpointing))
    print("interruption :", dict(o.interruption))
    print("preemptive   :", dict(o.preemptive_generation))
    print("transcription_timeout:", o.transcription_timeout)

    if detector is None:
        return
    stream = detector.stream()
    silence = rtc.AudioFrame(b"\x00\x00" * 1600, 16000, 1, 1600)
    for _ in range(10):
        stream.push_audio(silence)
        await asyncio.sleep(0.1)
    await asyncio.sleep(3)
    th = detector._opts.thresholds
    print("server thresholds:", th.thresholds or "(none received: cloud unreachable or model unsupported)")
    covered = sorted(set(th.thresholds or {}) & {"hi", "en", "mr", "ta", "te", "kn", "ml"})
    print("our languages with a tuned threshold:", covered)
    await stream.aclose()


if __name__ == "__main__":
    asyncio.run(run())
