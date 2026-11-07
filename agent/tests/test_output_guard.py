"""Unit tests for OutputGuard (Phase 2 P2-08)."""

import asyncio

import pytest
from interview.output_guard import OutputGuard, iter_guarded_clauses


@pytest.fixture
def guard() -> OutputGuard:
    return OutputGuard()


def test_clean_text_passes_unchanged(guard: OutputGuard) -> None:
    text = "कृपया बताइए कि आपने जीएनएम कब पूरा किया था?"
    blocked, out, reason = guard.inspect_text(text, language="hi-IN")
    assert not blocked
    assert out == text
    assert reason == ""


def test_salary_leak_english(guard: OutputGuard) -> None:
    text = "We will offer you a salary of 25000 per month."
    blocked, out, reason = guard.inspect_text(text, language="en-IN")
    assert blocked
    assert reason == "salary_leak"
    assert "Salary and package details will be shared directly" in out
    assert "25000" not in out


def test_salary_leak_hindi_currency(guard: OutputGuard) -> None:
    text = "आपका वेतन ₹30,000 प्रति माह होगा।"
    blocked, out, reason = guard.inspect_text(text, language="hi-IN")
    assert blocked
    assert reason == "salary_leak"
    assert "वेतन और पैकेज की जानकारी रिक्रूटमेंट टीम द्वारा सीधे साझा की जाएगी।" in out
    assert "30,000" not in out


def test_salary_leak_ctc_lakh(guard: OutputGuard) -> None:
    text = "The CTC for this role is 4 lakh per annum."
    blocked, out, reason = guard.inspect_text(text, language="en-IN")
    assert blocked
    assert reason == "salary_leak"
    assert "4 lakh" not in out


def test_offer_leak_english(guard: OutputGuard) -> None:
    text = "Congratulations, you are selected for the staff nurse role!"
    blocked, out, reason = guard.inspect_text(text, language="en-IN")
    assert blocked
    assert reason == "offer_leak"
    assert "The recruitment team will follow up with you" in out
    assert "congratulations" not in out.lower()


def test_offer_leak_hindi(guard: OutputGuard) -> None:
    text = "बहुत बढ़िया, आपका सिलेक्शन पक्का हो गया है।"
    blocked, out, reason = guard.inspect_text(text, language="hi-IN")
    assert blocked
    assert reason == "offer_leak"
    assert "साक्षात्कार के परिणाम की समीक्षा के बाद" in out


def test_multiple_questions_truncated(guard: OutputGuard) -> None:
    text = "Which hospital was that? And how many beds were in your ICU?"
    blocked, out, reason = guard.inspect_text(text, single_question=True)
    assert blocked
    assert reason == "multiple_questions"
    assert out == "Which hospital was that?"
    assert "ICU" not in out


def test_redundant_slot_blocked_when_already_captured(guard: OutputGuard) -> None:
    text = "Which city are you currently located in?"
    # When city is captured, asking city again is blocked
    blocked, out, reason = guard.inspect_text(
        text,
        language="en-IN",
        captured_slots={"city", "phone"},
    )
    assert blocked
    assert reason == "redundant_slot_city"
    assert "Which city" not in out
    assert "Let us continue to the next question." in out


def test_height_cm_spoken_replaced_when_candidate_used_feet(guard: OutputGuard) -> None:
    text = "I heard height 173 centimeters and weight 70 kilograms. Is that correct?"
    fallback = "I heard height 5 feet 11 inches and weight 70 kilograms. Is that correct?"
    blocked, out, reason = guard.inspect_text(
        text,
        language="en-IN",
        forbid_centimetres=True,
        fallback_text=fallback,
    )
    assert blocked
    assert reason == "height_cm_spoken"
    assert out == fallback
    assert "centimeter" not in out.lower()


def test_height_cm_allowed_when_they_said_cm(guard: OutputGuard) -> None:
    text = "I heard height 160 centimetres and weight 55 kilograms. Is that correct?"
    blocked, out, reason = guard.inspect_text(text, language="en-IN", forbid_centimetres=False)
    assert not blocked
    assert out == text


def test_slot_allowed_when_not_captured(guard: OutputGuard) -> None:
    text = "Which city are you currently located in?"
    # When city is not yet captured, asking city is allowed
    blocked, out, reason = guard.inspect_text(
        text,
        language="en-IN",
        captured_slots={"phone"},
    )
    assert not blocked
    assert out == text


def test_first_clause_starts_before_the_rest_of_any_reply(guard: OutputGuard) -> None:
    # Screening, clinical, and closing all use this path. Nothing here is phone-specific.
    async def go() -> list[str]:
        seen_rest = False
        heard: list[str] = []

        async def source():
            nonlocal seen_rest
            yield "Okay. "
            seen_rest = True
            yield "What would you do if the diaper was soaked? "

        async for piece in iter_guarded_clauses(source(), guard, language="en-IN"):
            if not heard:
                assert seen_rest is False
            heard.append(piece)
        return heard

    heard = asyncio.run(go())
    assert "Okay" in heard[0]
    assert any("diaper" in piece for piece in heard)


def test_unfinished_clause_is_not_spoken(guard: OutputGuard) -> None:
    async def source():
        yield "Okay, Del"
        yield "hi. Where do you work now? "

    async def go() -> list[str]:
        return [piece async for piece in iter_guarded_clauses(source(), guard, language="en-IN")]

    heard = asyncio.run(go())
    assert heard[0].strip().endswith("Delhi.") or heard[0].strip() == "Okay, Delhi."
    joined = "".join(heard)
    assert "Okay, Del " not in joined
    assert "Where do you work" in joined


def test_later_clause_salary_is_replaced_on_any_turn(guard: OutputGuard) -> None:
    async def source():
        yield "Thanks for explaining that. "
        yield "The salary is 25000 per month. "

    async def go() -> str:
        return "".join([piece async for piece in iter_guarded_clauses(source(), guard, language="en-IN")])

    spoken = asyncio.run(go())
    assert "Thanks for explaining" in spoken
    assert "25000" not in spoken
    assert "recruitment team" in spoken


def test_second_question_is_dropped_on_any_turn(guard: OutputGuard) -> None:
    async def source():
        yield "What would you check first? "
        yield "And what number would you report? "

    async def go() -> str:
        return "".join(
            [
                piece
                async for piece in iter_guarded_clauses(
                    source(), guard, language="en-IN", single_question=True
                )
            ]
        )

    spoken = asyncio.run(go())
    assert spoken.strip() == "What would you check first?"
    assert "number" not in spoken


def test_hindi_clause_is_released_the_same_way(guard: OutputGuard) -> None:
    async def source():
        yield "अच्छा। "
        yield "अभी आप कहाँ काम कर रहे हैं? "

    async def go() -> list[str]:
        return [piece async for piece in iter_guarded_clauses(source(), guard, language="hi-IN")]

    heard = asyncio.run(go())
    assert "अच्छा" in heard[0]
    assert any("काम" in piece for piece in heard)

