"""Human-sounding fillers, all spoken by the interview voice itself.

Two moments where people naturally fill speech, and only these:
  1. Turn start: right after the candidate finishes, a short listening reaction ("अच्छा, अच्छा.",
     "Right, okay.") while the reply is prepared. Pre-rendered with the interview TTS (same voice and
     accent), trimmed of silence, and played at once. The reply queues behind it; it is never cut.
  2. Mid-sentence: one "umm," where the speaker searches for the next words. The expressiveness engine
     adds it; normalize_fillers() makes any LLM-written form canonical, keeps at most one, and removes
     vowel moans.

The reaction plays before the Director has decided the move, so it must fit every move: persuade,
re-ask, a read-back and the close. Only listening tokens qualify ("I see", "okay"). Words that grade
or confirm the answer ("बढ़िया", "ठीक है", "समझ गई", "got it") are excluded; they also carry the
speaker's gender in several languages.

A standalone "Um" clip is what Chirp stretched into a moan; inside a sentence, with a comma on each
side, the Indic voices say it short (eval/filler_probe.py: +0.5s in mr-IN).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import AsyncIterable, AsyncIterator
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("interview-v2.fillers")

if TYPE_CHECKING:
    from livekit import rtc

# Canonical in-sentence filled pause. Latin script in every language: the probe found it the most
# consistent take-to-take in Marathi and Hindi.
INDIC_UM = "umm,"
ENGLISH_UM = "um,"

# Turn-start listening reactions. Real words only (bare vowels like "आ" or "हम्म" moaned). Two words
# each: Chirp streams a lone word as silence. Period, not ellipsis, so the voice does not drag.
# A language missing here gets no reaction: silence is better than a word in the wrong language.
ACKS: dict[str, list[str]] = {
    "hi-IN": ["अच्छा, अच्छा.", "हाँ जी, अच्छा.", "अच्छा, ओके.", "जी, अच्छा."],
    "mr-IN": ["बरं, बरं.", "हो, बरं.", "अच्छा, बरं.", "बरं, ओके."],
    "gu-IN": ["અચ્છા, અચ્છા.", "હા, અચ્છા.", "અચ્છા, ઓકે."],
    "ta-IN": ["சரி, சரி.", "ஓகே, சரி.", "அப்படியா, சரி."],
    "te-IN": ["సరే, సరే.", "ఓకే, సరే.", "అవునా, సరే."],
    "kn-IN": ["ಸರಿ, ಸರಿ.", "ಓಕೆ, ಸರಿ.", "ಹೌದಾ, ಸರಿ."],
    "ml-IN": ["ശരി, ശരി.", "ഓക്കെ, ശരി.", "ആണോ, ശരി."],
    "bn-IN": ["আচ্ছা, আচ্ছা.", "হ্যাঁ, আচ্ছা.", "আচ্ছা, ওকে."],
    "pa-IN": ["ਅੱਛਾ, ਅੱਛਾ.", "ਹਾਂ ਜੀ, ਅੱਛਾ.", "ਅੱਛਾ, ਓਕੇ."],
    "od-IN": ["ଆଚ୍ଛା, ଆଚ୍ଛା.", "ହଁ, ଆଚ୍ଛା.", "ଆଚ୍ଛା, ଓକେ."],
    "en-IN": ["Right, okay.", "I see, okay.", "Okay, right.", "Mm, okay."],
}

# Opening acknowledgements the reply LLM tends to write. After a played reaction they are a second
# "okay" in a row, so the reply loses them. Lower-case; matched only when punctuation follows.
_LEAD_ACKS: dict[str, tuple[str, ...]] = {
    "hi-IN": ("हाँ जी", "हां जी", "अच्छा", "ठीक है", "बढ़िया", "हाँ", "हां", "जी", "ओके", "okay"),
    "mr-IN": ("ठीक आहे", "बरं", "छान", "अच्छा", "हो", "ओके", "okay"),
    "gu-IN": ("ઠીક છે", "સારું", "અચ્છા", "બરાબર", "ઓકે", "હા", "okay"),
    "ta-IN": ("சரி", "ஓகே", "நல்லது", "அப்படியா", "okay"),
    "te-IN": ("సరే", "ఓకే", "బాగుంది", "అవునా", "okay"),
    "kn-IN": ("ಸರಿ", "ಓಕೆ", "ಚೆನ್ನಾಗಿದೆ", "ಹೌದಾ", "okay"),
    "ml-IN": ("ശരി", "ഓക്കെ", "നല്ലത്", "ആണോ", "okay"),
    "bn-IN": ("ঠিক আছে", "আচ্ছা", "ওকে", "বেশ", "হ্যাঁ", "okay"),
    "pa-IN": ("ਠੀਕ ਹੈ", "ਹਾਂ ਜੀ", "ਅੱਛਾ", "ਓਕੇ", "ਵਧੀਆ", "okay"),
    "od-IN": ("ଠିକ ଅଛି", "ଆଚ୍ଛା", "ଓକେ", "ହଁ", "okay"),
    "en-IN": ("okay", "ok", "got it", "alright", "all right", "right", "i see", "sure", "great", "nice",
              "thanks", "thank you", "mm"),
}

MIN_WORDS_FOR_FILLER = 4
MIN_VOICED_SECONDS = 0.15
MAX_VOICED_SECONDS = 1.6  # two short words measure ~0.6-1.4s; longer means the voice dragged them
MAX_RENDER_ATTEMPTS = 4
# Rotation memory: a reaction is not reused within this many picks.
_NO_REPEAT = 2

# 20ms analysis windows; RMS above this is speech in a quiet room.
_WINDOW_S = 0.02
_VOICE_RMS = 300
# Silence kept around the trimmed take so the word onset and tail are not clipped.
_PAD_HEAD_S = 0.04
_PAD_TAIL_S = 0.08


def um_for(language: str) -> str:
    return ENGLISH_UM if language.startswith("en") else INDIC_UM


def acks_for(language: str) -> list[str]:
    """Reviewed reactions for this language; an empty list means stay silent."""
    if language in ACKS:
        return ACKS[language]
    if (language or "").startswith("en"):
        return ACKS["en-IN"]
    return []


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


# --- no second "okay" after a played reaction ------------------------------------------------------

# An ack word only counts when a pause mark follows it ("अच्छा, तो..." yes; "ठीक है आप..." no).
_ACK_TAIL = r"\s*(?:\.\.\.|…|[,.!।॥])+\s*"
_LEAD_PATTERNS: dict[str, re.Pattern[str]] = {}
_SETTLED = re.compile(r"[.?!।॥](?:[\"')\]]*)(?:\s|$)")
_SETTLE_CHARS = 80


def _lead_pattern(language: str) -> re.Pattern[str] | None:
    lang = language if language in _LEAD_ACKS else ("en-IN" if (language or "").startswith("en") else "")
    if not lang:
        return None
    if lang not in _LEAD_PATTERNS:
        words = sorted(_LEAD_ACKS[lang], key=len, reverse=True)
        alts = "|".join(re.escape(w) for w in words)
        _LEAD_PATTERNS[lang] = re.compile(rf"^\s*(?:{alts})(?!{_L}){_ACK_TAIL}", re.IGNORECASE)
    return _LEAD_PATTERNS[lang]


def strip_lead_ack(text: str, language: str) -> str:
    """Drop acknowledgement words at the very start of a reply. Returns "" if nothing else is left."""
    pattern = _lead_pattern(language)
    if pattern is None:
        return text
    rest = text
    for _ in range(3):
        m = pattern.match(rest)
        if m is None:
            break
        rest = rest[m.end() :]
    if rest is text:
        return text
    if not is_speakable(rest):
        return ""
    if language.startswith("en") and rest[:1].islower():
        rest = rest[:1].upper() + rest[1:]
    return rest


async def drop_lead_ack(text: AsyncIterable[str], language: str) -> AsyncIterator[str]:
    """Stream filter: strip a leading acknowledgement from the reply, then pass everything through.

    Holds text only until the first sentence is complete. If the whole reply was an acknowledgement,
    it is spoken as written rather than leaving the candidate in silence.
    """
    original = ""
    buf = ""
    released = False
    async for chunk in text:
        if released:
            yield chunk
            continue
        original += chunk
        buf += chunk
        if not (_SETTLED.search(buf) or len(buf) >= _SETTLE_CHARS):
            continue
        rest = strip_lead_ack(buf, language)
        if rest:
            released = True
            yield rest
        buf = ""
    if released:
        return
    rest = strip_lead_ack(buf, language) if buf else ""
    if rest:
        yield rest
    elif original:
        yield original


# --- turn-start reaction player ------------------------------------------------------------------


def _samples(frames: list[rtc.AudioFrame]):  # noqa: ANN202
    import numpy as np  # local: keeps unit tests free of LiveKit/numpy

    return np.concatenate([np.frombuffer(f.data, dtype=np.int16) for f in frames])


def _window_rms(audio: Any, sr: int, channels: int):  # noqa: ANN202
    import numpy as np

    win = max(1, int(sr * _WINDOW_S)) * channels
    n = len(audio) // win
    if n == 0:
        return np.zeros(0), win
    rms = np.sqrt((audio[: n * win].astype(np.float32).reshape(n, win) ** 2).mean(axis=1))
    return rms, win


def _voiced_seconds(frames: list[rtc.AudioFrame]) -> float:
    """Seconds of audible speech, in 20ms windows above a quiet-room RMS floor."""
    if not frames:
        return 0.0
    rms, _win = _window_rms(_samples(frames), frames[0].sample_rate, frames[0].num_channels)
    return float((rms > _VOICE_RMS).sum()) * _WINDOW_S


def _trim_silence(frames: list[rtc.AudioFrame]) -> list[rtc.AudioFrame]:
    """Cut the TTS lead-in and tail silence so the reaction starts at once and the reply follows tight."""
    from livekit import rtc

    if not frames:
        return frames
    sr, channels = frames[0].sample_rate, frames[0].num_channels
    audio = _samples(frames)
    rms, win = _window_rms(audio, sr, channels)
    voiced = (rms > _VOICE_RMS).nonzero()[0]
    if len(voiced) == 0:
        return frames
    per_sample = channels
    start = max(0, int(voiced[0]) * win - int(sr * _PAD_HEAD_S) * per_sample)
    end = min(len(audio), (int(voiced[-1]) + 1) * win + int(sr * _PAD_TAIL_S) * per_sample)
    clip = audio[start:end]
    step = int(sr * _WINDOW_S) * per_sample
    out: list[rtc.AudioFrame] = []
    for i in range(0, len(clip), step):
        part = clip[i : i + step]
        out.append(rtc.AudioFrame(part.tobytes(), sr, channels, len(part) // channels))
    return out


class FillerPlayer:
    """Pre-renders turn-start reactions with the interview voice so playback starts instantly."""

    def __init__(self, tts: Any, probability: float, *, rng: random.Random | None = None) -> None:
        self._tts = tts
        self._probability = probability
        self._rng = rng or random.Random()
        self._cache: dict[str, dict[str, list[rtc.AudioFrame]]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._recent: list[str] = []

    def prepare(self, language: str) -> None:
        if self._tts is None or self._probability <= 0 or language in self._tasks or not acks_for(language):
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
                    rendered[text] = _trim_silence(frames)
                    break
        if len(rendered) < len(acks_for(language)):
            logger.warning("fillers rendered %s/%s for %s", len(rendered), len(acks_for(language)), language)
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
        said = (candidate_text or "").strip()
        if len(said.split()) < MIN_WORDS_FOR_FILLER:
            return None
        # They asked us something: a person answers it straight away, without "I see".
        if said.rstrip("\"') ").endswith(("?", "؟")):
            return None
        if self._rng.random() >= self._probability:
            return None
        rendered = self._cache.get(language)
        if not rendered:
            self.prepare(language)
            return None
        options = [t for t in rendered if t not in self._recent] or list(rendered)
        text = self._rng.choice(options)
        self._recent = (self._recent + [text])[-_NO_REPEAT:]
        return text, rendered[text]


async def frames_iter(frames: list[rtc.AudioFrame]):
    for frame in frames:
        yield frame
