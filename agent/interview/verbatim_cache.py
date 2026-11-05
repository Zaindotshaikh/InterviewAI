"""Pre-render fixed verbatim lines once per language, the same way fillers are cached.

Phone confirm and body confirm stay on live TTS: those sentences contain the digits
or the height and weight just heard. phone_invalid_line also interpolates the heard
digits, so it is not in this list and falls through to live TTS.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from interview.flow import CROWD_HELP_LINES, SALARY_HOLDOUT_LINES
from interview.phone_speech import phone_again_line, phone_ask_line

logger = logging.getLogger("interview-agent")


def static_verbatim_lines(language: str) -> list[str]:
    """Templates with no spoken digits. One clip per language is enough."""
    return [
        phone_ask_line(language),
        phone_again_line(language),
        SALARY_HOLDOUT_LINES.get(language, SALARY_HOLDOUT_LINES["en-IN"]),
        CROWD_HELP_LINES.get(language, CROWD_HELP_LINES["en-IN"]),
    ]


class VerbatimCache:
    """Synthesize each static line once. A miss returns None so the caller uses live TTS."""

    def __init__(self, tts: Any) -> None:
        self._tts = tts
        self._cache: dict[str, dict[str, list[Any]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def prepare(self, language: str) -> None:
        if self._tts is None or language in self._tasks:
            return
        self._tasks[language] = asyncio.create_task(self._render(language))

    async def _render(self, language: str) -> None:
        rendered: dict[str, list[Any]] = {}
        for text in static_verbatim_lines(language):
            try:
                rendered[text] = await self._synthesize(text)
            except Exception:  # noqa: BLE001
                logger.warning("verbatim cache render failed lang=%s chars=%d", language, len(text))
        self._cache[language] = rendered

    async def _synthesize(self, text: str) -> list[Any]:
        stream = self._tts.stream()
        try:
            stream.push_text(text)
            stream.end_input()
            return [ev.frame async for ev in stream]
        finally:
            await stream.aclose()

    def lookup(self, text: str, *, language: str) -> list[Any] | None:
        rendered = self._cache.get(language) or {}
        frames = rendered.get(text)
        if frames:
            logger.info("verbatim cache hit lang=%s chars=%d", language, len(text))
            return frames
        logger.info("verbatim cache miss lang=%s chars=%d", language, len(text))
        return None
