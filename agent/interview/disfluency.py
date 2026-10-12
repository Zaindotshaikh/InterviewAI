"""Shapes the LLM's reply for TTS: clean fillers, then add breath pauses.

Only the spoken audio changes; the transcript and chat history keep the LLM's text.
Filler policy lives in interview.fillers. This layer never invents a filler at a random spot: the LLM
places "umm," where a person would hesitate, and this keeps at most one per reply.
"""

from __future__ import annotations

import random
import re
from collections.abc import AsyncIterable, AsyncIterator

from interview.fillers import is_speakable, normalize_fillers
from interview.pacing import pace_sentence

_NO_PAUSE_TAG_LOCALES = {"pa-IN"}

_SENTENCE_END = re.compile(r"(?<!\.)[.?!।॥](?!\.)[\"')\]]*\s+")
# The um's own commas already pause; a tag next to it doubles the gap (and adjacent tags garble Chirp).
_TAG_BEFORE_UM = re.compile(r"\s*\[pause[^\]]*\]\s*(um+,)")
_TAG_AFTER_UM = re.compile(r"(um+,)\s*\[pause[^\]]*\]")


class Disfluency:
    def __init__(
        self,
        rate: float,
        use_pause_tags: bool,
        rng: random.Random | None = None,
        phrase_pause_rate: float = 0.0,
    ) -> None:
        # rate: chance an LLM-written um is spoken (0 = never speak one).
        self.rate = rate
        self.phrase_pause_rate = phrase_pause_rate
        self.use_pause_tags = use_pause_tags
        self._rng = rng or random.Random()

    def _shape(self, sentence: str, language: str, *, allow_um: bool) -> tuple[str, bool]:
        sentence, used = normalize_fillers(sentence, language, allow_um=allow_um)
        if self.use_pause_tags and language not in _NO_PAUSE_TAG_LOCALES:
            sentence = pace_sentence(sentence, language, self.phrase_pause_rate, self._rng)
            if used:
                sentence = _TAG_AFTER_UM.sub(r"\1", _TAG_BEFORE_UM.sub(r" \1", sentence))
        return sentence, used

    async def apply(
        self,
        text: AsyncIterable[str],
        language: str,
        skip_first: bool = False,
        opening: bool = False,
    ) -> AsyncIterator[str]:
        """Rewrite a streamed LLM reply sentence by sentence.

        skip_first: a reaction was just played, so the first sentence gets no um.
        opening: the greeting must start with the greeting itself, so no um anywhere in it.
        Buffering to a sentence boundary adds no latency: the TTS plugin's sentence tokenizer waits for it anyway.
        """
        um_left = not opening and self.rate > 0 and self._rng.random() < self.rate
        buf = ""
        first = True

        def shape(sentence: str) -> str:
            nonlocal um_left, first
            allow = um_left and not (first and skip_first)
            shaped, used = self._shape(sentence, language, allow_um=allow)
            if used:
                um_left = False
            if is_speakable(shaped):
                first = False
            return shaped

        async for chunk in text:
            buf += chunk
            while (m := _SENTENCE_END.search(buf)) is not None:
                sentence, buf = buf[: m.end()], buf[m.end() :]
                shaped = shape(sentence)
                if is_speakable(shaped):
                    yield shaped
        if buf.strip():
            shaped = shape(buf)
            if is_speakable(shaped):
                yield shaped
        elif buf:
            yield buf
