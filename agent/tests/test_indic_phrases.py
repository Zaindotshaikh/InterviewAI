"""Pan-Indic heuristic coverage for all interview language profiles."""

from __future__ import annotations

import pytest

from interview.analysis import heuristic_analysis, infer_care_accept
from interview.indic_phrases import DONT_KNOW_RE, FILLER_ONLY, REPEAT_RE, STOP_RE


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        # don't-know — one per supported Indic script + common roman
        ("pata nahi", "dont_know"),
        ("पता नहीं", "dont_know"),
        ("मला माहित नाही", "dont_know"),
        ("தெரியாது", "dont_know"),
        ("తెలియదు", "dont_know"),
        ("ಗೊತ್ತಿಲ್ಲ", "dont_know"),
        ("അറിയില്ല", "dont_know"),
        ("জানি না", "dont_know"),
        ("ખબર નથી", "dont_know"),
        ("ਪਤਾ ਨਹੀਂ", "dont_know"),
        ("ଜଣା ନାହିଁ", "dont_know"),
        ("gottilla", "dont_know"),
        ("theriyala", "dont_know"),
        # repeat / rephrase / stop / refusal / filler
        ("மறுபடி", "repeat_request"),
        ("మళ్ళీ", "repeat_request"),
        ("വീണ്ടും", "repeat_request"),
        ("আবার বলুন", "repeat_request"),
        ("புரியல", "rephrase_request"),
        ("అర్థం కాలేదు", "rephrase_request"),
        ("বন্ধ করো", "wants_to_stop"),
        ("ఆపు", "wants_to_stop"),
        ("சொல்ல மாட்டேன்", "refusal"),
        ("বলব না", "refusal"),
        ("ஆமா", "filler_only"),
        ("అవును", "filler_only"),
        ("হ্যাঁ", "filler_only"),
        ("hmm", "filler_only"),
    ],
)
def test_pan_indic_heuristic_intents(text, intent):
    assert heuristic_analysis(text).intent == intent


@pytest.mark.parametrize(
    "text",
    ["हाँ", "ஆமா", "అవును", "ಹೌದು", "അതെ", "হ্যাঁ", "હા", "ਹਾਂ", "ହଁ", "yes"],
)
def test_short_yes_confirms_when_pending(text):
    a = heuristic_analysis(text, pending_field="phone", pending_value="9876543210")
    assert a.confirmation == "confirmed"
    assert a.intent == "answer"


@pytest.mark.parametrize(
    "text",
    ["पता नहीं", "தெரியாது", "తెలియదు", "ಗೊತ್ತಿಲ್ಲ", "pata nahi"],
)
def test_dont_know_is_not_care_refuse(text):
    assert DONT_KNOW_RE.search(text)
    assert infer_care_accept(text) is None


def test_compiled_banks_are_reusable():
    assert REPEAT_RE.search("फिर से")
    assert STOP_RE.search("बंद करो")
    assert "हाँ" in FILLER_ONLY
    assert "ஆமா" in FILLER_ONLY
