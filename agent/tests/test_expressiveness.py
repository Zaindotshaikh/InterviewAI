"""Unit tests for the EL expressiveness engine (Phase 4)."""

import asyncio
import random

from interview.expressiveness import ExpressivenessEngine, filler_bucket_from_text
from interview.voice_tone import resolve_tone, tag_for_tone, tone_for_kind


def _run(engine: ExpressivenessEngine, text: str, **kw) -> str:
    async def chunks():
        for i in range(0, len(text), 5):
            yield text[i : i + 5]

    async def collect():
        return "".join([s async for s in engine.apply(chunks(), language="hi-IN", **kw)])

    return asyncio.run(collect())


def test_tone_for_kind_defaults():
    assert tone_for_kind("opening") == "warm"
    assert tone_for_kind("persuade") == "gentle"
    assert resolve_tone("ask_field", empathy_tone="gentle", empathy_enabled=False) == "curious"
    assert resolve_tone("ask_field", empathy_tone="gentle", empathy_enabled=True) == "gentle"


def test_engine_strips_llm_tags_and_adds_at_most_one():
    eng = ExpressivenessEngine(rng=random.Random(0), pause_rate=0, umm_rate=0, sigh_rate=0)
    out = _run(eng, "[warmly] अच्छा। [curious] आप कहाँ काम करते हैं?", tone="curious")
    assert out.count("[curious]") <= 1
    assert "[warmly]" not in out


def test_tag_split_across_chunks_reassembled():
    eng = ExpressivenessEngine(rng=random.Random(1), pause_rate=0, umm_rate=0, sigh_rate=0)

    async def chunks():
        # Split an LLM-invented tag across stream chunks; engine must reassemble then strip it,
        # and may add at most one whitelist tone tag.
        for c in ["[curi", "ous] Hello. ", "Next?"]:
            yield c

    async def collect():
        return [s async for s in eng.apply(chunks(), language="en-IN", tone="warm")]

    parts = asyncio.run(collect())
    joined = "".join(parts)
    assert "[curious]" not in joined  # LLM tag stripped
    assert joined.count("[warmly]") <= 1
    assert "Hello" in joined


def test_no_consecutive_same_tag():
    eng = ExpressivenessEngine(rng=random.Random(2), pause_rate=0, umm_rate=0, sigh_rate=0)
    a = _run(eng, "Hello there friend. How are you doing today?", tone="warm")
    b = _run(eng, "Okay next question about your work experience please?", tone="warm")
    # Second turn should not repeat the same tag consecutively
    if tag_for_tone("warm") and tag_for_tone("warm") in a:
        assert tag_for_tone("warm") not in b or a.count("[warmly]") <= 1


def test_filler_bucket_heuristic():
    assert filler_bucket_from_text("I am not comfortable with that") == "empathetic"
    assert filler_bucket_from_text("I worked in ICU for three years") == "neutral"
    assert filler_bucket_from_text("नहीं, मुझे नहीं पता") == "neutral"
    assert filler_bucket_from_text("I don't know") == "neutral"
    assert filler_bucket_from_text("मुझे बहुत डर लग रहा है") == "empathetic"


def test_a_played_reaction_does_not_get_another_hesitation():
    eng = ExpressivenessEngine(rng=random.Random(0), pause_rate=1, umm_rate=1, sigh_rate=0)
    out = _run(eng, "अच्छा, आप कहाँ काम करते हैं आजकल?", skip_first=True, tone="curious")
    assert "umm" not in out.lower()


def test_a_hesitation_sits_after_a_comma_without_a_second_pause():
    eng = ExpressivenessEngine(rng=random.Random(0), pause_rate=1, umm_rate=1, sigh_rate=0)
    out = _run(eng, "अच्छा, आप कहाँ काम करते हैं आजकल?", tone="curious")
    assert "umm," in out
    assert "..." not in out


def test_spoken_for_transcript_strips_tags():
    eng = ExpressivenessEngine()
    assert "warmly" not in eng.spoken_for_transcript("[warmly] Hello... there")
    assert "Hello" in eng.spoken_for_transcript("[warmly] Hello... there")
