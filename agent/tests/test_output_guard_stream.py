"""OutputGuard.stream releases checked sentences early (latency step L1)."""

import asyncio

from interview.output_guard import OutputGuard


async def _chunks(parts, log=None):
    for i, p in enumerate(parts):
        if log is not None:
            log.append(i)
        await asyncio.sleep(0)
        yield p


def _run(parts, **kw):
    async def go():
        out = []
        async for s in OutputGuard().stream(_chunks(parts), **kw):
            out.append(s)
        return out

    return asyncio.run(go())


def test_first_sentence_released_before_stream_ends():
    consumed: list[int] = []
    released_at: list[int] = []

    async def go():
        parts = ["Okay, thanks. ", "Which ", "city ", "are you in?"]
        async for s in OutputGuard().stream(_chunks(parts, consumed), language="en-IN"):
            released_at.append(len(consumed))
            yield_text.append(s)

    yield_text: list[str] = []
    asyncio.run(go())
    assert yield_text[0] == "Okay, thanks. "
    assert released_at[0] < 4  # released before the last chunk was read


def test_two_questions_are_cut_after_the_first():
    out = _run(["Which hospital was that? ", "And how many beds were in your ICU?"], language="en-IN")
    assert "".join(out).strip() == "Which hospital was that?"


def test_opening_allows_several_questions():
    out = _run(["Hello. ", "Is this a good time? ", "Can we start?"], language="en-IN", single_question=False)
    assert "".join(out) == "Hello. Is this a good time? Can we start?"


def test_salary_leak_in_second_sentence_releases_only_the_safe_line():
    out = _run(["Thanks, noted. ", "We will pay a salary of 25000 per month. ", "Ok?"], language="en-IN")
    assert out[0] == "Thanks, noted. "
    assert len(out) == 2
    assert "25000" not in "".join(out)
    assert "Salary and package details will be shared directly" in out[1]


def test_centimetres_replaced_with_fallback():
    fallback = "I heard height 5 feet 11 inches and weight 70 kilograms. Is that correct?"
    out = _run(
        ["I heard height 173 centimeters and weight 70 kilograms. ", "Is that correct?"],
        language="en-IN",
        forbid_centimetres=True,
        fallback_text=fallback,
    )
    assert out == [fallback]


def test_redundant_city_ask_is_replaced():
    out = _run(["Which city are you located in?"], language="en-IN", captured_slots={"city"})
    assert out == ["Let us continue to the next question."]


def test_clean_reply_without_trailing_space_is_released_whole():
    out = _run(["Thanks for that"], language="en-IN")
    assert out == ["Thanks for that"]


def test_statement_after_question_is_not_streamed_but_never_leaks():
    out = _run(["Which city? ", "Salary is 30000 rupees."], language="en-IN")
    assert "".join(out).strip() == "Which city?"


def test_live_question_starts_on_the_first_clause():
    words = "Can you tell me about a time when a patient needed urgent help in the ward last night".split()
    parts = [word + " " for word in words]
    consumed: list[int] = []
    released_at: list[int] = []
    out: list[str] = []

    async def go():
        async for sentence in OutputGuard().stream(_chunks(parts, consumed), language="en-IN"):
            released_at.append(len(consumed))
            out.append(sentence)

    asyncio.run(go())
    assert out[0] == "Can you tell me about a time. "
    assert released_at[0] < len(parts)
    assert "ward" in "".join(out)


def test_complete_question_is_not_cut():
    line = "Can you tell me about a time when a patient needed urgent help in the ward last night? "
    assert _run([line], language="en-IN") == [line]


def test_streamed_centimetres_are_not_spoken_before_the_guard():
    words = "I heard height 173 centimeters and weight 70 kilograms.".split()
    fallback = "I heard height 5 feet 11 inches and weight 70 kilograms. Is that correct?"
    out = _run(
        [word + " " for word in words],
        language="en-IN",
        forbid_centimetres=True,
        fallback_text=fallback,
    )
    assert out == [fallback]
    assert "173" not in "".join(out)


def test_salary_waiting_in_the_next_words_is_not_started():
    words = "Thanks for that update here is the salary of 25000 per month for this role".split()
    out = _run([word + " " for word in words], language="en-IN")
    spoken = "".join(out)
    assert "25000" not in spoken
    assert "Thanks for that update here is the." not in spoken
    assert "Salary and package details will be shared directly" in spoken


def test_short_comma_lead_in_starts_before_the_question():
    parts = ["Okay, ", "can ", "you ", "tell ", "me ", "which ", "ward ", "you ", "worked ", "in?"]
    consumed: list[int] = []
    released_at: list[int] = []
    out: list[str] = []

    async def go():
        async for sentence in OutputGuard().stream(_chunks(parts, consumed), language="en-IN"):
            released_at.append(len(consumed))
            out.append(sentence)

    asyncio.run(go())
    assert out[0] == "Okay. "
    assert released_at[0] < len(parts)
    assert "ward" in "".join(out)


def test_live_question_starts_on_the_first_clause():
    words = "Can you tell me about a time when a patient needed urgent help in the ward last night".split()
    parts = [word + " " for word in words]
    consumed: list[int] = []
    released_at: list[int] = []
    out: list[str] = []

    async def go():
        async for sentence in OutputGuard().stream(_chunks(parts, consumed), language="en-IN"):
            released_at.append(len(consumed))
            out.append(sentence)

    asyncio.run(go())
    assert out[0] == "Can you tell me about a time. "
    assert released_at[0] < len(parts)
    assert "ward" in "".join(out)


def test_complete_question_is_not_cut():
    line = "Can you tell me about a time when a patient needed urgent help in the ward last night? "
    assert _run([line], language="en-IN") == [line]


def test_streamed_centimetres_are_not_spoken_before_the_guard():
    words = "I heard height 173 centimeters and weight 70 kilograms.".split()
    fallback = "I heard height 5 feet 11 inches and weight 70 kilograms. Is that correct?"
    out = _run(
        [word + " " for word in words],
        language="en-IN",
        forbid_centimetres=True,
        fallback_text=fallback,
    )
    assert out == [fallback]
    assert "173" not in "".join(out)


def test_salary_waiting_in_the_next_words_is_not_started():
    words = "Thanks for that update here is the salary of 25000 per month for this role".split()
    out = _run([word + " " for word in words], language="en-IN")
    spoken = "".join(out)
    assert "25000" not in spoken
    assert "Thanks for that update here is the." not in spoken
    assert "Salary and package details will be shared directly" in spoken


def test_short_comma_lead_in_starts_before_the_question():
    parts = ["Okay, ", "can ", "you ", "tell ", "me ", "which ", "ward ", "you ", "worked ", "in?"]
    consumed: list[int] = []
    released_at: list[int] = []
    out: list[str] = []

    async def go():
        async for sentence in OutputGuard().stream(_chunks(parts, consumed), language="en-IN"):
            released_at.append(len(consumed))
            out.append(sentence)

    asyncio.run(go())
    assert out[0] == "Okay. "
    assert released_at[0] < len(parts)
    assert "ward" in "".join(out)
