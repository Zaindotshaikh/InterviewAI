"""Request options per model family: GPT-5 runs with reasoning off and no temperature."""

from interview.analysis import completion_options, reasoning_off


def test_gpt5_models_use_reasoning_off_and_completion_tokens():
    assert completion_options("gpt-5.4-mini", max_tokens=450) == {
        "reasoning_effort": "none",
        "max_completion_tokens": 450,
    }
    assert reasoning_off("gpt-5-mini") == "minimal"
    assert reasoning_off("o4-mini") == "low"


def test_older_models_keep_temperature_zero():
    assert completion_options("gpt-4o-mini", max_tokens=900) == {"temperature": 0, "max_tokens": 900}
    assert completion_options("gpt-4.1-mini", max_tokens=450)["temperature"] == 0
