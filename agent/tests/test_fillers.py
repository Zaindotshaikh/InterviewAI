import asyncio
import random
import re

from livekit import rtc

from interview.fillers import (
    ACKS,
    MAX_VOICED_SECONDS,
    FillerPlayer,
    _trim_silence,
    _voiced_seconds,
    acks_for,
    drop_lead_ack,
    strip_lead_ack,
)


def _frame(amplitude: int, seconds: float = 0.2, sr: int = 24000) -> rtc.AudioFrame:
    n = int(sr * seconds)
    data = (amplitude.to_bytes(2, "little", signed=True)) * n
    return rtc.AudioFrame(data, sr, 1, n)


def _player(probability: float = 1.0, language: str = "mr-IN") -> FillerPlayer:
    player = FillerPlayer(tts=None, probability=probability, rng=random.Random(0))
    player._cache[language] = {t: [_frame(3000)] for t in ACKS[language]}
    return player


LONG_MR = "मी पाच वर्षे ICU मध्ये काम केले"


def test_short_answers_get_no_reaction():
    assert _player().pick("mr-IN", "हो") is None


def test_a_question_from_the_candidate_gets_no_reaction():
    assert _player().pick("mr-IN", "पगार किती आहे या नोकरीसाठी?") is None


def test_reactions_rotate_without_repeats():
    player = _player()
    picks = [player.pick("mr-IN", LONG_MR)[0] for _ in range(12)]
    assert set(picks) <= set(ACKS["mr-IN"])
    assert all(a != b for a, b in zip(picks, picks[1:]))
    assert all(a != c for a, c in zip(picks, picks[2:]))


def test_probability_zero_disables():
    assert _player(probability=0.0).pick("mr-IN", LONG_MR) is None


def test_every_language_has_its_own_reactions():
    for lang in ("hi-IN", "mr-IN", "gu-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "bn-IN", "pa-IN", "od-IN", "en-IN"):
        assert acks_for(lang), lang
    # An unknown language stays silent instead of borrowing Hindi.
    assert acks_for("xx-IN") == []


def test_reactions_never_judge_confirm_or_carry_gender():
    banned = re.compile(r"गई|गया|ਗਈ|ਗਿਆ|शकते|सकती|सकता|ठीक है|बढ़िया|समझ|समज|got it|great|nice|sure", re.I)
    for lang, acks in ACKS.items():
        for text in acks:
            assert not banned.search(text), (lang, text)
            assert "um" not in text.lower()


def test_dragged_out_takes_are_rejected():
    n = len(acks_for("mr-IN"))
    takes = iter([[_frame(3000, seconds=3.0)], [_frame(3000, seconds=0.6)]] * n)
    player = FillerPlayer(tts=object(), probability=1.0)

    async def fake_synthesize(_text):
        return next(takes)

    player._synthesize = fake_synthesize
    asyncio.run(player._render("mr-IN"))
    assert len(player._cache["mr-IN"]) == n
    for frames in player._cache["mr-IN"].values():
        assert _voiced_seconds(frames) <= MAX_VOICED_SECONDS


def test_silent_takes_are_not_counted_as_speech():
    assert _voiced_seconds([_frame(10)]) == 0.0
    assert _voiced_seconds([_frame(3000)]) > 0.15


def test_lead_and_tail_silence_are_trimmed():
    take = [_frame(0, seconds=0.3), _frame(3000, seconds=0.5), _frame(0, seconds=0.4)]
    trimmed = _trim_silence(take)
    total = sum(f.samples_per_channel for f in trimmed) / 24000
    assert 0.5 <= total <= 0.65
    assert abs(_voiced_seconds(trimmed) - _voiced_seconds(take)) < 0.03


def test_strip_lead_ack_removes_a_second_okay():
    assert strip_lead_ack("अच्छा, तो अभी आप कहाँ काम करते हैं?", "hi-IN") == "तो अभी आप कहाँ काम करते हैं?"
    assert strip_lead_ack("हाँ जी, ठीक है। आप night shift कर सकते हैं?", "hi-IN") == "आप night shift कर सकते हैं?"
    assert strip_lead_ack("Okay, got it. Where are you working now?", "en-IN") == "Where are you working now?"
    assert strip_lead_ack("Right, so where do you work?", "en-IN") == "So where do you work?"


def test_strip_lead_ack_keeps_real_words():
    # No pause after the word: it is part of the sentence, not a reaction.
    assert strip_lead_ack("ठीक है आप कल join कर सकते हैं?", "hi-IN") == "ठीक है आप कल join कर सकते हैं?"
    assert strip_lead_ack("Okay? Let me repeat that.", "en-IN") == "Okay? Let me repeat that."
    assert strip_lead_ack("Rightly so, where do you work?", "en-IN") == "Rightly so, where do you work?"
    assert strip_lead_ack("अच्छा,", "xx-IN") == "अच्छा,"


async def _collect(chunks, language):
    async def gen():
        for c in chunks:
            yield c

    return "".join([c async for c in drop_lead_ack(gen(), language)])


def test_drop_lead_ack_streams_across_chunks():
    out = asyncio.run(_collect(["अच्छा", ", ", "तो आप", " कहाँ काम करते हैं? ", "बताइए।"], "hi-IN"))
    assert out == "तो आप कहाँ काम करते हैं? बताइए।"


def test_drop_lead_ack_skips_an_ack_only_first_sentence():
    out = asyncio.run(_collect(["Okay. ", "Where are you working now?"], "en-IN"))
    assert out == "Where are you working now?"


def test_drop_lead_ack_never_leaves_silence():
    assert asyncio.run(_collect(["Okay."], "en-IN")) == "Okay."
