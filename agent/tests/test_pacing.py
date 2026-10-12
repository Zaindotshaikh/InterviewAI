import asyncio
import random

from interview.disfluency import Disfluency
from interview.pacing import MAX_PAUSES_PER_SENTENCE, pace_sentence


def _pace(text, lang="hi-IN", rate=1.0, seed=0):
    return pace_sentence(text, lang, rate, random.Random(seed))


def test_comma_becomes_a_pause_and_text_is_otherwise_unchanged():
    text = "अच्छा, आप अभी कहाँ काम कर रही हैं?"
    outs = [_pace(text, seed=s) for s in range(50)]
    # Commas already pause in the voice, so the tag is added only some of the time (never always, never never).
    with_tag = sum("अच्छा, [pause" in o for o in outs)
    assert 0 < with_tag < 50
    for o in outs:
        assert o.replace(" [pause short]", "").replace(" [pause]", "") == text


def test_break_before_conjunction_without_comma():
    out = _pace("आप ICU में काम करती हैं और night shift भी करती हैं?")
    assert "हैं [pause" in out and "और night" in out


def test_long_run_gets_a_break_after_a_phrase_closing_word():
    out = _pace("आप अपने पिछले hospital के काम के बारे में मुझे थोड़ा विस्तार से बताइए")
    assert "[pause" in out
    assert out.split("[pause")[0].split()[-1] in {"में", "से", "पर", "तक", "लिए", "साथ", "बारे"}


def test_short_sentences_and_zero_rate_are_untouched():
    assert _pace("हाँ जी, ठीक है।") == "हाँ जी, ठीक है।"
    assert _pace("अच्छा, आप कहाँ काम करती हैं?", rate=0.0) == "अच्छा, आप कहाँ काम करती हैं?"


def test_never_more_than_cap_and_no_one_word_fragments():
    text = "तो, आप पहले, फिर दूसरे, और तीसरे, लेकिन चौथे, और पाँचवें hospital में काम करती हैं"
    for seed in range(20):
        out = _pace(text, seed=seed)
        assert out.count("[pause") <= MAX_PAUSES_PER_SENTENCE
        assert not out.rstrip().endswith("]")


def test_trailing_whitespace_preserved_and_existing_ellipsis_not_doubled():
    assert _pace("आप अभी कहाँ काम कर रही हैं? ").endswith("हैं? ")
    out = _pace("तो... आप अभी कहाँ काम कर रही हैं?")
    assert "... [pause" not in out


def test_pause_lengths_vary_across_sentences():
    short = medium = 0
    for seed in range(100):
        out = _pace("अच्छा, आप अभी कहाँ काम कर रही हैं?", seed=seed)
        short += "[pause short]" in out
        medium += "[pause]" in out
    assert short > medium > 0  # mostly short, sometimes longer


def test_works_for_every_language_without_error():
    for lang in ("mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "en-IN", "hi-IN"):
        _pace("one two three, four five six seven eight nine ten eleven and twelve", lang)


async def _stream(chunks):
    for c in chunks:
        yield c


def _apply(d, chunks, lang="hi-IN", **kw):
    async def run():
        return [s async for s in d.apply(_stream(chunks), lang, **kw)]

    return asyncio.run(run())


def test_disfluency_applies_pacing_only_when_markup_is_available():
    chunks = ["आप ICU में काम करती हैं और night shift भी करती हैं? "]
    on = _apply(Disfluency(0.0, True, random.Random(0), phrase_pause_rate=1.0), chunks)
    off = _apply(Disfluency(0.0, False, random.Random(0), phrase_pause_rate=1.0), chunks)
    assert "[pause" in on[0]
    assert off == chunks


def test_pacing_and_opening_coexist():
    d = Disfluency(1.0, True, random.Random(0), phrase_pause_rate=1.0)
    # Opening never prepends Um/Ah — greeting is the first spoken text.
    out = _apply(d, ["नमस्ते Priya, मैं आपका interview लेने वाली हूँ। "], opening=True)
    assert "Um" not in out[0]
    assert out[0].lstrip().startswith("नमस्ते")
    en = _apply(d, ["Hi Priya, I will take your interview. "], lang="en-IN", opening=True)
    assert en[0].lstrip().startswith("Hi")
    assert not en[0].lstrip().lower().startswith("um")
