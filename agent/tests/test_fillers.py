import asyncio

from livekit import rtc

from interview.fillers import ACKS, MAX_VOICED_SECONDS, FillerPlayer, _voiced_seconds, acks_for


def _frame(amplitude: int, seconds: float = 0.2, sr: int = 24000) -> rtc.AudioFrame:
    n = int(sr * seconds)
    data = (amplitude.to_bytes(2, "little", signed=True)) * n
    return rtc.AudioFrame(data, sr, 1, n)


def _player(probability: float = 1.0) -> FillerPlayer:
    player = FillerPlayer(tts=None, probability=probability)
    player._cache["mr-IN"] = {f"neutral:{t}": [_frame(3000)] for t in ACKS["mr-IN"]}
    return player


def test_a_repair_gets_no_receipt():
    assert _player().pick("mr-IN", "हो", kind="ask_repeat") is None


def test_receipts_are_one_word_and_not_every_question():
    player = _player()
    long = "मी पाच वर्षे ICU मध्ये काम केले"
    picks = [player.pick("mr-IN", long, kind="ask_field") for _ in range(6)]
    spoken = [p[0] for p in picks if p is not None]
    assert spoken
    assert set(spoken) <= set(ACKS["mr-IN"])
    assert all("," not in text for text in spoken)
    assert [p is None for p in picks] == [False, True, False, True, False, True]
    assert all(a != b for a, b in zip(spoken, spoken[1:]))
    assert "um" not in " ".join(acks_for("hi-IN")).lower()


def test_probability_zero_disables():
    assert _player(probability=0.0).pick("mr-IN", "मी पाच वर्षे ICU मध्ये काम केले", kind="ask_field") is None


def test_dragged_out_takes_are_rejected():
    # Neutral + empathetic texts for mr-IN (empathy falls back to hi forms for mr).
    n = len(acks_for("mr-IN", "neutral")) + len(acks_for("mr-IN", "empathetic"))
    takes = iter([[_frame(3000, seconds=3.0)], [_frame(3000, seconds=0.6)]] * n)
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
