"""ElevenLabs expressiveness engine: plain LLM text → ≤1 tone tag + pauses + rare um/sigh.

Chirp path does not use this module. Behind VOICE_EXPRESSIVENESS=engine.
"""

from __future__ import annotations

import random
import re
from collections.abc import AsyncIterable, AsyncIterator

from interview.fillers import is_speakable, normalize_fillers, um_for
from interview.voice_tone import tag_for_tone

_SENTENCE_END = re.compile(r"(?<!\.)[.?!।॥](?!\.)[\"')\]]*\s+")
_ANY_TAG = re.compile(r"\[[^\]]+\]")
_ELLIPSIS = re.compile(r"\s*\.\.\.\s*")

# Per-language forms. Only hi / mr / en marked reviewed; others fall back to hi/en.
REVIEWED_LANGS = frozenset({"hi-IN", "mr-IN", "en-IN"})

_SIGH: dict[str, str] = {
    "hi-IN": "आह, ",
    "mr-IN": "अरे, ",
    "en-IN": "[sighs] ",
}

_EMPATHY_WORDS = re.compile(
    r"\b(no|not|never|uncomfortable|scared|afraid|nervous|don'?t|cant|can'?t|"
    r"नहीं|नही|डरा|डर|परेशान|मुश्किल|"
    r"नाही|नको|भीती|अवघड)\b",
    re.I,
)


class ExpressivenessEngine:
    def __init__(
        self,
        *,
        sigh_rate: float = 0.15,
        umm_rate: float = 0.25,
        pause_rate: float = 0.55,
        cooldown_turns: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self.sigh_rate = sigh_rate
        self.umm_rate = umm_rate
        self.pause_rate = pause_rate
        self.cooldown_turns = max(0, cooldown_turns)
        self._rng = rng or random.Random()
        self._last_tag: str | None = None
        self._last_pause = False
        self._last_umm = False
        self._last_sigh = False
        self._turns_since_umm = 99
        self._turns_since_sigh = 99

    def _lang_forms(self, language: str) -> str:
        if language in REVIEWED_LANGS:
            return language
        return "en-IN" if (language or "").startswith("en") else "hi-IN"

    def strip_tags(self, text: str) -> str:
        return _ANY_TAG.sub("", text)

    def spoken_for_transcript(self, text: str) -> str:
        """What scoring / UI should store as `text` (tags removed for display; keep ellipses)."""
        return re.sub(r"[ \t]{2,}", " ", self.strip_tags(text)).strip()

    def _insert_pause(self, sentence: str, *, opening: bool, allow: bool) -> tuple[str, bool]:
        if not allow or self._last_pause and not opening:
            return sentence, False
        if "..." in sentence or "…" in sentence:
            return sentence, True
        # Prefer after first comma / first 4–8 words.
        words = sentence.split()
        if len(words) < 6:
            return sentence, False
        if self._rng.random() >= self.pause_rate and not opening:
            return sentence, False
        cut = min(len(words) - 2, max(3, len(words) // 2))
        # Don't split right after a tag remnant
        left = " ".join(words[:cut]).rstrip(",")
        right = " ".join(words[cut:])
        return f"{left}... {right}", True

    def _maybe_sigh(self, sentence: str, language: str, *, empathy: bool) -> tuple[str, bool]:
        if not empathy or self._turns_since_sigh < self.cooldown_turns:
            return sentence, False
        if self._rng.random() >= self.sigh_rate:
            return sentence, False
        form_lang = self._lang_forms(language)
        sigh = _SIGH.get(form_lang, _SIGH["hi-IN"])
        # Avoid stacking if LLM already wrote something similar
        if sentence.lstrip().startswith(("[sighs]", "आह", "अरे")):
            return sentence, False
        return f"{sigh}{sentence.lstrip()}", True

    def _shape_sentence(
        self,
        sentence: str,
        *,
        language: str,
        tone: str,
        first: bool,
        opening: bool,
        skip_first: bool,
        empathy: bool,
        allow_tag: bool,
        allow_umm: bool,
        allow_pause: bool,
    ) -> tuple[str, dict[str, bool]]:
        used = {"tag": False, "umm": False, "pause": False, "sigh": False}
        # Engine owns tags — strip any the LLM invented.
        sentence = self.strip_tags(sentence)
        if not sentence.strip():
            return sentence, used

        if first and not skip_first and not opening:
            sentence, used["sigh"] = self._maybe_sigh(sentence, language, empathy=empathy)

        # Um only mid-sentence, not on greeting / post-filler first sentence.
        can_um = allow_umm and not (first and (skip_first or opening)) and self._turns_since_umm >= self.cooldown_turns
        sentence, um_hit = normalize_fillers(sentence, language, allow_um=can_um)
        if um_hit:
            used["umm"] = True
        elif can_um and self._rng.random() < self.umm_rate and not opening:
            # Inject canonical um after first connector-ish chunk when LLM omitted it.
            parts = re.split(r"(,\s+)", sentence, maxsplit=1)
            if len(parts) == 3 and len(parts[0].split()) <= 4:
                sentence = f"{parts[0]}{parts[1]}{um_for(language)} {parts[2]}"
                used["umm"] = True

        sentence, used["pause"] = self._insert_pause(sentence, opening=opening, allow=allow_pause)

        if first and allow_tag and not skip_first:
            tag = tag_for_tone(tone)
            if tag and tag != self._last_tag:
                sentence = f"{tag} {sentence.lstrip()}"
                used["tag"] = True

        return sentence, used

    async def apply(
        self,
        text: AsyncIterable[str],
        *,
        language: str,
        tone: str = "neutral",
        opening: bool = False,
        skip_first: bool = False,
        empathy: bool = False,
    ) -> AsyncIterator[str]:
        buf = ""
        first = True
        tag_budget = 1
        pause_budget = 2 if opening else 1
        umm_budget = 1
        used_any = {"tag": False, "umm": False, "pause": False, "sigh": False}

        async for chunk in text:
            buf += chunk
            while (m := _SENTENCE_END.search(buf)) is not None:
                sentence, buf = buf[: m.end()], buf[m.end() :]
                shaped, used = self._shape_sentence(
                    sentence,
                    language=language,
                    tone=tone,
                    first=first,
                    opening=opening,
                    skip_first=skip_first,
                    empathy=empathy,
                    allow_tag=tag_budget > 0,
                    allow_umm=umm_budget > 0,
                    allow_pause=pause_budget > 0,
                )
                if used["tag"]:
                    tag_budget = 0
                    self._last_tag = tag_for_tone(tone)
                if used["umm"]:
                    umm_budget = 0
                if used["pause"]:
                    pause_budget = max(0, pause_budget - 1)
                for k, v in used.items():
                    used_any[k] = used_any[k] or v
                if is_speakable(self.strip_tags(shaped)):
                    first = False
                    yield shaped
        if buf.strip():
            shaped, used = self._shape_sentence(
                buf,
                language=language,
                tone=tone,
                first=first,
                opening=opening,
                skip_first=skip_first,
                empathy=empathy,
                allow_tag=tag_budget > 0,
                allow_umm=umm_budget > 0,
                allow_pause=pause_budget > 0,
            )
            for k, v in used.items():
                used_any[k] = used_any[k] or v
            if used["tag"]:
                self._last_tag = tag_for_tone(tone)
            if is_speakable(self.strip_tags(shaped)):
                yield shaped
        elif buf:
            yield buf

        self._turns_since_umm = 0 if used_any["umm"] else self._turns_since_umm + 1
        self._turns_since_sigh = 0 if used_any["sigh"] else self._turns_since_sigh + 1
        self._last_pause = used_any["pause"]
        self._last_umm = used_any["umm"]
        self._last_sigh = used_any["sigh"]


def filler_bucket_from_text(text: str, *, previous_empathy: bool = False) -> str:
    """Heuristic bucket for ack fillers — NOT Director (filler runs earlier)."""
    if previous_empathy or _EMPATHY_WORDS.search(text or ""):
        return "empathetic"
    return "neutral"
