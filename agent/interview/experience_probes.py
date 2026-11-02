"""Build the post-care experience probe queue from resume text + the nursing bank.

Flow owns when to ask; this module only picks facts and bank ids. No speech policy here.
"""

from __future__ import annotations

import re
from typing import Any

from interview.blueprint import Blueprint, ExperienceProbeSpec

_NURSING_LINE = re.compile(
    r"(?:"
    r"\b(?:nurse|nursing|staff\s*nurse|gnm|anm|b\.?\s*sc|icu|nicu|picu|ccu|ward|ot\b|theatre|"
    r"hospitals?|clinics?|apollo|fortis|max\b|manipal|aiims|pgimer|homecare|home\s*care|"
    r"ventilators?|infusions?|medications?|patients?|duties|duty|internships?|postings?|opd|casualty|emergency)\b"
    r"|नर्स|वार्ड|हॉस्पिटल|अस्पताल|आईसीयू|इंटर्न"
    r")",
    re.IGNORECASE,
)
_YEARISH = re.compile(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\s*(?:\+)?\s*(?:years?|yrs?|साल|वर्ष)\b", re.IGNORECASE)
_SPLIT = re.compile(r"[\n\r•|;]+|(?<=[.!?])\s+")


def is_fresher(*, experience_level: str, years_value: Any) -> bool:
    if experience_level == "fresher":
        return True
    try:
        n = float(years_value)
    except (TypeError, ValueError):
        return experience_level in ("", "unknown") and years_value in (None, "", "0", 0)
    return n < 0.5


def extract_resume_facts(resume_text: str, *, limit: int = 3) -> list[str]:
    """Short concrete lines from the resume to ground spoken questions. Empty when nothing useful."""
    text = " ".join((resume_text or "").split())
    if not text:
        return []
    chunks: list[str] = []
    for part in _SPLIT.split(resume_text or ""):
        line = " ".join(part.split()).strip(" -:\t")
        if len(line) < 12 or len(line) > 160:
            continue
        if not (_NURSING_LINE.search(line) or _YEARISH.search(line)):
            continue
        low = line.lower()
        if any(low == c.lower() or low in c.lower() or c.lower() in low for c in chunks):
            continue
        chunks.append(line)
        if len(chunks) >= limit:
            break
    if len(chunks) >= limit:
        return chunks[:limit]
    # Fall back to a truncated whole resume so experienced candidates still get resume-tied asks.
    if text and not chunks:
        chunks.append(text[:180])
    return chunks[:limit]


def candidate_tags(*, settings: str, resume_text: str, fresher: bool) -> set[str]:
    blob = f"{settings} {resume_text}".lower()
    tags: set[str] = {"general", "ward"}
    if fresher:
        tags.add("fresher")
    for tag, words in (
        ("icu", ("icu", "nicu", "picu", "ccu", "critical", "ventilator")),
        ("homecare", ("home", "homecare", "elderly", "attendant")),
        ("ward", ("ward", "opd", "clinic", "hospital", "ot ", "operation")),
        ("emergency", ("emergency", "casualty", "trauma", "code blue")),
        ("junior", ("year", "staff", "nurse")),
    ):
        if any(w in blob for w in words):
            tags.add(tag)
    return tags


def pick_bank_probes(
    bank: tuple[ExperienceProbeSpec, ...],
    *,
    tags: set[str],
    count: int,
    exclude_ids: set[str] | None = None,
) -> list[ExperienceProbeSpec]:
    """Prefer probes whose tags overlap the candidate; fill from the rest of the bank."""
    if count <= 0 or not bank:
        return []
    skip = exclude_ids or set()
    scored: list[tuple[int, int, ExperienceProbeSpec]] = []
    for i, p in enumerate(bank):
        if p.id in skip:
            continue
        overlap = len(set(p.tags) & tags)
        # Freshers: boost fresher-tagged items.
        if "fresher" in tags and "fresher" in p.tags:
            overlap += 2
        scored.append((-overlap, i, p))
    scored.sort()
    return [p for _, _, p in scored[:count]]


def build_probe_queue(
    bp: Blueprint,
    *,
    fresher: bool,
    resume_text: str,
    settings: str,
) -> list[dict[str, Any]]:
    """Ordered queue items: {id, source, ask, fact?}."""
    lim = bp.limits
    queue: list[dict[str, Any]] = []
    tags = candidate_tags(settings=settings, resume_text=resume_text, fresher=fresher)

    if not fresher:
        facts = extract_resume_facts(resume_text, limit=max(0, int(lim.experience_resume_tied)))
        for i, fact in enumerate(facts):
            queue.append(
                {
                    "id": f"resume_{i + 1}",
                    "source": "resume",
                    "fact": fact,
                    "ask": (
                        "Ask ONE short spoken question about this concrete fact from their resume work. "
                        "Do not read the resume aloud. Do not ask a second question. "
                        f"Fact: {fact}"
                    ),
                }
            )
        # Experienced with no usable resume: still one background ask from spoken settings.
        if not facts and settings.strip():
            queue.append(
                {
                    "id": "settings_depth",
                    "source": "settings",
                    "fact": settings.strip()[:160],
                    "ask": (
                        f"They said they worked in {settings.strip()[:120]}. Ask ONE short question about what they "
                        "actually did with patients there. Do not start scored clinical scenarios."
                    ),
                }
            )
        bank_n = max(0, int(lim.experience_bank_target))
    else:
        bank_n = max(0, int(lim.experience_fresher_target))

    bank = pick_bank_probes(bp.experience_probes, tags=tags, count=bank_n)
    for p in bank:
        queue.append(
            {
                "id": p.id,
                "source": "bank",
                "ask": p.ask
                + " One question only. Do not start the scored clinical scenarios yet.",
            }
        )
    return queue
