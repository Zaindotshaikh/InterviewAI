"""Per-turn latency waterfall for voice A/B (Phase 1).

Headline metric: time-to-first-audio from VAD end of candidate speech (`ttfa_vad_ms`).
Also persist confirm-to-first-audio (`ttfa_confirm_ms`).
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Any

logger = logging.getLogger("interview-v2.latency")

# Allow LLM/TTS metric events to land after first audio before flushing the turn.
_FLUSH_DELAY_S = 1.5


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    # Nearest-rank
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[k], 1)


def summarize_turns(turns: list[dict[str, Any]]) -> dict[str, Any]:
    def col(key: str) -> list[float]:
        out: list[float] = []
        for t in turns:
            v = t.get(key)
            if isinstance(v, (int, float)):
                out.append(float(v))
        return out

    summary: dict[str, Any] = {"turns": len(turns)}
    for key in (
        "ttfa_vad_ms",
        "ttfa_confirm_ms",
        "filler_from_vad_ms",
        "director_ms",
        "llm_ttft_ms",
        "tts_ttfb_ms",
        "eou_delay_ms",
        "transcription_delay_ms",
        "hook_ms",
    ):
        vals = col(key)
        if not vals:
            continue
        summary[key] = {
            "n": len(vals),
            "p50": percentile(vals, 50),
            "p95": percentile(vals, 95),
            "max": round(max(vals), 1),
            "mean": round(statistics.fmean(vals), 1),
        }
    return summary


class LatencyTracker:
    """Collects one turn at a time and posts `turn.latency` events when enabled."""

    def __init__(
        self,
        *,
        backend: Any,
        interview_id: str,
        enabled: bool,
        spawn: Any,
    ) -> None:
        self._backend = backend
        self._interview_id = interview_id
        self._enabled = enabled
        self._spawn = spawn
        self._turn_index = 0
        self._cur: dict[str, Any] | None = None
        self._turns: list[dict[str, Any]] = []
        self._awaiting_first_audio = False
        self._flush_task: asyncio.Task[Any] | None = None

    def attach(self, session: Any) -> None:
        if not self._enabled:
            return
        session.on("metrics_collected", self._on_metrics)
        session.on("user_state_changed", self._on_user_state)
        session.on("agent_state_changed", self._on_agent_state)
        session.on("user_input_transcribed", self._on_transcribed)

    def _ensure_turn(self) -> dict[str, Any]:
        if self._cur is None:
            self._cur = {"mono_marks": {}}
        return self._cur

    def _mark(self, name: str, when: float | None = None) -> None:
        cur = self._ensure_turn()
        marks: dict[str, float] = cur.setdefault("mono_marks", {})
        if name not in marks:
            marks[name] = when if when is not None else time.monotonic()

    def _on_user_state(self, ev: Any) -> None:
        # VAD end of speech: user leaves "speaking".
        old = getattr(ev, "old_state", None)
        new = getattr(ev, "new_state", None)
        if old == "speaking" and new != "speaking":
            self._mark("vad_speech_end")

    def _on_transcribed(self, ev: Any) -> None:
        if getattr(ev, "is_final", False) and getattr(ev, "transcript", None):
            self._mark("stt_final")

    def _on_agent_state(self, ev: Any) -> None:
        new = getattr(ev, "new_state", None)
        if new == "speaking" and self._awaiting_first_audio:
            self._mark("first_audio")
            self._awaiting_first_audio = False
            self._maybe_finalize()

    def _on_metrics(self, ev: Any) -> None:
        metrics = getattr(ev, "metrics", None)
        if metrics is None:
            return
        mtype = getattr(metrics, "type", None)
        cur = self._ensure_turn()
        if mtype == "eou_metrics":
            eou = float(getattr(metrics, "end_of_utterance_delay", 0.0) or 0.0)
            tx = float(getattr(metrics, "transcription_delay", 0.0) or 0.0)
            hook = float(getattr(metrics, "on_user_turn_completed_delay", 0.0) or 0.0)
            cur["eou_delay_ms"] = round(eou * 1000, 1)
            cur["transcription_delay_ms"] = round(tx * 1000, 1)
            cur["hook_ms_sdk"] = round(hook * 1000, 1)
            # If user_state_changed missed, estimate VAD end from metrics emission time.
            if "vad_speech_end" not in cur.get("mono_marks", {}):
                self._mark("vad_speech_end", time.monotonic() - eou)
        elif mtype == "llm_metrics":
            ttft = getattr(metrics, "ttft", None)
            if isinstance(ttft, (int, float)) and ttft >= 0:
                cur["llm_ttft_ms"] = round(float(ttft) * 1000, 1)
        elif mtype == "tts_metrics":
            ttfb = getattr(metrics, "ttfb", None)
            if isinstance(ttfb, (int, float)) and ttfb >= 0:
                # Keep the first TTFB of the reply (ignore later segments if any).
                cur.setdefault("tts_ttfb_ms", round(float(ttfb) * 1000, 1))

    def on_hook_start(self, turn_index: int) -> None:
        if not self._enabled:
            return
        # Previous turn may still be waiting on first audio; finalize with what we have.
        if self._cur is not None and self._cur.get("hook_started"):
            self._finalize(force=True)
        self._turn_index = turn_index
        self._cur = {
            "turn_index": turn_index,
            "mono_marks": {},
            "hook_started": True,
        }
        self._mark("turn_confirm")
        self._mark("hook_start")
        self._awaiting_first_audio = True

    def on_filler_start(self) -> None:
        if not self._enabled:
            return
        self._mark("filler_start")

    def on_director_done(self, duration_s: float) -> None:
        if not self._enabled:
            return
        cur = self._ensure_turn()
        cur["director_ms"] = round(max(0.0, duration_s) * 1000, 1)

    def on_hook_end(self) -> None:
        if not self._enabled:
            return
        self._mark("hook_end")
        cur = self._ensure_turn()
        marks = cur.get("mono_marks") or {}
        if "hook_start" in marks and "hook_end" in marks:
            cur["hook_ms"] = round((marks["hook_end"] - marks["hook_start"]) * 1000, 1)

    def _maybe_finalize(self) -> None:
        cur = self._cur
        if not cur or not cur.get("hook_started"):
            return
        marks = cur.get("mono_marks") or {}
        if "first_audio" not in marks:
            return
        if self._flush_task and not self._flush_task.done():
            return

        async def _delayed() -> None:
            await asyncio.sleep(_FLUSH_DELAY_S)
            self._finalize(force=False)

        try:
            self._flush_task = asyncio.get_running_loop().create_task(_delayed())
        except RuntimeError:
            self._finalize(force=False)

    def _finalize(self, *, force: bool) -> None:
        cur = self._cur
        if cur is None or cur.get("_flushed"):
            return
        marks: dict[str, float] = cur.get("mono_marks") or {}
        if not force and "first_audio" not in marks:
            return

        def delta_ms(start: str, end: str) -> float | None:
            if start not in marks or end not in marks:
                return None
            return round((marks[end] - marks[start]) * 1000, 1)

        payload = {
            "turn_index": cur.get("turn_index", self._turn_index),
            "ttfa_vad_ms": delta_ms("vad_speech_end", "first_audio"),
            "ttfa_confirm_ms": delta_ms("turn_confirm", "first_audio"),
            "filler_from_vad_ms": delta_ms("vad_speech_end", "filler_start"),
            "director_ms": cur.get("director_ms"),
            "llm_ttft_ms": cur.get("llm_ttft_ms"),
            "tts_ttfb_ms": cur.get("tts_ttfb_ms"),
            "eou_delay_ms": cur.get("eou_delay_ms"),
            "transcription_delay_ms": cur.get("transcription_delay_ms"),
            "hook_ms": cur.get("hook_ms") or cur.get("hook_ms_sdk"),
            "marks_present": sorted(marks.keys()),
        }
        cur["_flushed"] = True
        self._turns.append(payload)
        self._cur = None
        self._awaiting_first_audio = False
        logger.info(
            "turn.latency turn=%s ttfa_vad=%s ttfa_confirm=%s filler=%s director=%s llm_ttft=%s tts_ttfb=%s",
            payload["turn_index"],
            payload["ttfa_vad_ms"],
            payload["ttfa_confirm_ms"],
            payload["filler_from_vad_ms"],
            payload["director_ms"],
            payload["llm_ttft_ms"],
            payload["tts_ttfb_ms"],
        )
        self._spawn(self._backend.post_event(self._interview_id, "turn.latency", payload))

    def summary(self) -> dict[str, Any]:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        if self._cur is not None:
            self._finalize(force=True)
        return summarize_turns(self._turns)
