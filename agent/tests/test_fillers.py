import asyncio

from livekit import rtc

from interview.fillers import ACKS, MAX_VOICED_SECONDS, FillerPlayer, _voiced_seconds, acks_for


def _frame(amplitude: int, seconds: float = 0.2, sr: int = 24000) -> rtc.AudioFrame:
    n = int(sr * seconds)
    data = (amplitude.to_bytes(2, "little", signed=True)) * n
    return rtc.AudioFrame(data, sr, 1, n)


def _player(probability: float = 1.0) -> FillerPlayer:
    player = FillerPlayer(tts=None, probability=probability)
    player._cache["mr-IN"] = {t: [_frame(3000)] for t in ACKS["mr-IN"]}
    return player


def test_short_answers_get_no_reaction():
    assert _player().pick("mr-IN", "हो") is None


def test_reactions_are_native_words_and_rotate():
    player = _player()
    picks = [player.pick("mr-IN", "मी पाच वर्षे ICU मध्ये काम केले")[0] for _ in range(6)]
    assert set(picks) <= set(ACKS["mr-IN"])
    assert all(a != b for a, b in zip(picks, picks[1:]))
    assert "um" not in " ".join(acks_for("hi-IN")).lower()


def test_probability_zero_disables():
    assert _player(probability=0.0).pick("mr-IN", "मी पाच वर्षे ICU मध्ये काम केले") is None


def test_dragged_out_takes_are_rejected():
    takes = iter([[_frame(3000, seconds=3.0)], [_frame(3000, seconds=0.6)]] * len(ACKS["mr-IN"]))
    player = FillerPlayer(tts=object(), probability=1.0)

    async def fake_synthesize(_text):
        return next(takes)

    player._synthesize = fake_synthesize
    asyncio.run(player._render("mr-IN"))
    assert player._cache["mr-IN"]
    for frames in player._cache["mr-IN"].values():
        assert _voiced_seconds(frames) <= MAX_VOICED_SECONDS


def test_silent_takes_are_not_counted_as_speech():
    assert _voiced_seconds([_frame(10)]) == 0.0
    assert _voiced_seconds([_frame(3000)]) > 0.15
