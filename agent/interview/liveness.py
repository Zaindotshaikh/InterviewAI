"""Silence escalation and drop/rejoin handling for a live call (LiveKit-facing, kept apart from the flow logic)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("interview-v2.liveness")


class SilenceMonitor:
    """Escalates when the candidate goes quiet: nudge, rephrase, check they are there, then end as incomplete."""

    def __init__(self, *, session: Any, agent: Any, flow: Any, spacing_s: float) -> None:
        self._session = session
        self._agent = agent
        self._flow = flow
        self._spacing = spacing_s
        self._task: asyncio.Task[None] | None = None

    def attach(self) -> None:
        self._session.on("user_state_changed", self._on_state)

    def _on_state(self, ev: Any) -> None:
        if ev.new_state == "away":
            if self._task is None or self._task.done():
                self._task = asyncio.get_running_loop().create_task(self._run())
        else:
            self.cancel()

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _run(self) -> None:
        level = 0
        try:
            while not self._flow.done:
                level += 1
                # Never talk over ourselves.
                while getattr(self._session, "agent_state", "listening") in ("speaking", "thinking"):
                    await asyncio.sleep(0.4)
                move = self._flow.silence(level)
                logger.info("silence level=%d move=%s", level, move.kind)
                await self._agent.speak_move(move)
                if move.end_session:
                    return
                await asyncio.sleep(self._spacing + 6)
        except asyncio.CancelledError:
            pass


class ConnectionGuard:
    """Handles the candidate dropping (network, refresh) and coming back, without losing the interview."""

    def __init__(self, *, room: Any, agent: Any, flow: Any, grace_s: float) -> None:
        self._room = room
        self._agent = agent
        self._flow = flow
        self._grace = grace_s
        self._grace_task: asyncio.Task[None] | None = None
        self._dropped = False

    def attach(self) -> None:
        self._room.on("participant_disconnected", self._on_disconnected)
        self._room.on("participant_connected", self._on_connected)

    def _on_disconnected(self, participant: Any) -> None:
        if self._flow.done or self._dropped:
            return
        self._dropped = True
        logger.info("candidate disconnected; waiting %.0fs for them to return", self._grace)
        self._grace_task = asyncio.get_running_loop().create_task(self._expire())

    def _on_connected(self, participant: Any) -> None:
        if not self._dropped or self._flow.done:
            return
        self._dropped = False
        if self._grace_task is not None:
            self._grace_task.cancel()
            self._grace_task = None
        asyncio.get_running_loop().create_task(self._welcome_back())

    async def _welcome_back(self) -> None:
        await asyncio.sleep(1.5)  # let their audio track attach before speaking
        try:
            await self._agent.speak_move(self._flow.resume())
        except Exception:  # noqa: BLE001
            logger.exception("could not welcome candidate back")

    async def _expire(self) -> None:
        try:
            await asyncio.sleep(self._grace)
        except asyncio.CancelledError:
            return
        if self._flow.done or not self._dropped:
            return
        logger.info("candidate did not return; ending interview as incomplete")
        move = self._flow.force_complete("incomplete_disconnect")
        move.end_session = True
        # Nobody is listening, so do not speak; just record and close.
        self._agent._finish_if_needed(move)  # noqa: SLF001
        self._agent.spawn(self._agent._persist(move.events))  # noqa: SLF001
