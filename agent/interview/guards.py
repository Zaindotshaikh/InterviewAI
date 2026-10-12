"""Prompt injection and untrusted-input guards."""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    re.compile(r"ignore (all |any )?(previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"reveal (your|the) (prompt|instructions)", re.I),
]


def sanitize_candidate_text(text: str) -> str:
    cleaned = text.strip()
    for pat in INJECTION_PATTERNS:
        if pat.search(cleaned):
            return "[candidate utterance redacted: policy]"
    # Cap extreme length to protect context
    if len(cleaned) > 4000:
        return cleaned[:4000] + "…"
    return cleaned
