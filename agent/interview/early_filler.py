"""Phase 3 optional: start ack filler on VAD silence + interim transcript; cancel if speech resumes."""

from __future__ import annotations

import logging
from typing import Any

from interview.fillers import FillerPlayer, frames_iter

logger = logging.getLogger("interview-v2.early_filler")


class EarlyFiller:
    def __init__(
        self,
        *,
        session: Any,
        fillers: FillerPlayer | None,
        language: str,
        enabled: bool,
        on_start: Any | None = None,
    ) -> None:
        self._session = session
        self._fillers = fillers
        self._language = language
        self._enabled = enabled
        self._on_start = on_start
        self._interim = ""
        self._started = False
        self._false_starts = 0
        self._starts = 0

    def attach(self) -> None:
        if not self._enabled or self._fillers is None:
            return
        self._session.on("user_input_transcribed", self._on_transcribed)
        self._session.on("user_state_changed", self._on_user_state)

    def _on_transcribed(self, ev: Any) -> None:
        text = (getattr(ev, "transcript", None) or "").strip()
        if not text:
            return
        if not getattr(ev, "is_final", False):
            self._interim = text
            return
        self._interim = ""

    def _on_user_state(self, ev: Any) -> None:
        old, new = getattr(ev, "old_state", None), getattr(ev, "new_state", None)
        # Candidate paused (speaking → listening) with some interim text → try early ack.
        if old == "speaking" and new == "listening" and self._interim and not self._started:
            picked = self._fillers.pick(self._language, self._interim, bucket="neutral")
            if picked is None:
                return
            text, frames = picked
            self._started = True
            self._starts += 1
            if self._on_start:
                self._on_start()
            try:
                self._session.say(text, audio=frames_iter(frames), add_to_chat_ctx=False)
                logger.info("early filler started false_starts=%s starts=%s", self._false_starts, self._starts)
            except Exception:  # noqa: BLE001
                logger.exception("early filler say failed")
                self._started = False
        # Resumed speaking → count false start (filler may already be playing).
        if self._started and new == "speaking":
            self._false_starts += 1
            self._started = False
            logger.info(
                "early filler false-start rate≈%.2f (%s/%s)",
                self._false_starts / max(1, self._starts),
                self._false_starts,
                self._starts,
            )

    def stats(self) -> dict[str, float | int]:
        return {
            "starts": self._starts,
            "false_starts": self._false_starts,
            "false_start_rate": round(self._false_starts / max(1, self._starts), 3),
        }
