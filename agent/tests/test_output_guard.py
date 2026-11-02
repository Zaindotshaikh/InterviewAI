"""Unit tests for OutputGuard (Phase 2 P2-08)."""

import pytest
from interview.output_guard import OutputGuard


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

