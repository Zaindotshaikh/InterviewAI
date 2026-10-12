"""Human-sounding fillers, all spoken by the interview voice itself.

Two moments where people naturally fill speech, and only these:
  1. Turn start: right after the other person finishes, a short reaction ("बरं.", "अच्छा.", "Okay.")
     while they think. Pre-rendered with the interview TTS (same voice and accent) and played while
     the reply is prepared.
  2. Mid-sentence: one "umm," where the speaker searches for the next words - after an opening
     connector, before a specific detail, or while rephrasing. The LLM places it; normalize_fillers()
     makes the spelling canonical, keeps at most one per reply and removes vowel moans.

A standalone "Um" clip is what Chirp stretched into a moan; inside a sentence, with a comma on each
side, the Indic voices say it short (eval/filler_probe.py: +0.5s in mr-IN).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

import numpy as np
from livekit import rtc

logger = logging.getLogger("interview-v2.fillers")

# Canonical in-sentence filled pause. Latin script in every language: the probe found it the most
# consistent take-to-take in Marathi and Hindi.
INDIC_UM = "umm,"
ENGLISH_UM = "um,"

# Turn-start reactions, real words only (bare vowels like "आ" are what moaned). Period, not ellipsis,
# so the voice does not drag the word out. Two words each: Chirp streams a lone word ("बरं.") as silence.
ACKS: dict[str, list[str]] = {
    "hi-IN": ["ठीक है.", "अच्छा, ठीक है.", "हाँ जी, अच्छा."],
    "mr-IN": ["हो, बरं.", "बरं, ठीक आहे.", "अच्छा, बरं."],
    "ta-IN": ["சரி, சரி.", "ஓகே, சரி."],
    "te-IN": ["సరే, సరే.", "ఓకే, సరే."],
    "kn-IN": ["ಸರಿ, ಸರಿ.", "ಓಕೆ, ಸರಿ."],
    "ml-IN": ["ശരി, ശരി.", "ഓക്കെ, ശരി."],
    "bn-IN": ["আচ্ছা, ঠিক আছে.", "ঠিক আছে."],
    "gu-IN": ["સારું, સારું.", "અચ્છા, સારું."],
    "pa-IN": ["ਠੀਕ ਹੈ.", "ਅੱਛਾ, ਠੀਕ ਹੈ."],
    "en-IN": ["Okay, got it.", "Right, okay.", "Okay, sure."],
}

MIN_WORDS_FOR_FILLER = 4
MIN_VOICED_SECONDS = 0.15
MAX_VOICED_SECONDS = 1.6  # two short words measure ~0.6-1.4s; longer means the voice dragged them
MAX_RENDER_ATTEMPTS = 4


def um_for(language: str) -> str:
    return ENGLISH_UM if language.startswith("en") else INDIC_UM


def acks_for(language: str) -> list[str]:
    return ACKS.get(language, ACKS["en-IN"])


# --- text normalization ------------------------------------------------------------------------

_SEP = r"(?:\s*(?:\.\.\.|…|[,.!?।॥]))?"
# Letters and vowel signs of the Indic scripts, minus the danda (।॥), so "आता" is one word but "आ।" is a token.
_L = r"[\w\u0900-\u0963\u0966-\u0D7F]"
# Filled pauses in any spelling the LLM may write; all become the canonical um.
_UM_FAMILY = re.compile(rf"(?<!{_L})(?:(?i:u+h*m+|u+h+|e+r+m+|e+h+m+)|उम्+म?|उम्म|अं+)(?!{_L})" + _SEP)
# Vowel moans and humming: never wanted, removed outright. Real words (आता, अच्छा, आणि) are untouched.
_MOAN = re.compile(
    rf"(?<!{_L})(?:(?i:a+h+|h+m+|e+r+)|आ+ह*|अः|उह+|हम्+म?|हं+|ஆ+|ఆ+|ಆ+|ആ+|আ+|આ+|ਆ+)(?!{_L})" + _SEP
)
_SPACES = re.compile(r"[ \t]{2,}")
_PAUSE_TAG = re.compile(r"\[pause[^\]]*\]")
_PUNCT_ONLY = re.compile(r"^[\s.,!?…।॥\"')\]]*$")


def normalize_fillers(text: str, language: str, *, allow_um: bool) -> tuple[str, bool]:
    """Return (text, used_um). Moans go; the first um-family token becomes canonical if allowed, others go."""
    if not text.strip():
        return text, False
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    body = _MOAN.sub(" ", text.strip())
    used = False

    def _um(m: re.Match[str]) -> str:
        nonlocal used
        if allow_um and not used:
            used = True
            return f" {um_for(language)} "
        return " "

    body = _UM_FAMILY.sub(_um, body)
    body = _SPACES.sub(" ", body).strip()
    # A filler at the very start loses its leading comma context; also drop a dangling leading comma.
    body = body.lstrip(",، ").strip()
    if used and body.rstrip(" ,").endswith(um_for(language).rstrip(",")):
        # Ending on "umm" sounds like trailing off; drop it.
        body = body.rstrip(" ,")[: -len(um_for(language).rstrip(","))].rstrip(" ,")
        used = False
    return f"{lead}{body}{trail}", used


def is_speakable(text: str) -> bool:
    """False for empty or punctuation-only leftovers that must not reach TTS."""
    return not _PUNCT_ONLY.match(_PAUSE_TAG.sub("", text or ""))


# --- turn-start acknowledgement player -----------------------------------------------------------


def _voiced_seconds(frames: list[rtc.AudioFrame]) -> float:
    """Seconds of audible speech, in 20ms windows above a quiet-room RMS floor."""
    if not frames:
        return 0.0
    sr = frames[0].sample_rate
    audio = np.concatenate([np.frombuffer(f.data, dtype=np.int16) for f in frames]).astype(np.float32)
    win = sr // 50
    n = len(audio) // win
    if n == 0:
        return 0.0
    rms = np.sqrt((audio[: n * win].reshape(n, win) ** 2).mean(axis=1))
    return float((rms > 300).sum()) * 0.02


class FillerPlayer:
    """Pre-renders turn-start reactions with the interview voice so playback starts instantly."""

    def __init__(self, tts: Any, probability: float) -> None:
        self._tts = tts
        self._probability = probability
        self._cache: dict[str, dict[str, list[rtc.AudioFrame]]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._last: str | None = None

    def prepare(self, language: str) -> None:
        if self._tts is None or self._probability <= 0 or language in self._tasks:
            return
        self._tasks[language] = asyncio.create_task(self._render(language))

    async def _render(self, language: str) -> None:
        rendered: dict[str, list[rtc.AudioFrame]] = {}
        for text in acks_for(language):
            for _ in range(MAX_RENDER_ATTEMPTS):
                try:
                    frames = await self._synthesize(text)
                except Exception:  # noqa: BLE001
                    logger.warning("filler render failed for %r (%s)", text, language)
                    continue
                if MIN_VOICED_SECONDS <= _voiced_seconds(frames) <= MAX_VOICED_SECONDS:
                    rendered[text] = frames
                    break
        self._cache[language] = rendered

    async def _synthesize(self, text: str) -> list[rtc.AudioFrame]:
        stream = self._tts.stream()
        try:
            stream.push_text(text)
            stream.end_input()
            return [ev.frame async for ev in stream]
        finally:
            await stream.aclose()

    def pick(self, language: str, candidate_text: str) -> tuple[str, list[rtc.AudioFrame]] | None:
        """Return a reaction to play for this turn, or None to stay silent."""
        if len(candidate_text.split()) < MIN_WORDS_FOR_FILLER or random.random() >= self._probability:
            return None
        rendered = self._cache.get(language)
        if not rendered:
            self.prepare(language)
            return None
        options = [t for t in rendered if t != self._last] or list(rendered)
        text = random.choice(options)
        self._last = text
        return text, rendered[text]


async def frames_iter(frames: list[rtc.AudioFrame]):
    for frame in frames:
        yield frame
