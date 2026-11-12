"""Early analysis reuse keyed on normalised text (latency step L3)."""

import asyncio

from tests.test_director import CITY, FakeClient, build
from tests.test_flow import blueprint, make_plan  # noqa: F401  (fixture re-export)


def _run(blueprint, early_text, confirmed_text, extra_final=None):  # noqa: F811
    client = FakeClient([CITY], delay=0.02)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript(early_text)
        if extra_final:
            director.on_final_transcript(extra_final)
        await asyncio.sleep(0.005)
        await director.decide(confirmed_text)

    asyncio.run(go())
    return client.calls, director


def test_spacing_and_punctuation_difference_reuses_the_early_call(blueprint):  # noqa: F811
    calls, director = _run(blueprint, "Pune ke liye apply kar rahi hoon", "  Pune ke liye,  apply kar rahi hoon. ")
    assert calls == 1
    assert director.last_early_hit is True


def test_filler_tail_reuses_the_early_call(blueprint):  # noqa: F811
    calls, director = _run(blueprint, "Pune ke liye apply kar rahi hoon", "Pune ke liye apply kar rahi hoon haan")
    assert calls == 1
    assert director.last_early_hit is True


def test_new_substantive_sentence_runs_the_analyst_again(blueprint):  # noqa: F811
    calls, director = _run(
        blueprint,
        "Pune ke liye apply kar rahi hoon",
        "Pune ke liye apply kar rahi hoon aur mera experience teen saal ka hai ICU mein",
    )
    assert calls == 2
    assert director.last_early_hit is False


def test_changed_context_runs_the_analyst_again(blueprint):  # noqa: F811
    client = FakeClient([CITY], delay=0.02)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("Pune ke liye apply kar rahi hoon")
        await asyncio.sleep(0.005)
        director.note_assistant("Aur aapki qualification kya hai?")  # last question changed
        await director.decide("Pune ke liye apply kar rahi hoon.")

    asyncio.run(go())
    assert client.calls == 2
    assert director.last_early_hit is False


def test_early_ready_only_when_the_early_result_is_done_and_usable(blueprint):  # noqa: F811
    client = FakeClient([CITY], delay=0.05)
    director, flow = build(blueprint, client)
    flow.opening()
    seen: dict[str, bool] = {}

    async def go():
        assert director.early_ready("Pune ke liye apply kar rahi hoon") is False  # nothing started
        director.on_final_transcript("Pune ke liye apply kar rahi hoon")
        await asyncio.sleep(0.005)
        seen["running"] = director.early_ready("Pune ke liye apply kar rahi hoon")
        await asyncio.sleep(0.08)
        seen["done"] = director.early_ready("Pune ke liye apply kar rahi hoon.")
        seen["new_text"] = director.early_ready("Pune ke liye apply kar rahi hoon aur teen saal ICU mein kaam")
        await director.decide("Pune ke liye apply kar rahi hoon.")

    asyncio.run(go())
    assert seen == {"running": False, "done": True, "new_text": False}
    assert client.calls == 1


def _partial_then_final(blueprint, partial, final, confirmed):  # noqa: F811
    client = FakeClient([CITY], delay=0.02)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_partial_settled(partial)
        await asyncio.sleep(0.005)
        director.on_final_transcript(final)
        await director.decide(confirmed)

    asyncio.run(go())
    return client.calls, director


def test_partial_analysis_is_kept_when_the_final_matches(blueprint):  # noqa: F811
    calls, director = _partial_then_final(
        blueprint, "Pune ke liye apply kar rahi hoon", "Pune ke liye, apply kar rahi hoon.", "Pune ke liye apply kar rahi hoon."
    )
    assert calls == 1
    assert director.last_early_hit is True


def test_partial_analysis_is_replaced_when_the_final_differs(blueprint):  # noqa: F811
    calls, director = _partial_then_final(
        blueprint,
        "Pune ke liye apply",
        "Nagpur ke liye apply kar rahi hoon",
        "Nagpur ke liye apply kar rahi hoon",
    )
    assert calls == 2
    assert director.last_early_hit is True
