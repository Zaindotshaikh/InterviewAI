"""Turn-taking policy: when has the candidate finished, and when is an overlap a real interruption.

Why this exists. A fixed silence timer cannot tell "finished" from "thinking in a second language".
Nurses answering in Marathi or Tamil pause mid-thought to find words, and cutting them off is the
fastest way to make an interviewer feel robotic. The policy combines:

* a semantic end-of-turn model (LiveKit) that waits when the candidate is clearly mid-thought,
* dynamic endpointing that learns each candidate's own pause length during the call,
* a higher silence floor for languages the semantic model does not cover,
* adaptive interruption handling so "haan" / "mm-hmm" / a cough does not stop the agent,
* recovery when speech was heard but no transcript came back,
* structured logs and one summary event per call, so tuning is driven by data.

Everything is settings-driven and degrades to plain VAD turn-taking if a model is unavailable.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections.abc import Awaitable, Callable
from typing import Any

from config import Settings
from interview.language import native_script_reminder

logger = logging.getLogger("interview-v2.turns")

# Languages of ours that LiveKit's semantic end-of-turn model ships thresholds for (its docs list 14
# languages; Hindi and English are the only ones we use). Marathi, Tamil, Telugu, Kannada and
# Malayalam are not covered, so for them silence is the main signal.
DETECTOR_LANGUAGES = frozenset({"en", "hi"})

MAX_BACKEND_EVENTS = 25

REPEAT_DIRECTIVE = (
    "CONTROLLER DIRECTIVE: You could not make out what the candidate just said. "
    "In one short, warm sentence in the interview language, say sorry and ask them to say it again. "
    "Do not move on to the next question and do not blame the candidate."
)


def detector_covers(language: str) -> bool:
    return language.split("-")[0].lower() in DETECTOR_LANGUAGES


def endpointing_options(language: str, settings: Settings) -> dict[str, Any]:
    """Endpointing config for a language. Uncovered languages get a higher silence floor."""
    covered = settings.turn_detector_enabled and detector_covers(language)
    min_delay = settings.endpointing_min_delay if covered else settings.endpointing_min_delay_uncovered
    return {
        "mode": settings.endpointing_mode,
        "min_delay": min_delay,
        "max_delay": max(settings.endpointing_max_delay, min_delay),
        "alpha": settings.endpointing_alpha,
    }


def build_turn_detector(settings: Settings) -> Any | None:
    """LiveKit's audio end-of-turn model, or None if disabled or unavailable."""
    if not settings.turn_detector_enabled:
        return None
    try:
        from livekit.agents import inference

        return inference.TurnDetector()
    except Exception:  # noqa: BLE001
        logger.warning("Turn detector unavailable; using VAD turn detection", exc_info=True)
        return None


def build_turn_handling(
    language: str,
    settings: Settings,
    *,
    has_vad: bool,
    detector: Any | None = None,
    stt_aligned: bool | str = False,
) -> dict[str, Any]:
    """Options for ``AgentSession(turn_handling=...)``."""
    if not has_vad:
        turn_detection: Any = "stt"
    else:
        turn_detection = detector if detector is not None else "vad"

    # When STT has no word alignment, raise min_words so short backchannels (हाँ/जी) don't barge in.
    aligned = bool(stt_aligned)
    min_words = (
        settings.interruption_min_words
        if aligned
        else max(settings.interruption_min_words, settings.interruption_min_words_no_align)
    )
    interruption: dict[str, Any] = {
        "enabled": True,
        "mode": settings.interruption_mode if has_vad else "vad",
        "min_words": min_words,
        "false_interruption_timeout": settings.false_interruption_timeout,
        "resume_false_interruption": True,
    }
    return {
        "turn_detection": turn_detection,
        "endpointing": endpointing_options(language, settings),
        "interruption": interruption,
        "preemptive_generation": {"enabled": settings.preemptive_generation},
        "user_turn_limit": {"max_duration": 90.0},
    }


def apply_language_profile(session: Any, language: str, settings: Settings) -> None:
    """Re-tune endpointing when the interview language changes mid-call."""
    opts = endpointing_options(language, settings)
    try:
        session.update_options(
            endpointing_opts={"min_delay": opts["min_delay"], "max_delay": opts["max_delay"]},
        )
    except Exception:  # noqa: BLE001
        logger.exception("could not update endpointing for %s", language)


def summarize(eou_delays: list[float], counters: dict[str, int]) -> dict[str, Any]:
    """Per-call turn-taking summary posted to the backend."""
    summary: dict[str, Any] = dict(counters)
    summary["turns"] = len(eou_delays)
    if eou_delays:
        summary["eou_delay_median_s"] = round(statistics.median(eou_delays), 3)
        summary["eou_delay_max_s"] = round(max(eou_delays), 3)
    return summary


class TurnWatchdog:
    """Watches turn-taking health: logs, counts, and recovers when speech is heard but not transcribed."""

    def __init__(
        self,
        *,
        session: Any,
        backend: Any,
        interview_id: str,
        settings: Settings,
        is_listening_armed: Callable[[], bool] | None = None,
        get_language: Callable[[], str] | None = None,
        speak: Callable[..., Awaitable[bool]] | None = None,
    ) -> None:
        self._session = session
        self._backend = backend
        self._interview_id = interview_id
        self._settings = settings
        self._is_listening_armed = is_listening_armed
        self._get_language = get_language
        self._speak = speak
        self._eou_delays: list[float] = []
        self._counters = {
            "transcription_timeouts": 0,
            "false_interruptions": 0,
            "repeat_prompts": 0,
            "interim_salvages": 0,
            "preamble_skips": 0,
        }
        self._events_sent = 0
        self._tasks: set[Any] = set()

    def _armed(self) -> bool:
        if self._is_listening_armed is None:
            return True
        try:
            return bool(self._is_listening_armed())
        except Exception:  # noqa: BLE001
            return True

    def attach(self) -> None:
        self._session.on("user_transcription_timeout", self._on_transcription_timeout)
        self._session.on("agent_false_interruption", self._on_false_interruption)
        self._session.on("metrics_collected", self._on_metrics)

    def summary(self) -> dict[str, Any]:
        return summarize(self._eou_delays, self._counters)

    async def post_summary(self) -> None:
        try:
            await self._backend.post_event(self._interview_id, "turn.summary", self.summary())
        except Exception:  # noqa: BLE001
            logger.exception("could not post turn summary")

    def _on_metrics(self, ev: Any) -> None:
        metrics = getattr(ev, "metrics", None)
        if getattr(metrics, "type", None) != "eou_metrics":
            return
        self._eou_delays.append(float(metrics.end_of_utterance_delay))
        logger.info(
            "turn eou_delay=%.2fs transcription_delay=%.2fs hook_delay=%.2fs",
            metrics.end_of_utterance_delay,
            metrics.transcription_delay,
            metrics.on_user_turn_completed_delay,
        )

    def _on_false_interruption(self, ev: Any) -> None:
        self._counters["false_interruptions"] += 1
        resumed = bool(getattr(ev, "resumed", False))
        logger.info("false interruption (resumed=%s) — interviewer should continue", resumed)
        self._spawn(
            self._post_event("turn.false_interruption", {"resumed": resumed})
        )

    def _on_transcription_timeout(self, ev: Any) -> None:
        self._counters["transcription_timeouts"] += 1
        speech_s = float(getattr(ev, "speech_duration", 0.0))
        logger.warning("speech heard (%.1fs) but no transcript arrived", speech_s)
        self._spawn(self._post_event("turn.transcription_timeout", {"speech_duration_s": round(speech_s, 2)}))
        # Prefer promoting interim STT text (Scribe often has the digits already) over
        # asking the candidate to repeat cold.
        self._spawn(self._salvage_or_repeat())

    def _speech_busy(self) -> bool:
        owner = getattr(self._speak, "__self__", None)
        if owner is None:
            return False
        for name in ("speech_busy", "busy"):
            fn = getattr(owner, name, None)
            if callable(fn):
                try:
                    return bool(fn())
                except Exception:  # noqa: BLE001
                    return False
        return False

    async def _salvage_or_repeat(self) -> None:
        if getattr(self._session, "agent_state", None) in ("speaking", "thinking"):
            return
        # During opening settle, ignore ambient STT — do not salvage junk into a real turn.
        if not self._armed():
            self._counters["preamble_skips"] += 1
            logger.info("skipping transcript salvage — listening not armed yet")
            self._spawn(self._post_event("audio.preamble_skip", {"reason": "transcription_timeout"}))
            return
        commit = getattr(self._session, "commit_user_turn", None)
        if callable(commit):
            try:
                result = commit(transcript_timeout=1.5, stt_flush_duration=0.5)
                transcript = await result if hasattr(result, "__await__") else result
                if str(transcript or "").strip():
                    self._counters["interim_salvages"] += 1
                    logger.info("salvaged interim transcript after STT timeout (%d chars)", len(str(transcript)))
                    return
            except Exception:  # noqa: BLE001
                logger.exception("could not salvage interim transcript")
        self._maybe_ask_to_repeat()

    def _maybe_ask_to_repeat(self) -> None:
        if self._counters["repeat_prompts"] >= self._settings.max_repeat_prompts:
            return
        # Never talk over the agent itself; a transcript may also still be on its way.
        if getattr(self._session, "agent_state", None) in ("speaking", "thinking"):
            return
        if not self._armed():
            return
        if self._speech_busy():
            return
        instructions = REPEAT_DIRECTIVE
        if self._get_language is not None:
            lang = self._get_language()
            if lang:
                instructions = f"{REPEAT_DIRECTIVE}\n{native_script_reminder(lang)}"
        if self._speak is None:
            try:
                self._session.generate_reply(instructions=instructions)
                self._counters["repeat_prompts"] += 1
            except Exception:  # noqa: BLE001
                logger.exception("could not ask the candidate to repeat")
            return
        self._spawn(self._repeat_via_speak(instructions))

    async def _repeat_via_speak(self, instructions: str) -> None:
        try:
            ok = await self._speak(
                "watchdog",
                lambda: self._session.generate_reply(instructions=instructions),
                wait=False,
                detail="repeat",
            )
            if ok:
                self._counters["repeat_prompts"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("could not ask the candidate to repeat")

    async def _post_event(self, event_type: str, data: dict[str, Any]) -> None:
        if self._events_sent >= MAX_BACKEND_EVENTS:
            return
        self._events_sent += 1
        data = {**data, "ts": round(time.time(), 3)}
        try:
            await self._backend.post_event(self._interview_id, event_type, data)
        except Exception:  # noqa: BLE001
            logger.exception("could not post %s", event_type)

    def _spawn(self, coro: Any) -> None:
        import asyncio

        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
