"""Glue between the live call and the interview flow.

The director owns the per-call conversational memory (last question, recent turns), starts the analyst as soon as a
final transcript arrives (so it overlaps the end-of-turn wait), and turns each candidate utterance into a `Move`.
It has no LiveKit dependency, so it is unit-testable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from interview.analysis import TurnAnalyzer, heuristic_analysis, recover_care_updates
from interview.flow import InterviewFlow, Move
from interview.guards import sanitize_candidate_text
from interview.phone_speech import has_spoken_words
from interview.plan import classify_answer

logger = logging.getLogger("interview-v2.director")

RECENT_TURNS = 8


class Director:
    def __init__(
        self,
        flow: InterviewFlow,
        analyzer: TurnAnalyzer,
        *,
        recent: list[dict[str, str]] | None = None,
        is_listening_armed: Callable[[], bool] | None = None,
    ) -> None:
        self.flow = flow
        self.analyzer = analyzer
        self.recent: list[dict[str, str]] = list(recent or [])[-RECENT_TURNS:]
        self.last_agent_text = ""
        self._finals: list[str] = []
        self._early: tuple[str, str, asyncio.Task[Any]] | None = None  # (text, payload, task)
        self._is_listening_armed = is_listening_armed

    def _armed(self) -> bool:
        if self._is_listening_armed is None:
            return True
        try:
            return bool(self._is_listening_armed())
        except Exception:  # noqa: BLE001
            return True

    # ------------------------------------------------------------------------------------------ conversation

    def note_assistant(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.last_agent_text = text
        self._push("assistant", text)
        # The most recent thing asked is what the next answer is judged against.
        if "?" in text:
            self.flow.state.last_question = text[-400:]

    def note_user(self, text: str) -> None:
        if text:
            self._push("user", text)

    def _push(self, role: str, text: str) -> None:
        self.recent.append({"role": role, "text": text[:600]})
        del self.recent[:-RECENT_TURNS]

    # ----------------------------------------------------------------------------------------------- analysis

    def _prepare(self, text: str) -> tuple[str, Any]:
        payload = self.flow.analysis_payload(text, self.last_agent_text, self.recent)
        pending = self.flow.pending_confirmation()
        fallback = heuristic_analysis(
            text,
            pending_field=pending[0] if pending else "",
            pending_value=pending[1] if pending else "",
        )
        return payload, fallback

    def on_final_transcript(self, text: str) -> None:
        """Start analysing now; the turn is usually confirmed 0.4-1.5s later, so this hides most of the latency."""
        if self.flow.done or not self.analyzer.available:
            return
        if not self._armed():
            return
        self._finals.append(sanitize_candidate_text(text))
        joined = " ".join(t for t in self._finals if t).strip()
        if classify_answer(joined) == "noise":
            return
        self._cancel_early()
        payload, fallback = self._prepare(joined)
        task = asyncio.get_running_loop().create_task(
            self.analyzer.analyze(payload, clinical=self.flow.wants_clinical_model, fallback=fallback)
        )
        self._early = (joined, payload, task)

    def _cancel_early(self) -> None:
        if self._early is not None:
            self._early[2].cancel()
            self._early = None

    async def decide(self, text: str) -> Move:
        """Turn the confirmed utterance into the next move."""
        early, self._early = self._early, None
        self._finals = []
        if not self._armed():
            if early:
                early[2].cancel()
            return self.flow.noise_move()
        if classify_answer(text) == "noise":
            if early:
                early[2].cancel()
            return self.flow.noise_move()

        payload, fallback = self._prepare(text)
        phone_check = None
        if self._needs_phone_check(text):
            phone_check = asyncio.create_task(self.analyzer.hear_phone_digits(text))
        if early and early[1] == payload:
            try:
                analysis = await early[2]
            except Exception:  # noqa: BLE001
                analysis = fallback
        else:
            if early:
                early[2].cancel()
            analysis = await self.analyzer.analyze(
                payload, clinical=self.flow.wants_clinical_model, fallback=fallback
            )
        # Care focus (intro or single item): recover clear हाँ/नहीं if the LLM omitted care_updates.
        # Experience-dump हाँ is still rejected inside recover_care_updates / infer_care_accept.
        if self.flow.state.focus.get("type") == "care":
            items = [str(i) for i in (self.flow.state.focus.get("items") or [])]
            before = len(analysis.care_updates)
            analysis = recover_care_updates(analysis, text=text, item_ids=items)
            if len(analysis.care_updates) > before:
                logger.info("care stance recovered from utterance for items=%s", items)

        analysis.raw_utterance = text
        if phone_check is not None:
            try:
                analysis.phone_hint = await phone_check
            except Exception:  # noqa: BLE001
                logger.debug("phone digit check skipped", exc_info=True)
                analysis.phone_hint = ""
        logger.info(
            "analysis source=%s intent=%s clarity=%s stage=%s latency=%.0fms",
            analysis.source,
            analysis.intent,
            analysis.intelligibility,
            self.flow.stage,
            self.analyzer.last_latency_ms,
        )
        move = self.flow.apply(analysis)
        # Tone is outside Flow policy. Empathy override only when DIRECTOR_EMPATHY_TONE=true.
        try:
            from config import get_settings
            from interview.voice_tone import resolve_tone

            settings = get_settings()
            empathy: str | None = None
            if settings.director_empathy_tone:
                empathy = analysis.empathy_tone or None
                if not empathy and (
                    analysis.nervous
                    or any(c.stance in ("hesitant", "refuses") for c in analysis.care_updates)
                ):
                    empathy = "gentle"
            move.tone = resolve_tone(
                move.kind,
                empathy_tone=empathy,
                empathy_enabled=settings.director_empathy_tone,
            )
        except Exception:  # noqa: BLE001
            logger.debug("tone resolve skipped", exc_info=True)
        return move

    def _needs_phone_check(self, text: str) -> bool:
        """Hear number-words. Digits alone are already the number."""
        if not has_spoken_words(text):
            return False
        focus = self.flow.state.focus or {}
        on_phone = focus.get("type") == "slots" and "phone" in (focus.get("ids") or [])
        pending = self.flow.pending_confirmation()
        on_confirm = False
        if pending:
            spec = self.flow.bp.field_spec(pending[0])
            on_confirm = spec is not None and spec.kind == "phone"
        return on_phone or on_confirm
