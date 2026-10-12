"""Phrase-level pauses: turns breath points inside a sentence into Chirp pause tags.

People don't say a sentence in one unbroken run. They chunk it into phrases of ~3-7 words with a small gap
between. The LLM is asked to put commas at those points; this module converts them to real pauses and, for
long runs with no comma, adds a break at a grammatically safe spot (before a conjunction, or after a postposition
that closes a phrase). Pure text-to-text so it is deterministic to test; randomness only decides *whether* and
*how long*, so the rhythm never becomes a metronome.
"""

from __future__ import annotations

import random

MIN_WORDS_TO_PACE = 5
MIN_WORDS_PER_PHRASE = 2  # never leave a 1-word fragment on either side of a pause
LONG_RUN_WORDS = 8  # a run longer than this gets a break even without a comma
MAX_PAUSES_PER_SENTENCE = 3

SHORT_PAUSE = "[pause short]"
MEDIUM_PAUSE = "[pause]"
MEDIUM_PAUSE_CHANCE = 0.2
COMMA_TAG_CHANCE = 0.55

_COMMA_ENDINGS = (",", "،", ";", ":", "—", "–")
_PAUSE_ALREADY = ("...", "…")

# Words that start a new phrase: a pause just before them sounds natural.
CONJUNCTIONS: dict[str, frozenset[str]] = {
    "hi-IN": frozenset({"और", "लेकिन", "मगर", "क्योंकि", "जब", "फिर", "या", "इसलिए", "जैसे", "वरना"}),
    "mr-IN": frozenset({"आणि", "पण", "परंतु", "कारण", "जेव्हा", "मग", "किंवा", "म्हणजे", "तरी"}),
    "ta-IN": frozenset({"ஆனால்", "மற்றும்", "அப்புறம்", "அதனால்", "பிறகு", "இல்லனா"}),
    "te-IN": frozenset({"కానీ", "మరియు", "అప్పుడు", "ఎందుకంటే", "తర్వాత", "అలాగే"}),
    "kn-IN": frozenset({"ಆದರೆ", "ಮತ್ತು", "ನಂತರ", "ಯಾಕೆಂದರೆ", "ಹಾಗಾದರೆ"}),
    "ml-IN": frozenset({"പക്ഷേ", "പിന്നെ", "എന്നാൽ", "കാരണം", "അതുകൊണ്ട്"}),
    "bn-IN": frozenset({"কিন্তু", "এবং", "আর", "কারণ", "তারপর", "অথবা"}),
    "gu-IN": frozenset({"પણ", "અને", "પછી", "અથવા", "તેથી"}),
    "pa-IN": frozenset({"ਪਰ", "ਅਤੇ", "ਕਿਉਂਕਿ", "ਫਿਰ", "ਜਾਂ"}),
    "en-IN": frozenset({"and", "but", "so", "because", "when", "then", "or", "which"}),
}

# Words that close a phrase: a pause just after them is safe (e.g. "अपने काम के बारे में | बताइए").
PHRASE_CLOSERS: dict[str, frozenset[str]] = {
    "hi-IN": frozenset({"में", "से", "पर", "तक", "लिए", "साथ", "बारे"}),
    "mr-IN": frozenset({"मध्ये", "साठी", "पासून", "बद्दल", "सोबत", "मधे"}),
    "ta-IN": frozenset({"பற்றி", "கூட", "வரை"}),
    "te-IN": frozenset({"గురించి", "తో", "వరకు"}),
    "kn-IN": frozenset({"ಬಗ್ಗೆ", "ಜೊತೆ", "ವರೆಗೆ"}),
    "ml-IN": frozenset({"കുറിച്ച്", "കൂടെ", "വരെ"}),
    "bn-IN": frozenset({"সম্পর্কে", "জন্য", "সাথে", "পর্যন্ত"}),
    "gu-IN": frozenset({"વિશે", "માટે", "સાથે", "સુધી"}),
    "pa-IN": frozenset({"ਬਾਰੇ", "ਲਈ", "ਨਾਲ", "ਤੱਕ"}),
    "en-IN": frozenset(),
}


def _bare(word: str) -> str:
    return word.strip(".,;:!?।॥…\"'()[]—–،").lower()


def _candidates(words: list[str], language: str) -> list[tuple[int, int]]:
    """Break points as (index of the word to pause AFTER, priority); lower priority number = stronger."""
    conj = CONJUNCTIONS.get(language, frozenset())
    closers = PHRASE_CLOSERS.get(language, frozenset())
    n = len(words)
    found: dict[int, int] = {}

    # 1) Commas the LLM wrote are the strongest signal of an intended breath.
    for i, w in enumerate(words[:-1]):
        if w.endswith(_PAUSE_ALREADY):
            continue
        if w.endswith(_COMMA_ENDINGS):
            found[i] = 0

    # 2) A conjunction after a few words starts a new phrase.
    for i in range(1, n):
        if _bare(words[i]) in conj and i - 1 not in found and not words[i - 1].endswith(_PAUSE_ALREADY):
            found[i - 1] = 1

    # 3) Long runs with no break get one at a phrase-closing word closest to the middle of the run.
    marks = sorted(found)
    bounds = [-1, *marks, n - 1]
    for start, end in zip(bounds, bounds[1:]):
        run = end - start
        if run <= LONG_RUN_WORDS:
            continue
        mid = (start + end) / 2
        options = [
            i
            for i in range(start + MIN_WORDS_PER_PHRASE + 1, end - MIN_WORDS_PER_PHRASE)
            if _bare(words[i]) in closers and not words[i].endswith(_COMMA_ENDINGS + _PAUSE_ALREADY)
        ]
        if options:
            found[min(options, key=lambda i: abs(i - mid))] = 2

    # Keep each side of a pause long enough. A comma after a one-word opener ("अच्छा, ...") is a natural beat,
    # so the LLM's own commas may follow a single word; computed breaks need a full phrase before them.
    def _ok(i: int, priority: int) -> bool:
        before = i + 1
        after = n - before
        return after >= MIN_WORDS_PER_PHRASE and before >= (1 if priority == 0 else MIN_WORDS_PER_PHRASE)

    return sorted((i, p) for i, p in found.items() if _ok(i, p))


def pace_sentence(sentence: str, language: str, rate: float, rng: random.Random) -> str:
    """Insert pause tags at phrase boundaries. Leaves the text untouched if nothing qualifies."""
    if rate <= 0:
        return sentence
    stripped = sentence.strip()
    words = stripped.split()
    if len(words) < MIN_WORDS_TO_PACE:
        return sentence

    # Chirp already pauses ~0.35s at a written comma; stacking a tag on every one makes speech sluggish
    # (measured: +30% duration in Marathi). Commas get a tag only sometimes; computed breaks always may.
    picked = [
        (i, p)
        for i, p in _candidates(words, language)
        if rng.random() < (rate * COMMA_TAG_CHANCE if p == 0 else rate)
    ]
    if len(picked) > MAX_PAUSES_PER_SENTENCE:
        # Drop the weakest first (highest priority number), never the LLM's own commas unless forced.
        picked = sorted(sorted(picked, key=lambda x: x[1])[:MAX_PAUSES_PER_SENTENCE])
    if not picked:
        return sentence

    for i, _ in picked:
        tag = MEDIUM_PAUSE if rng.random() < MEDIUM_PAUSE_CHANCE else SHORT_PAUSE
        words[i] = f"{words[i]} {tag}"

    lead = sentence[: len(sentence) - len(sentence.lstrip())]
    trail = sentence[len(sentence.rstrip()) :]
    return f"{lead}{' '.join(words)}{trail}"
