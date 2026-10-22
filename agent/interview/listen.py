"""What the interviewer should act on.

Two rules, the way a person runs a noisy phone call:

* Sounds that are not words (a fan, a cough, "uh", a TV hum the transcriber could not
  turn into language) are not an answer. Ignore them and keep going.
* Real words are the candidate. Once those words stop changing, the turn is over
  even if the room is still noisy.
"""

from __future__ import annotations

import re
import unicodedata

# Sounds and transcriber leftovers. Real words ("okay", "haan", "पुणे", "yes") are not in here.
_NON_WORDS = {
    "uh",
    "um",
    "umm",
    "hm",
    "hmm",
    "hmmm",
    "ah",
    "ahh",
    "er",
    "err",
    "mm",
    "mmm",
    "mhm",
    "mh",
    "huh",
    "ugh",
    "ohh",
    "ahem",
    "हम्म",
    "हम्म्म",
    "उम्म",
    "अह",
    "अं",
}

_NOISE_LABEL = re.compile(
    r"[\(\[\{<][^\)\]\}>]{0,40}[\)\]\}>]",
)


def _tokens(text: str) -> list[str]:
    """Letters, digits, and the vowel signs that belong to them.

    Python's ``\\w`` splits Devanagari ``पुणे`` into single letters because the
    vowel signs are marks, not word characters. A person hears that as one word.
    """
    tokens: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isdigit() or cat.startswith("L"):
            buf.append(ch)
        elif cat.startswith("M") and buf:
            buf.append(ch)
        else:
            flush()
    flush()
    return tokens


def is_candidate_speech(text: str | None) -> bool:
    """True when the transcript contains real words or digits, not just noise."""
    raw = _NOISE_LABEL.sub(" ", text or "")
    raw = raw.replace("…", " ").replace("\ufffd", " ")
    tokens = _tokens(raw)
    if not tokens:
        return False
    for tok in tokens:
        if tok.lower() in _NON_WORDS:
            continue
        if any(ch.isdigit() for ch in tok):
            return True
        letters = [ch for ch in tok if unicodedata.category(ch).startswith("L")]
        # One base letter plus its vowel sign is still a word. A bare "a" is not.
        if len(letters) >= 2 or (letters and len(tok) >= 2):
            return True
    return False


def looks_finished(text: str) -> bool:
    """The candidate landed the sentence, rather than stopping mid-thought."""
    stripped = (text or "").rstrip()
    return stripped.endswith((".", "?", "!", "।", "॥", "？"))


class ListenFloor:
    """Closes a turn from the words, not from the room staying loud.

    ``commit`` — words have stopped; take the answer.
    ``release`` — only noise was heard; drop the turn and keep waiting.
    ``wait`` — still their turn, or the interviewer is the one talking.
    """

    def __init__(self) -> None:
        self._speech_started: float | None = None
        self._words = ""
        self._words_at: float | None = None

    def note_agent_busy(self) -> None:
        """Interviewer is speaking, or this open listen was just resolved."""
        self._speech_started = None
        self._words = ""
        self._words_at = None

    def note_speech_start(self, now: float) -> None:
        if self._speech_started is None:
            self._speech_started = now

    def note_transcript(self, text: str, now: float) -> None:
        cleaned = (text or "").strip()
        if not is_candidate_speech(cleaned):
            return
        if cleaned != self._words:
            self._words = cleaned
            self._words_at = now
        if self._speech_started is None:
            self._speech_started = now

    def decide(
        self,
        now: float,
        *,
        user_speaking: bool,
        min_hold: float,
        max_hold: float,
    ) -> str:
        # VAD already went quiet: the normal endpointing path will close the turn.
        if not user_speaking:
            return "wait"
        # A period in the transcript is not the end of the thought. Scribe often
        # puts "पुणे." or "911, 2323." in the middle of a sentence while the
        # candidate is still talking. Closing there splits one answer into two
        # turns and the tail gets scored as the next question. While the mic
        # still hears them, close only after the words have sat still for
        # max_hold (the room is stuck on noise). A quiet room is closed by
        # endpointing, which already uses min_hold.
        _ = min_hold
        if self._words and self._words_at is not None:
            stable = now - self._words_at
            if stable >= max_hold:
                return "commit"
            return "wait"
        if self._speech_started is not None and now - self._speech_started >= max_hold:
            return "release"
        return "wait"

    def take(self) -> str:
        words = self._words
        self.note_agent_busy()
        return words
