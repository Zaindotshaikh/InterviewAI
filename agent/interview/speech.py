"""Single floor for agent TTS. One utterance at a time; fillers yield to Director.

Call sites start audio only through ``SpeechArbiter.play`` (``InterviewAgent.speak``).
Sources: director, filler, silence, verbatim, watchdog.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Literal

logger = logging.getLogger("interview-v2.speech")

SpeechSource = Literal["director", "filler", "silence", "verbatim", "watchdog"]

VALID_SOURCES = frozenset({"director", "filler", "silence", "verbatim", "watchdog"})
# Do not queue behind an in-flight utterance — skip instead.
LOW_PRIORITY = frozenset({"filler", "watchdog"})
# Cancel these when Director / silence / verbatim / watchdog claims the floor.
PREEMPTABLE = frozenset({"filler"})


def source_for_move(kind: str) -> SpeechSource:
    if (kind or "").startswith("silence"):
        return "silence"
    return "director"


def interrupt_handle(handle: Any) -> None:
    """Stop in-flight LiveKit speech. Adaptive barge-in still uses SpeechHandle.interrupt."""
    if handle is None:
        return
    interrupt = getattr(handle, "interrupt", None)
    if not callable(interrupt):
        return
    try:
        interrupt(force=True)
    except TypeError:
        try:
            interrupt()
        except Exception:  # noqa: BLE001
            logger.debug("speech.interrupt failed", exc_info=True)
    except Exception:  # noqa: BLE001
        logger.debug("speech.interrupt failed", exc_info=True)


async def await_playout(handle: Any) -> None:
    """Wait until a SpeechHandle finishes (say / generate_reply return handles, not coroutines)."""
    if handle is None:
        return
    wait = getattr(handle, "wait_for_playout", None)
    try:
        if callable(wait):
            await wait()
        elif hasattr(handle, "__await__"):
            await handle
    except Exception:  # noqa: BLE001
        logger.exception("speech playout wait failed")


class SpeechArbiter:
    """Serialize agent TTS. Fillers and watchdog skip if a real utterance is in flight."""

    def __init__(self) -> None:
        self._mu = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()
        self._current: str | None = None
        self._handles: list[Any] = []
        self._seq = 0

    @property
    def current_source(self) -> str | None:
        return self._current

    @property
    def seq(self) -> int:
        return self._seq

    def busy(self) -> bool:
        return self._current is not None

    async def acquire(self, source: str, *, detail: str = "") -> bool:
        if source not in VALID_SOURCES:
            source = "director"
        while True:
            async with self._mu:
                if self._current is None:
                    self._claim(source, detail=detail)
                    return True
                if source in LOW_PRIORITY:
                    logger.info("speech.rejected source=%s current=%s", source, self._current)
                    return False
                if self._current in PREEMPTABLE:
                    self._preempt(source, detail=detail)
                    return True
                logger.info("speech.queued source=%s current=%s", source, self._current)
            await self._idle.wait()

    def note_handle(self, handle: Any) -> None:
        if handle is not None:
            self._handles.append(handle)

    def release(self, source: str) -> None:
        if self._current != source:
            return
        logger.info("speech.end source=%s seq=%s", source, self._seq)
        self._current = None
        self._handles = []
        self._idle.set()

    def release_if(self, source: str, seq: int) -> None:
        if self._seq != seq:
            return
        self.release(source)

    async def play(
        self,
        source: str,
        *starts: Callable[[], Any],
        wait: bool = True,
        detail: str = "",
    ) -> bool:
        """Claim the floor, invoke each start() (must return a SpeechHandle), then wait or background-release.

        Returns False when this source is skipped because a higher-priority utterance is already playing.
        """
        if not starts:
            raise TypeError("play() requires at least one start callable")
        ok = await self.acquire(source, detail=detail)
        if not ok:
            return False
        seq = self._seq
        handles: list[Any] = []
        try:
            for start in starts:
                handle = start()
                self.note_handle(handle)
                handles.append(handle)
        except Exception:
            self.release_if(source, seq)
            raise
        if wait:
            try:
                for handle in handles:
                    await await_playout(handle)
                return True
            finally:
                self.release_if(source, seq)
        asyncio.get_running_loop().create_task(self._wait_and_release(source, seq, handles))
        return True

    async def _wait_and_release(self, source: str, seq: int, handles: list[Any]) -> None:
        try:
            for handle in handles:
                await await_playout(handle)
        finally:
            self.release_if(source, seq)

    def _claim(self, source: str, *, detail: str = "") -> None:
        self._seq += 1
        self._current = source
        self._handles = []
        self._idle.clear()
        extra = f" detail={detail}" if detail else ""
        logger.info("speech.start source=%s seq=%s%s", source, self._seq, extra)

    def _preempt(self, source: str, *, detail: str = "") -> None:
        prev = self._current
        for handle in self._handles:
            interrupt_handle(handle)
        self._handles = []
        logger.info("speech.preempted current=%s by=%s", prev, source)
        self._claim(source, detail=detail)
