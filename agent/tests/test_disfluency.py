import asyncio
import random

from interview.disfluency import Disfluency
from interview.fillers import INDIC_UM, normalize_fillers


async def _stream(chunks):
    for c in chunks:
        yield c


def _run(d: Disfluency, chunks, language="hi-IN", skip_first=False, opening=False) -> list[str]:
    async def collect():
        return [s async for s in d.apply(_stream(chunks), language, skip_first=skip_first, opening=opening)]

    return asyncio.run(collect())


REPLY = ["अच्छा, बहुत बढ़िया है। ", "आप अभी किस hospital में ", "काम कर रही हैं? ", "और कितने साल से?"]


def test_splits_streamed_tokens_into_sentences_and_keeps_text():
    out = _run(Disfluency(rate=1.0, use_pause_tags=True), REPLY)
    assert out == ["अच्छा, बहुत बढ़िया है। ", "आप अभी किस hospital में काम कर रही हैं? ", "और कितने साल से?"]


def test_ellipsis_is_not_a_sentence_break():
    out = _run(Disfluency(rate=0.0, use_pause_tags=False), ["तो... अपने बारे में थोड़ा बताइए? "])
    assert len(out) == 1


def test_never_invents_a_filler():
    d = Disfluency(rate=1.0, use_pause_tags=False, rng=random.Random(1))
    for lang in ("hi-IN", "mr-IN", "en-IN"):
        out = "".join(_run(d, ["आप अभी कहाँ काम कर रही हैं? ", "कितने साल से?"], language=lang))
        assert "um" not in out.lower()


def test_llm_um_is_kept_once_in_canonical_spelling():
    d = Disfluency(rate=1.0, use_pause_tags=False)
    out = "".join(_run(d, ["बरं, तर Umm... तुम्ही ICU मध्ये किती वर्षं काम केलं? ", "आणि uhm, कुठे? "], language="mr-IN"))
    assert out.count(INDIC_UM) == 1
    assert "बरं, तर umm, तुम्ही" in out
    assert "uhm" not in out.lower() and "Umm" not in out


def test_rate_zero_removes_the_um():
    d = Disfluency(rate=0.0, use_pause_tags=False)
    out = "".join(_run(d, ["बरं, तर umm, तुम्ही किती वर्षं काम केलं? "], language="mr-IN"))
    assert "umm" not in out and "तर तुम्ही" in out


def test_no_um_right_after_a_reaction_was_played_or_in_the_greeting():
    d = Disfluency(rate=1.0, use_pause_tags=False)
    after_ack = _run(d, ["तर umm, तुम्ही कुठे काम करता? "], language="mr-IN", skip_first=True)
    assert "umm" not in after_ack[0]
    # Opening: first sentence stays a clean greeting; later sentences may keep umm.
    parts = _run(d, ["नमस्कार Priya. ", "तर umm, थोडं सांगा? "], language="mr-IN", opening=True)
    greeting = "".join(parts)
    assert parts[0].lstrip().startswith("नमस्कार") and "umm" not in parts[0]
    assert "umm" in greeting


def test_moans_are_removed_and_real_words_kept():
    def clean(t, lang="mr-IN"):
        return normalize_fillers(t, lang, allow_um=True)[0]

    assert clean("आ... तुमच्याबद्दल थोडं सांगा?") == "तुमच्याबद्दल थोडं सांगा?"
    assert clean("उह, आता कुठे काम करताय?") == "आता कुठे काम करताय?"
    assert clean("aah, where do you work?", "en-IN") == "where do you work?"
    assert clean("hmm, okay tell me more", "en-IN") == "okay tell me more"
    for real in ("आता तुम्ही कुठे काम करताय?", "अच्छा, तो बताइए", "हे काम आहे का?", "अंग दुखतंय का?"):
        assert clean(real) == real


def test_um_is_not_left_dangling_at_the_end():
    assert normalize_fillers("तुम्ही कुठे काम करता, umm.", "mr-IN", allow_um=True) == ("तुम्ही कुठे काम करता", False)


def test_moan_only_sentence_is_dropped():
    out = _run(Disfluency(rate=1.0, use_pause_tags=False), ["आ। ", "नमस्कार, मी Aven बोलतेय. "], language="mr-IN", opening=True)
    assert out[0].lstrip().startswith("नमस्कार")


def test_pause_tags_do_not_pile_up_around_the_um():
    d = Disfluency(rate=1.0, use_pause_tags=True, rng=random.Random(0), phrase_pause_rate=1.0)
    for seed in range(20):
        d._rng = random.Random(seed)
        out = "".join(_run(d, ["बरं, तर umm, तुम्ही ICU मध्ये आणि ward मध्ये किती वर्षं काम केलं? "], language="mr-IN"))
        assert "] umm," not in out and "umm, [" not in out
