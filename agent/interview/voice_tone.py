"""Deterministic move.kind → tone map (outside InterviewFlow). Optional Director empathy override."""

from __future__ import annotations

from typing import Literal

Tone = Literal[
    "warm",
    "neutral",
    "curious",
    "gentle",
    "reassuring",
    "matter_of_fact",
    "thoughtful",
]

# Whitelist tag per tone (engine mode). neutral → no tag.
TONE_TAG: dict[str, str | None] = {
    "warm": "[warmly]",
    "curious": "[curious]",
    "gentle": "[gently]",
    "reassuring": "[reassuring]",
    "matter_of_fact": "[matter-of-fact]",
    "thoughtful": "[thoughtful]",
    "neutral": None,
}

_KIND_TONE: dict[str, Tone] = {
    "opening": "warm",
    "ask_field": "curious",
    "ask_care": "curious",
    "ask_care_item": "curious",
    "ask_repeat": "curious",
    "reask_invalid": "curious",
    "confirm": "matter_of_fact",
    "confirm_stop": "matter_of_fact",
    "persuade": "gentle",
    "experience_dive": "curious",
    "resume_check": "curious",
    "aside": "warm",
    "goodbye": "warm",
    "ended": "warm",
    "resume": "warm",
    "resume_closing": "warm",
    "noise": "reassuring",
    "silence_hold": "neutral",
    "silence_nudge": "reassuring",
    "silence_rephrase": "gentle",
    "silence_check": "gentle",
    "redirect": "neutral",
    "answer_faq": "matter_of_fact",
}


def tone_for_kind(kind: str) -> Tone:
    return _KIND_TONE.get(kind, "neutral")


def resolve_tone(kind: str, *, empathy_tone: str | None = None, empathy_enabled: bool = False) -> Tone:
    """Kind default, unless Director empathy override is enabled and provided."""
    if empathy_enabled and empathy_tone in TONE_TAG:
        return empathy_tone  # type: ignore[return-value]
    return tone_for_kind(kind)


def tag_for_tone(tone: str) -> str | None:
    return TONE_TAG.get(tone)
