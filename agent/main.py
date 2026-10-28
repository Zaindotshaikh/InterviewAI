"""LiveKit Agents entrypoint for Indic interview v2."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from livekit.agents import (
    Agent,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
    JobProcess,
    StopResponse,
    WorkerOptions,
    cli,
)
from livekit.agents.llm import function_tool
from livekit.plugins import google as _google_plugin  # noqa: F401
from livekit.plugins import openai as _openai_plugin  # noqa: F401
from livekit.plugins import sarvam as _sarvam_plugin  # noqa: F401
from livekit.plugins import silero as _silero_plugin  # noqa: F401

try:
    from livekit.plugins import elevenlabs as _elevenlabs_plugin  # noqa: F401
except ImportError:  # pragma: no cover
    _elevenlabs_plugin = None  # type: ignore[assignment]

from backend import BackendClient
from config import get_settings
from interview import (
    BASE_VOICE_RULES,
    ELEVENLABS_EXPRESSIVE_RULES,
    Blueprint,
    Disfluency,
    FillerPlayer,
    FlowState,
    InterviewFlow,
    InterviewPlan,
    ControllerState,
    Move,
    TurnAnalyzer,
    TurnWatchdog,
    classify_answer,
    apply_language_profile,
    build_turn_detector,
    build_turn_handling,
    detect_script_language,
    frames_iter,
    get_profile,
    gpt_live_voice_instructions,
    opening_seed,
    native_script_reminder,
    sanitize_candidate_text,
    spoken_style,
)
from interview.director import Director
from interview.listen import ListenFloor, is_candidate_speech
from interview.early_filler import EarlyFiller
from interview.expressiveness import ExpressivenessEngine, filler_bucket_from_text
from interview.latency import LatencyTracker
from interview.liveness import ConnectionGuard, SilenceMonitor
from interview.prompts import ELEVENLABS_PLAIN_SPEECH_RULES
from interview.voice_tone import tone_for_kind
from providers import (
    SessionRefused,
    build_fallback_stt,
    build_llm,
    build_noise_cancellation,
    build_stt,
    build_tts,
    build_vad,
    google_voice_for,
    openai_stt_languages,
)

logger = logging.getLogger("interview-v2")


async def _abort_refused_session(ctx: JobContext, backend: BackendClient) -> None:
    """Leave before session.start so the room never greets on the wrong stack."""
    try:
        await ctx.room.disconnect()
    except Exception:  # noqa: BLE001
        logger.exception("disconnect after refused session failed")
    try:
        await backend.aclose()
    except Exception:  # noqa: BLE001
        logger.exception("backend close after refused session failed")


async def _iter_joined(chunks: list[str]):
    if chunks:
        yield "".join(chunks)


logging.basicConfig(level=logging.INFO)


def _as_meta_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _merge_job_payload(ctx: JobContext) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    raws: list[Any] = []
    try:
        raws.append(ctx.job.metadata)
    except Exception:  # noqa: BLE001
        pass
    try:
        raws.append(ctx.room.metadata)
    except Exception:  # noqa: BLE001
        pass
    for p in ctx.room.remote_participants.values():
        if p.metadata:
            raws.append(p.metadata)
    for raw in raws:
        merged.update(_as_meta_dict(raw))
    return merged


def _parse_interview_id(ctx: JobContext) -> str | None:
    interview_id = _merge_job_payload(ctx).get("interviewId")
    return str(interview_id) if interview_id else None


def _wants_avatar(payload: dict[str, Any]) -> bool:
    value = payload.get("avatar")
    return value is True or value == "true" or value == 1


def _tts_provider_override(payload: dict[str, Any], job_meta: dict[str, Any]) -> str | None:
    """Per-interview TTS override from start payload / job metadata (e.g. elevenlabs test route)."""
    raw = payload.get("ttsProvider") or job_meta.get("ttsProvider") or payload.get("tts_provider")
    if not raw:
        return None
    value = str(raw).strip().lower()
    return value if value in ("elevenlabs", "google", "openai", "sarvam", "mock") else None


def _voice_provider_override(payload: dict[str, Any], job_meta: dict[str, Any]) -> str | None:
    """Full-duplex voice path (e.g. gpt_live) — replaces cascade STT/LLM/TTS for that interview."""
    raw = payload.get("voiceProvider") or job_meta.get("voiceProvider") or payload.get("voice_provider")
    if not raw:
        return None
    value = str(raw).strip().lower()
    return value if value in ("gpt_live",) else None


# Instant speakable progress while Director runs (same delegation_id as the final directive).
_GPT_LIVE_ACK_COMMENTARY = (
    "Brief warm acknowledgement only — one short beat like हाँ / ठीक है / okay / hmm. "
    "Do NOT ask any new interview question, follow-up, or topic yet. "
    "Wait for the next CONTROLLER DIRECTIVE commentary."
)

_GPT_LIVE_FOCUS_LOCK_INSTRUCTIONS = (
    "Standing rule: ask ONLY what the current CONTROLLER focus allows. "
    "Never invent screening, clinical, salary, night-shift, join-date, hospital, or closing "
    "questions on your own. While waiting for CONTROLLER DIRECTIVE commentary after a "
    "delegation: brief ack/backchannel only — no new question."
)

# After we already spoke a question — must not trigger another spoken turn.
_GPT_LIVE_LISTEN_HOLD = (
    "LISTEN HOLD — you already asked the current question. Stay silent and wait for the "
    "candidate. Do NOT repeat, rephrase, or ask anything else until CONTROLLER DIRECTIVE "
    "commentary arrives."
)


def _gpt_live_commentary(move: Move, language: str) -> str:
    """Commentary the voice model paraphrases; keep under the ~500-token append cap."""
    if move.verbatim:
        return (
            "Say only this one sentence, then stop. Do not add a name, a reaction, or a second question:\n"
            f"{move.verbatim}"
        )
    lead = ""
    if move.kind == "opening":
        lead = (
            "OPENING — speak this greeting immediately. Do NOT wait for silence. "
            "Ignore ambient/ward noise or mic pickup; it is not the candidate's turn.\n"
        )
    text = (
        f"{lead}"
        "CONTROLLER DIRECTIVE — paraphrase naturally in the candidate's language; "
        "do not invent a different question or topic:\n"
        f"{move.directive}\n"
        f"{native_script_reminder(language)}"
    )
    return text[:1800]


async def _start_tavus_avatar(session: AgentSession, ctx: JobContext, settings) -> bool:  # noqa: ANN001
    api_key = settings.tavus_api_key or os.getenv("TAVUS_API_KEY")
    if not api_key:
        logger.error("avatar requested but TAVUS_API_KEY is not set")
        return False
    os.environ["TAVUS_API_KEY"] = api_key
    try:
        from livekit.plugins import tavus
    except Exception:  # noqa: BLE001
        logger.exception("livekit-plugins-tavus is not installed")
        return False
    kwargs: dict[str, Any] = {"api_key": api_key}
    if settings.tavus_face_id:
        kwargs["face_id"] = settings.tavus_face_id
    if settings.tavus_pal_id:
        kwargs["pal_id"] = settings.tavus_pal_id
    logger.info("starting Tavus avatar face_id=%s pal_id=%s", kwargs.get("face_id"), kwargs.get("pal_id"))
    avatar = tavus.AvatarSession(**kwargs)
    await avatar.start(session, room=ctx.room)
    try:
        await avatar.wait_for_join()
    except TimeoutError:
        logger.error("Tavus avatar did not publish video within 30s")
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Tavus wait_for_join failed")
        return False
    logger.info("Tavus avatar joined conversation_id=%s", getattr(avatar, "conversation_id", None))
    return True


def _unwrap_stt(stt: Any) -> list[Any]:
    """Return the concrete STT instances behind StreamAdapter / FallbackAdapter."""
    if stt is None:
        return []
    inner = getattr(stt, "wrapped_stt", None)
    if inner is not None:
        return _unwrap_stt(inner)
    children = getattr(stt, "_stt_instances", None)
    if children:
        out: list[Any] = []
        for child in children:
            out.extend(_unwrap_stt(child))
        return out
    return [stt]


def _switch_stt_language(stt: Any, code: str, settings) -> None:  # noqa: ANN001
    for inner in _unwrap_stt(stt):
        provider = getattr(inner, "provider", "") or type(inner).__module__
        try:
            if "sarvam" in str(provider).lower():
                inner.update_options(language=code)
            elif "elevenlabs" in str(provider).lower() or (
                _elevenlabs_plugin is not None and isinstance(inner, _elevenlabs_plugin.STT)
            ):
                from providers import _scribe_language_hints

                primary, secondary = _scribe_language_hints(code)
                try:
                    inner.update_options(language_code=primary, secondary_languages=secondary)
                except TypeError:
                    inner.update_options(language_code=primary)
            elif getattr(inner.capabilities, "keyterms", False):
                inner.update_options(language=openai_stt_languages(code))
            else:
                inner.update_options(language=code.split("-")[0])
        except Exception:  # noqa: BLE001
            logger.exception("STT language switch failed for %s", provider)


def _switch_tts_language(tts: Any, code: str, settings) -> None:  # noqa: ANN001
    if isinstance(tts, _google_plugin.TTS):
        if str(tts.model).startswith("gemini"):
            tts.update_options(language=code, voice_name=settings.google_tts_voice)
        else:
            locale, voice_name = google_voice_for(code, settings.model_copy(update={"google_tts_model": "chirp_3"}))
            tts.update_options(language=locale, voice_name=voice_name)
    elif isinstance(tts, _sarvam_plugin.TTS):
        tts.update_options(language_code=code, speaker=get_profile(code).tts_speaker)
    elif _elevenlabs_plugin is not None and isinstance(tts, _elevenlabs_plugin.TTS):
        from providers import elevenlabs_language, elevenlabs_voice_for

        tts.update_options(
            language=elevenlabs_language(code),
            voice_id=elevenlabs_voice_for(code, settings),
        )


class InterviewAgent(Agent):
    def __init__(
        self,
        *,
        plan: InterviewPlan,
        flow: InterviewFlow,
        director: Director,
        backend: BackendClient,
        session_ref: dict[str, Any],
        tts_provider: str | None = None,
        gpt_live: bool = False,
    ) -> None:
        settings = get_settings()
        voice = settings.google_tts_voice
        self._gpt_live = bool(gpt_live)
        self._tts_provider = (tts_provider or "").strip().lower()
        # /elevenlabs-interviewer locks TTS to ElevenLabs — never mid-call Chirp fallback.
        self._tts_locked_el = self._tts_provider == "elevenlabs"
        self._expressiveness_mode = settings.voice_expressiveness
        if self._gpt_live:
            # GPT-Live owns audio pacing/fillers; cascade TTS tags / Disfluency are not used.
            # Voice may be "gpt_live:marin" or "gpt_live:custom:voice_…" — use name for gender hints only.
            live_voice = "marin"
            if self._tts_provider.startswith("gpt_live:"):
                rest = self._tts_provider.split(":", 1)[1]
                live_voice = "marin" if rest.startswith("custom:") else (rest or "marin")
            instructions = gpt_live_voice_instructions(plan, voice=live_voice)
        else:
            if self._tts_provider == "elevenlabs":
                if self._expressiveness_mode == "engine":
                    expressive = f"\n\n{ELEVENLABS_PLAIN_SPEECH_RULES}"
                else:
                    expressive = f"\n\n{ELEVENLABS_EXPRESSIVE_RULES}"
            else:
                expressive = ""
            instructions = (
                f"{plan.system_prompt}\n\n{BASE_VOICE_RULES}\n\n{spoken_style(plan.language, voice)}\n\n"
                f"{native_script_reminder(plan.language)}{expressive}"
            )
        super().__init__(instructions=instructions)
        self.plan = plan
        self.flow = flow
        self.director = director
        self.backend = backend
        self.session_ref = session_ref
        self._turn_index = 0
        self._started_at = datetime.now(timezone.utc)
        self._persist_lock = asyncio.Lock()  # FIFO, so state patches reach the server in order
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closing = False
        # Chirp markup pauses only; never inject [pause short] on ElevenLabs (use audio tags instead).
        self._disfluency = Disfluency(
            settings.hesitation_rate,
            use_pause_tags=False,
            phrase_pause_rate=settings.phrase_pause_rate,
        )
        self._engine = ExpressivenessEngine(
            sigh_rate=settings.voice_sigh_rate,
            umm_rate=settings.voice_umm_rate,
            pause_rate=settings.voice_pause_rate,
            cooldown_turns=settings.voice_express_cooldown_turns,
        )
        # Set when a pre-rendered reaction was just played, so the reply's first sentence gets no um.
        self._suppress_lead = False
        self._greeting_pending = True
        # False until the opening greeting finishes — candidate audio is kept, but not acted on.
        self._listening_armed = False
        self._floor = ListenFloor()
        self.latency: LatencyTracker | None = None
        self._current_tone = "neutral"
        self._empathy_hint = False
        self._last_spoken = ""
        self._last_llm_text = ""
        self._interrupted = False
        self._previous_empathy = False
        # After LiveKit resumes a false barge-in, briefly discard ambient STT fragments.
        self._discard_user_until: float = 0.0
        self._delegation_wired = False
        # GPT-Live: drive Flow from user transcripts (like cascade). Delegation is backup only —
        # the voice model often acks without ever emitting delegation_created.
        self._gpt_live_user_buf: list[str] = []
        self._gpt_live_buf_started: float = 0.0
        # Wait for speech to STOP (partials keep resetting this). 0.7s was committing mid-answer.
        self._gpt_live_drive_settle_s: float = 1.15
        self._gpt_live_drive_gen: int = 0
        self._gpt_live_driving: bool = False
        self._gpt_live_last_user: str = ""
        self._gpt_live_last_user_at: float = 0.0
        self._gpt_live_last_committed: str = ""
        self._gpt_live_open_dep_id: str | None = None
        self._gpt_live_ignore_until: float = 0.0
        self._gpt_live_held_voice: bool = False
        self._floor_watch_started = False

    def is_listening_armed(self) -> bool:
        return bool(self._listening_armed)

    def _set_candidate_mic(self, enabled: bool, *, reason: str) -> None:
        """Gate candidate audio so ward noise cannot steal the turn before the greeting.

        GPT-Live: use duplex mute_input (feed silence) — detaching RoomIO audio via
        set_audio_enabled(False) can prevent the model from starting speech at all
        (logs: \"the model did not start speaking when asked\" → ~10s silence).
        Cascade: disable RoomIO input so VAD/STT do not hold the floor.
        """
        if self._gpt_live:
            duplex = getattr(self, "duplex_session", None)
            if duplex is not None:
                try:
                    if enabled:
                        duplex.unmute_input()
                    else:
                        duplex.mute_input()
                    logger.info("gpt-live mic %s reason=%s", "on" if enabled else "off", reason)
                    return
                except Exception:  # noqa: BLE001
                    logger.exception("gpt-live mic toggle failed reason=%s", reason)
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return
        try:
            inp = getattr(session, "input", None)
            if inp is None:
                return
            if bool(getattr(inp, "audio_enabled", True)) == enabled:
                return
            inp.set_audio_enabled(enabled)
            logger.info("candidate mic %s reason=%s", "on" if enabled else "off", reason)
        except Exception:  # noqa: BLE001
            logger.exception("candidate mic toggle failed reason=%s", reason)

    def _gate_opening_input(self) -> None:
        """Mute + clear any in-flight user turn so opening speech starts immediately.

        The candidate's published microphone stays in the room recording. This only
        stops the agent from treating that audio as a turn until the greeting is done.
        """
        if self._listening_armed:
            return
        self._set_candidate_mic(False, reason="opening_guard")
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return
        try:
            clear = getattr(session, "clear_user_turn", None)
            if callable(clear):
                clear()
                logger.info("cleared pending user turn before opening")
        except Exception:  # noqa: BLE001
            logger.debug("clear_user_turn before opening failed", exc_info=True)

    def note_false_interruption(self, *, resumed: bool) -> None:
        """Agent was paused by noise/cough, then resumed — do not treat that audio as an answer."""
        self._interrupted = False
        self.director._cancel_early()
        self.director._finals = []
        if resumed:
            discard_s = float(get_settings().false_interrupt_discard_seconds or 0.0)
            self._discard_user_until = asyncio.get_running_loop().time() + max(0.0, discard_s)
            logger.info("false interruption resumed; discarding user audio for %.2fs", discard_s)

    async def _await_playout(self, handle: Any) -> None:
        """Wait until a SpeechHandle finishes playing (say / generate_reply return handles, not coroutines)."""
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

    async def _gpt_live_wait_quiet(self, *, min_quiet_s: float = 1.2, timeout_s: float = 14.0) -> None:
        """GPT-Live splits one directive into several spoken beats; wait until speech has truly stopped.

        Pushing append_instructions / arming listening after the first beat was cutting the opening
        mid-question (logs: greeting → focus_lock → leftover 'तो' / 'Umm आप किस city').
        """
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            await asyncio.sleep(min_quiet_s)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            await asyncio.sleep(min_quiet_s)
            return
        deadline = loop.time() + timeout_s
        quiet_start: float | None = None
        while loop.time() < deadline:
            state = getattr(session, "agent_state", None)
            if state in ("speaking", "thinking"):
                quiet_start = None
            else:
                if quiet_start is None:
                    quiet_start = loop.time()
                elif loop.time() - quiet_start >= min_quiet_s:
                    logger.info("GPT-Live quiet after opening/state=%s", state)
                    return
            await asyncio.sleep(0.15)
        logger.info("GPT-Live quiet wait timed out after %.1fs", timeout_s)

    async def _arm_listening(self, *, reason: str) -> None:
        if self._listening_armed:
            return
        settle = float(get_settings().opening_settle_seconds or 0.0)
        if settle > 0:
            await asyncio.sleep(settle)
        # Drop whatever the room did during the greeting so it cannot become the first answer.
        self._floor.note_agent_busy()
        session: AgentSession | None = self.session_ref.get("session")
        if session is not None:
            try:
                clear = getattr(session, "clear_user_turn", None)
                if callable(clear):
                    clear()
            except Exception:  # noqa: BLE001
                logger.debug("clear_user_turn before arm failed", exc_info=True)
        self._listening_armed = True
        # Opening used a mic mute; reopen only after the greeting so listening can start.
        self._set_candidate_mic(True, reason=reason)
        # Ignore echo / residual opening audio so we do not treat it as the candidate answering.
        # Keep this short so a real answer is not dropped; answer debounce stays in _gpt_live_settle_s.
        if self._gpt_live:
            try:
                self._gpt_live_ignore_until = asyncio.get_running_loop().time() + max(1.2, settle + 0.8)
            except RuntimeError:
                pass
        logger.info("listening armed reason=%s settle=%.2fs", reason, settle)
        self.spawn(
            self.backend.post_event(
                self.plan.interview_id,
                "audio.listening_armed",
                {"reason": reason, "settle_s": settle},
            )
        )

    async def _hold_opening_floor(self) -> None:
        """While the greeting plays, keep clearing candidate turns so noise cannot take the floor."""
        while not self._listening_armed and not self.flow.done:
            await asyncio.sleep(0.25)
            if self._listening_armed or self.flow.done:
                return
            self._gate_opening_input()

    async def _watch_listen_floor(self) -> None:
        """After the greeting, close the turn when words stop. Noise alone does not keep it open."""
        if self._floor_watch_started:
            return
        self._floor_watch_started = True
        from interview.turns import detector_covers

        settings = get_settings()
        while not self.flow.done:
            await asyncio.sleep(0.2)
            if not self._listening_armed or self._gpt_live:
                continue
            session: AgentSession | None = self.session_ref.get("session")
            if session is None:
                continue
            if getattr(session, "agent_state", None) in ("speaking", "thinking"):
                self._floor.note_agent_busy()
                continue
            try:
                now = asyncio.get_running_loop().time()
            except RuntimeError:
                return
            lang = self.flow.state.language or ""
            covered = bool(settings.turn_detector_enabled) and detector_covers(lang)
            min_hold, max_hold = self.flow.endpointing_hold_s(covered=covered, settings=settings)
            speaking = getattr(session, "user_state", None) == "speaking"
            decision = self._floor.decide(
                now,
                user_speaking=speaking,
                min_hold=min_hold,
                max_hold=max_hold,
            )
            if decision == "wait":
                continue
            self._floor.take()
            if decision == "release":
                logger.info("listen release — background noise, no words")
                try:
                    session.clear_user_turn()
                except Exception:  # noqa: BLE001
                    logger.debug("clear after noise release failed", exc_info=True)
                self.spawn(
                    self.backend.post_event(
                        self.plan.interview_id,
                        "audio.noise_released",
                        {},
                    )
                )
                continue
            logger.info("candidate words stopped; closing the turn")
            try:
                session.commit_user_turn(transcript_timeout=1.0, stt_flush_duration=0.4)
            except Exception:  # noqa: BLE001
                logger.exception("commit after words stopped failed")

    async def tts_node(self, text, model_settings):  # noqa: ANN001
        tts = self.session.tts
        is_el = self._tts_provider == "elevenlabs" or (
            _elevenlabs_plugin is not None and isinstance(tts, _elevenlabs_plugin.TTS)
        )
        if is_el:
            self._disfluency.use_pause_tags = False
        else:
            self._disfluency.use_pause_tags = bool(getattr(getattr(tts, "_opts", None), "use_markup", False))
        skip_first, self._suppress_lead = self._suppress_lead, False
        opening, self._greeting_pending = self._greeting_pending, False

        # Collect LLM raw + spoken for transcript split.
        raw_chunks: list[str] = []
        spoken_chunks: list[str] = []

        async def _tee_raw() -> Any:
            async for chunk in text:
                raw_chunks.append(chunk)
                yield chunk

        use_engine = is_el and self._expressiveness_mode == "engine"
        if use_engine:
            shaped = self._engine.apply(
                _tee_raw(),
                language=self.flow.state.language,
                tone=self._current_tone,
                opening=opening,
                skip_first=skip_first,
                empathy=self._empathy_hint,
            )
        else:
            shaped = self._disfluency.apply(
                _tee_raw(),
                self.flow.state.language,
                skip_first=skip_first,
                opening=opening,
            )

        async def _collect_spoken() -> Any:
            async for chunk in shaped:
                spoken_chunks.append(chunk)
                yield chunk

        try:
            async for frame in Agent.default.tts_node(self, _collect_spoken(), model_settings):
                yield frame
        except Exception:
            # Phase 7: optional Chirp fallback — never on /elevenlabs-interviewer (locked EL).
            settings = get_settings()
            if getattr(self, "_tts_locked_el", False):
                logger.exception("ElevenLabs TTS failed; EL interview mode is locked (no Chirp fallback)")
                raise
            if is_el and settings.tts_fallback_on_error == "google":
                logger.exception("ElevenLabs TTS failed; falling back to Google Chirp")
                try:
                    from providers import build_tts

                    self.session.tts = build_tts(self.flow.state.language, settings, provider="google")
                    self._tts_provider = "google"
                    async for frame in Agent.default.tts_node(self, _iter_joined(spoken_chunks or raw_chunks), model_settings):
                        yield frame
                    return
                except Exception:  # noqa: BLE001
                    logger.exception("Chirp fallback also failed")
            raise
        finally:
            self._last_llm_text = "".join(raw_chunks)
            self._last_spoken = "".join(spoken_chunks) if spoken_chunks else self._last_llm_text
            if use_engine:
                self._last_spoken = self._engine.spoken_for_transcript(self._last_spoken)

    async def switch_language(self, language_code: str) -> str:
        """Switch the whole interview language only when the candidate clearly asks to change language.

        Do not call this because their answer contains English words. language_code is en-IN, hi-IN, te-IN, ta-IN, kn-IN, ml-IN, bn-IN, mr-IN, gu-IN, pa-IN, or od-IN.
        """
        profile = get_profile(language_code)
        current = self.flow.state.language
        if profile.code == current:
            return f"Already on {profile.label}. Keep this same voice."
        last_user = ""
        for turn in reversed(self.director.recent):
            if turn.get("role") == "user":
                last_user = turn.get("text") or ""
                break
        spoken = detect_script_language(last_user)
        # A Hindi sentence with a few English words is still Hindi. Do not change the voice.
        if spoken and spoken != profile.code:
            return (
                f"Stay on {current}. Their answer is still that language. "
                "Do not switch voice for English words."
            )
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return f"Unable to switch; stay on {current}"

        settings = get_settings()
        try:
            _switch_stt_language(getattr(session, "stt", None), profile.code, settings)
            _switch_tts_language(getattr(session, "tts", None), profile.code, settings)

            self.flow.state.language = profile.code
            if (fillers := self.session_ref.get("fillers")) is not None:
                fillers.prepare(profile.code)
            apply_language_profile(session, profile.code, settings)
            await self.backend.update_controller(
                self.plan.interview_id,
                {"language": profile.code},
            )
            await self.backend.post_event(
                self.plan.interview_id,
                "language.switched",
                {"language": profile.code},
            )
            return f"Switched to {profile.label} ({profile.code}). Continue in that language."
        except Exception as err:  # noqa: BLE001
            logger.exception("switch_language failed")
            return f"Language switch failed: {err}"

    # ----------------------------------------------------------------------------------------------- plumbing

    def spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _record_user_move(self, move: Move, utterance: str, events: list[tuple[str, dict[str, Any]]]) -> None:
        """Store the candidate line with the move it caused, so a reviewer can see both."""
        self.spawn(
            self.backend.post_transcript(
                self.plan.interview_id,
                role="user",
                text=utterance,
                turn_index=self._turn_index,
                move=move.kind,
            )
        )
        self.spawn(
            self._persist(
                [
                    (
                        "flow.move",
                        {
                            "kind": move.kind,
                            "stage": self.flow.state.stage,
                            "utterance": utterance[:400],
                        },
                    ),
                    *events,
                    *move.events,
                ]
            )
        )

    async def _persist(self, events: list[tuple[str, dict[str, Any]]] | None = None) -> None:
        """Save flow state and events; ordered, off the critical path, never raises."""
        async with self._persist_lock:
            try:
                for event_type, data in events or []:
                    await self.backend.post_event(self.plan.interview_id, event_type, data)
                await self.backend.update_controller(
                    self.plan.interview_id,
                    {
                        "flow": self.flow.state.to_dict(),
                        "language": self.flow.state.language,
                        "completed": self.flow.done,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception("persisting flow state failed")

    def _finish_if_needed(self, move: Move) -> None:
        if not move.completed or self._closing:
            return
        self._closing = True
        self.spawn(self._complete_and_close(move))

    async def _complete_and_close(self, move: Move) -> None:
        try:
            await self.backend.complete(
                self.plan.interview_id,
                {"reason": move.kind, "outcome": self.flow.state.outcome, "stage": self.flow.state.stage},
            )
        except Exception:  # noqa: BLE001
            logger.exception("complete call failed")
        if not move.end_session:
            return
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return
        # Let the goodbye be spoken: wait until the agent has started and then finished talking.
        spoke = False
        for _ in range(150):
            await asyncio.sleep(0.3)
            state = getattr(session, "agent_state", None)
            if state in ("thinking", "speaking"):
                spoke = True
            elif spoke and state in ("listening", "idle"):
                break
        await asyncio.sleep(0.8)
        try:
            session.shutdown(drain=True)
        except Exception:  # noqa: BLE001
            logger.exception("session shutdown failed")
        if (job_ctx := self.session_ref.get("job_ctx")) is not None:
            job_ctx.shutdown(reason="interview_complete")

    async def speak_move(self, move: Move) -> None:
        """Say something unprompted (resume, silence nudges, goodbyes)."""
        self.spawn(self._persist(move.events))
        self._finish_if_needed(move)
        # First silence level is intentional quiet — do not invent a "no hurry" line.
        if move.kind == "silence_hold" or not (move.directive or "").strip():
            return
        try:
            self._current_tone = move.tone or tone_for_kind(move.kind)
            self._empathy_hint = self._current_tone in ("gentle", "reassuring")
            # Opening must never wait on / yield to ambient mic noise.
            block = move.kind == "opening" and bool(get_settings().opening_block_interruptions)
            if move.kind == "opening":
                self._gate_opening_input()
            if self._gpt_live:
                # GPT-Live has no half-cascade: session.say() needs a separate TTS. Use commentary.
                reply_kwargs: dict[str, Any] = {
                    "instructions": _gpt_live_commentary(move, self.flow.state.language),
                }
                # Still request no barge-in; mic is muted until listening is armed.
                if move.kind == "opening":
                    reply_kwargs["allow_interruptions"] = False
                reply_handle = self.session.generate_reply(**reply_kwargs)
                await self._await_playout(reply_handle)
                if move.kind == "opening":
                    # Wait out multi-beat openings. 0.55s was too short: quiet gap between
                    # greeting beats → focus_lock / retry re-asked the same question.
                    await self._gpt_live_wait_quiet(min_quiet_s=1.6, timeout_s=14.0)
                    self._gpt_live_push_listen_hold(reason="opening_complete")
                    await self._arm_listening(reason="opening_complete")
                else:
                    await self._gpt_live_wait_quiet(min_quiet_s=1.2, timeout_s=12.0)
                    self._gpt_live_push_listen_hold(reason=move.kind)
                return
            if move.kind == "opening":
                # Speak the greeting word immediately; start the LLM while seed plays.
                seed = opening_seed(
                    self.flow.state.language,
                    elevenlabs=self._tts_provider == "elevenlabs",
                    engine=self._expressiveness_mode == "engine",
                )
                seed_handle = self.session.say(seed, allow_interruptions=not block)
                directive_text = (
                    f"CONTROLLER DIRECTIVE: {move.directive}\n"
                    f"{native_script_reminder(self.flow.state.language)}"
                )
                reply_handle = self.session.generate_reply(
                    instructions=directive_text,
                    allow_interruptions=not block,
                )
                await self._await_playout(seed_handle)
                await self._await_playout(reply_handle)
                # Playout already finished — do NOT poll agent_state (that used to hang ~45s).
                await self._arm_listening(reason="opening_complete")
            else:
                directive_text = f"CONTROLLER DIRECTIVE: {move.directive}"
                reply_handle = self.session.generate_reply(instructions=directive_text)
                await self._await_playout(reply_handle)
        except Exception:  # noqa: BLE001
            logger.exception("generate_reply failed for %s", move.kind)
            if move.kind == "opening" and not self._listening_armed:
                # Fail open so a TTS glitch does not mute the candidate forever.
                await self._arm_listening(reason="opening_error_fail_open")

    def _wire_gpt_live_delegation(self) -> None:
        if self._delegation_wired or not self._gpt_live:
            return
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            logger.warning("GPT-Live duplex_session missing; client delegation not wired yet")
            return
        duplex.on("delegation_created", self._on_gpt_live_delegation)
        # Capture finals before speech buffer is cleared (pending_transcript often arrives empty).
        try:
            duplex.on("input_audio_transcription_completed", self._on_gpt_live_user_transcript)
        except Exception:  # noqa: BLE001
            logger.debug("GPT-Live transcript hook not available", exc_info=True)
        self._delegation_wired = True
        logger.info("GPT-Live client delegation wired")

    def _on_gpt_live_delegation(self, delegation: Any) -> None:
        self.spawn(self._handle_gpt_live_delegation(delegation))

    def _on_gpt_live_user_transcript(self, event: Any) -> None:
        """Streaming partials → coalesce + reset silence timer. Commit only after speech stops."""
        if not self._listening_armed or self._gpt_live_driving:
            return
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0
        if now < self._gpt_live_ignore_until:
            return
        raw = getattr(event, "transcript", None) or ""
        text = sanitize_candidate_text(str(raw)).strip()
        if not text or text in {"\ufffd", "…", "..."} or set(text) <= {"\ufffd", " ", ".", "…"}:
            return
        # Noise must not reset the end-of-turn timer or get glued onto the answer.
        if not is_candidate_speech(text):
            return
        before = (self._gpt_live_last_user or "").strip()
        joined = self._gpt_live_coalesce_transcript(text, now=now)
        if joined == before:
            return
        logger.info("GPT-Live user transcript stashed chars=%d text=%s", len(joined), joined[:80])
        # Always re-arm debounce on every scrap — do not commit while they are still talking.
        self._gpt_live_schedule_drive(source="transcript")

    def _gpt_live_coalesce_transcript(self, text: str, *, now: float) -> str:
        """Merge streaming scraps / phone chunks spoken as separate STT items."""
        prev = (self._gpt_live_last_user or "").strip()
        gap = now - self._gpt_live_last_user_at if self._gpt_live_last_user_at else 99.0
        if prev and gap < 3.0:
            if text == prev:
                joined = prev
            elif text.startswith(prev) or prev in text:
                joined = text if len(text) >= len(prev) else prev
            elif prev.startswith(text):
                joined = prev  # older longer revision
            else:
                # New chunk in the same answer (e.g. phone digit groups).
                joined = f"{prev} {text}".strip()
        else:
            joined = text
        self._gpt_live_last_user = joined
        self._gpt_live_last_user_at = now
        if not self._gpt_live_user_buf or self._gpt_live_user_buf[-1] != joined:
            self._gpt_live_user_buf.append(joined)
        return joined

    def _gpt_live_ready_enough(self, text: str) -> bool:
        """Delegate to Flow so readiness matches the question currently in focus."""
        return self.flow.utterance_ready_for_focus(text)

    def _gpt_live_settle_s(self) -> float:
        """Longer silence for phone / multi-fact answers so we do not cut them mid-speech."""
        kinds = self.flow.short_answer_kinds()
        if kinds and all(k == "phone" for k in kinds):
            return 1.7
        if self.flow.patient_answer_focus():
            return 2.0
        ftype = (self.flow.state.focus or {}).get("type") or ""
        if ftype in ("clinical", "experience_dive", "experience_probe"):
            return 1.5
        return self._gpt_live_drive_settle_s

    def _retune_endpointing(self) -> None:
        """Give height/weight and work-history answers more silence before the turn closes."""
        if self._gpt_live:
            return
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return
        settings = get_settings()
        from interview.turns import detector_covers

        lang = self.flow.state.language or ""
        covered = bool(settings.turn_detector_enabled) and detector_covers(lang)
        min_delay, max_delay = self.flow.endpointing_hold_s(covered=covered, settings=settings)
        try:
            session.update_options(endpointing_opts={"min_delay": min_delay, "max_delay": max_delay})
        except Exception:  # noqa: BLE001
            logger.debug("endpointing retune failed", exc_info=True)

    def _gpt_live_user_from_chat(self) -> str:
        """Latest user turn already in chat_ctx."""
        try:
            items = getattr(self.chat_ctx, "items", None) or []
        except Exception:  # noqa: BLE001
            return ""
        for item in reversed(list(items)):
            if getattr(item, "role", None) != "user":
                continue
            raw = getattr(item, "text_content", None) or getattr(item, "content", "") or ""
            if isinstance(raw, list):
                raw = " ".join(str(x) for x in raw)
            text = sanitize_candidate_text(str(raw)).strip()
            if text:
                return text
        return ""

    def _gpt_live_resolve_utterance(self, pending: str = "") -> str:
        """Best available candidate text: pending → stash → chat_ctx."""
        pending = sanitize_candidate_text(pending or "").strip()
        if pending:
            return pending
        stashed = (self._gpt_live_last_user or "").strip()
        if stashed:
            return stashed
        return self._gpt_live_user_from_chat()

    def _gpt_live_is_duplicate(self, text: str) -> bool:
        """True if this is the same answer we already committed (or a shorter echo of it)."""
        text = (text or "").strip()
        prev = (self._gpt_live_last_committed or "").strip()
        if not text or not prev:
            return False
        if text == prev:
            return True
        if text in prev or prev in text:
            return True
        return False

    def _gpt_live_hold_voice(self) -> None:
        """Stop the model inventing the next question while Director runs (once per answer)."""
        if self._gpt_live_held_voice:
            return
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            return
        try:
            duplex.append_instructions(
                "The candidate is answering. Brief acknowledgement only if needed. "
                "Do NOT ask any new interview question, list options, or invent a topic. "
                "Wait for the next CONTROLLER DIRECTIVE commentary."
            )
            self._gpt_live_held_voice = True
        except Exception:  # noqa: BLE001
            logger.debug("GPT-Live hold_voice append failed", exc_info=True)

    def _gpt_live_push_focus_lock(self) -> None:
        """Standing rules so the voice model cannot freestyle the next interview topic."""
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            return
        summary = self.flow.focus_lock_summary()
        try:
            duplex.append_instructions(f"{_GPT_LIVE_FOCUS_LOCK_INSTRUCTIONS} Current focus: {summary}")
            duplex.append_thinking(f"Interview focus lock: {summary}")
            logger.info("GPT-Live focus_lock %s", summary[:160])
        except Exception:  # noqa: BLE001
            logger.exception("GPT-Live focus lock append failed")

    def _gpt_live_push_listen_hold(self, *, reason: str) -> None:
        """After we asked something: lock focus silently and forbid repeating the question.

        Thinking-only — append_instructions/commentary right after a question can make
        GPT-Live speak again (double-ask within ~0.5s).
        """
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            return
        summary = self.flow.focus_lock_summary()
        try:
            duplex.append_thinking(
                f"{_GPT_LIVE_FOCUS_LOCK_INSTRUCTIONS} {_GPT_LIVE_LISTEN_HOLD} "
                f"Current focus: {summary} (reason={reason})"
            )
            logger.info("GPT-Live listen_hold reason=%s focus=%s", reason, summary[:120])
        except Exception:  # noqa: BLE001
            logger.exception("GPT-Live listen_hold failed")

    def _gpt_live_append(self, commentary: str, *, delegation_id: str | None = None) -> None:
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            return
        try:
            duplex.append_commentary(commentary, delegation_id=delegation_id)
        except Exception:  # noqa: BLE001
            logger.exception("append_commentary failed")

    def _gpt_live_schedule_drive(self, *, source: str) -> None:
        """Debounce until silence after last scrap, then run Director (cascade-equivalent)."""
        self._gpt_live_hold_voice()
        self._gpt_live_drive_gen += 1
        gen = self._gpt_live_drive_gen
        settle = self._gpt_live_settle_s()

        async def _drive() -> None:
            await asyncio.sleep(settle)
            if gen != self._gpt_live_drive_gen:
                return
            try:
                now = asyncio.get_running_loop().time()
            except RuntimeError:
                now = 0.0
            if now < self._gpt_live_ignore_until:
                return
            text = self._gpt_live_resolve_utterance()
            if not text or not self._gpt_live_ready_enough(text):
                logger.info(
                    "GPT-Live drive skip source=%s settle=%.1f ready=%s text=%s",
                    source,
                    settle,
                    bool(text and self._gpt_live_ready_enough(text)),
                    (text or "")[:80],
                )
                return
            await self._gpt_live_drive_turn(text, source=source)

        self.spawn(_drive())

    async def _gpt_live_drive_turn(self, text: str, *, source: str) -> None:
        """Cascade-equivalent: user text → Director → CONTROLLER DIRECTIVE commentary."""
        text = (text or "").strip()
        if not text or not self._listening_armed or self.flow.done:
            return
        if self._gpt_live_driving:
            logger.info("GPT-Live drive busy; skip source=%s", source)
            return
        if self._gpt_live_is_duplicate(text):
            logger.info("GPT-Live drive duplicate skip chars=%d source=%s", len(text), source)
            return

        self._gpt_live_driving = True
        dep_id = self._gpt_live_open_dep_id
        self._gpt_live_open_dep_id = None
        try:
            await self._gpt_live_commit_joined(text, delegation_id=dep_id, ack_first=True, source=source)
        finally:
            self._gpt_live_driving = False
            self._gpt_live_held_voice = False

    async def _gpt_live_commit_joined(
        self,
        joined: str,
        *,
        delegation_id: str | None,
        ack_first: bool = True,
        source: str = "commit",
    ) -> None:
        """Ack (optional) → Director → CONTROLLER DIRECTIVE. Same Flow as ElevenLabs cascade."""
        duplex = getattr(self, "duplex_session", None)
        settings = get_settings()
        self._gpt_live_user_buf = []
        self._gpt_live_buf_started = 0.0
        self._gpt_live_drive_gen += 1  # cancel pending debounce

        if not joined.strip() or not is_candidate_speech(joined):
            self._gpt_live_append(
                "No clear candidate speech yet. Keep listening — do not ask a new interview question.",
                delegation_id=delegation_id,
            )
            return

        if self._gpt_live_is_duplicate(joined):
            logger.info("GPT-Live skip duplicate commit chars=%d source=%s", len(joined), source)
            self._gpt_live_append(
                "Already noted. Continue with the current CONTROLLER focus only — "
                "do not invent a new question.",
                delegation_id=delegation_id,
            )
            return

        # Reserve this utterance so concurrent transcript/delegation cannot double-apply Flow.
        self._gpt_live_last_committed = joined.strip()
        self._gpt_live_user_buf = []
        self._gpt_live_last_user = ""

        # Phase 1: speakable progress immediately so Director latency is not dead air.
        if ack_first:
            self._gpt_live_append(_GPT_LIVE_ACK_COMMENTARY, delegation_id=delegation_id)
            logger.info(
                "GPT-Live ack_sent source=%s dep=%s chars=%d focus=%s text=%s",
                source,
                delegation_id,
                len(joined),
                (self.flow.state.focus or {}).get("type"),
                joined[:80],
            )

        self._turn_index += 1
        if self.latency is not None:
            self.latency.on_hook_start(self._turn_index)

        detected = detect_script_language(joined)
        events: list[tuple[str, dict[str, Any]]] = []
        if detected and detected != self.flow.state.language:
            events.append(("language.detected", {"from": self.flow.state.language, "to": detected}))

        self.director.on_final_transcript(joined)

        elapsed_min = (datetime.now(timezone.utc) - self._started_at).total_seconds() / 60.0
        t0 = datetime.now(timezone.utc)
        if elapsed_min >= settings.v2_max_minutes and not self.flow.done:
            move = self.flow.force_complete("time")
        else:
            move = await self.director.decide(joined)
        self._retune_endpointing()
        director_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
        if self.latency is not None:
            self.latency.on_director_done(director_ms / 1000.0)

        self._current_tone = move.tone or tone_for_kind(move.kind)
        self._empathy_hint = self._current_tone in ("gentle", "reassuring")
        self._previous_empathy = self._empathy_hint
        self._interrupted = False
        self.director.note_user(joined)

        self._record_user_move(move, joined, events)
        logger.info(
            "gpt_live move=%s stage=%s director_ms=%.0f source=%s joined_chars=%d text=%s",
            move.kind,
            self.flow.state.stage,
            director_ms,
            source,
            len(joined),
            joined[:80],
        )

        # Phase 2: one CONTROLLER DIRECTIVE only (no generate_reply double-speak).
        self._gpt_live_append(_gpt_live_commentary(move, self.flow.state.language), delegation_id=delegation_id)
        # Ignore echo while the model speaks; listen-hold after quiet (not immediately —
        # immediate append_instructions was causing a second spoken ask).
        try:
            self._gpt_live_ignore_until = asyncio.get_running_loop().time() + 3.0
        except RuntimeError:
            self._gpt_live_ignore_until = 0.0

        async def _hold_after_speak() -> None:
            await self._gpt_live_wait_quiet(min_quiet_s=1.2, timeout_s=12.0)
            self._gpt_live_push_listen_hold(reason=f"after_{move.kind}")
            try:
                # Brief echo window only; answer debounce stays at _gpt_live_settle_s.
                self._gpt_live_ignore_until = asyncio.get_running_loop().time() + 1.0
            except RuntimeError:
                pass

        self.spawn(_hold_after_speak())
        if self.latency is not None:
            self.latency.on_hook_end()
        self._finish_if_needed(move)

    async def _handle_gpt_live_delegation(self, delegation: Any) -> None:
        """Backup path only — Flow is driven from transcripts; answer open deps without freestyle."""
        duplex = getattr(self, "duplex_session", None)
        if duplex is None:
            return
        dep_id = getattr(delegation, "id", None)
        raw = getattr(delegation, "pending_transcript", None) or ""
        fragment = self._gpt_live_resolve_utterance(str(raw))
        logger.info(
            "GPT-Live delegation id=%s pending_chars=%d resolved_chars=%d focus=%s text=%s",
            dep_id,
            len(str(raw or "").strip()),
            len(fragment),
            (self.flow.state.focus or {}).get("type"),
            fragment[:100],
        )

        def _reply(commentary: str) -> None:
            try:
                duplex.append_commentary(commentary, delegation_id=dep_id)
            except Exception:  # noqa: BLE001
                logger.exception("append_commentary failed")

        if not self._listening_armed:
            _reply(
                "The candidate has not finished hearing the opening yet. "
                "Pause briefly and keep listening — do not ask a new interview question."
            )
            return

        # Already applied this answer via transcript-driven path.
        if fragment and self._gpt_live_is_duplicate(fragment):
            _reply(
                "Already noted by the interview controller. "
                "Follow the latest CONTROLLER DIRECTIVE only — do not invent a new question."
            )
            return

        if self._gpt_live_driving:
            self._gpt_live_open_dep_id = dep_id
            _reply(_GPT_LIVE_ACK_COMMENTARY)
            return

        if not fragment.strip():
            self._gpt_live_open_dep_id = dep_id
            _reply(
                "Brief acknowledgement only. Keep listening — do not ask a new interview question."
            )
            return

        if not self._gpt_live_ready_enough(fragment):
            self._gpt_live_open_dep_id = dep_id
            self._gpt_live_last_user = fragment.strip()
            _reply(_GPT_LIVE_ACK_COMMENTARY)
            self._gpt_live_schedule_drive(source="delegation_hold")
            return

        await self._gpt_live_drive_turn(fragment, source="delegation")

    async def _rehydrate(self) -> None:
        """After a restart, give the voice model the last few turns so it keeps its thread."""
        recent = self.plan.recent_transcript[-6:]
        if not recent:
            return
        try:
            ctx = self.chat_ctx.copy()
            for turn in recent:
                ctx.add_message(role=turn["role"], content=turn["text"])
            await self.update_chat_ctx(ctx)
        except Exception:  # noqa: BLE001
            logger.exception("could not restore chat context")

    # --------------------------------------------------------------------------------------------- lifecycle

    async def on_enter(self) -> None:
        if self._gpt_live:
            self._wire_gpt_live_delegation()
        resuming = self.flow.state.stage != "opening"
        if resuming:
            self._listening_armed = True
            self._set_candidate_mic(True, reason="resume")
            for turn in self.plan.recent_transcript:
                if turn["role"] == "assistant":
                    self.director.note_assistant(turn["text"])
                else:
                    self.director.note_user(turn["text"])
            await self._rehydrate()
        else:
            # Drop in-flight noise so it cannot delay the greeting. The published mic
            # stays in the room recording; this only stops the agent acting on it.
            self._gate_opening_input()
            self.spawn(self._hold_opening_floor())
        self.spawn(self._watch_listen_floor())
        move = self.flow.resume() if resuming else self.flow.opening()
        # Don't block first audio on analytics — speak immediately.
        self.spawn(
            self.backend.post_event(
                self.plan.interview_id,
                "interview.agent_entered",
                {
                    "resumed": resuming,
                    "stage": self.flow.state.stage,
                    "voice_provider": "gpt_live" if self._gpt_live else "cascade",
                    "opening_mic_gated": not resuming,
                },
            )
        )
        await self.speak_move(move)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # noqa: ANN001
        raw = getattr(new_message, "text_content", None) or getattr(new_message, "content", "") or ""
        if isinstance(raw, list):
            raw = " ".join(str(x) for x in raw)
        text = sanitize_candidate_text(str(raw))
        settings = get_settings()

        # GPT-Live: same Flow as cascade — drive Director from the user turn.
        # Do not wait for model delegation (it often freestyles without ever delegating).
        if self._gpt_live:
            if not self._listening_armed:
                logger.info("gpt_live discard pre-arm user audio (%d chars): %s", len(text), text[:80])
                self.spawn(
                    self.backend.post_event(
                        self.plan.interview_id,
                        "audio.preamble_discard",
                        {"text": text[:160], "chars": len(text), "source": "gpt_live_turn"},
                    )
                )
                raise StopResponse()
            now = asyncio.get_running_loop().time()
            if now < self._discard_user_until:
                verdict = classify_answer(text)
                if verdict in ("noise", "weak") or len(text.strip()) < 24:
                    logger.info(
                        "gpt_live discard post-false-interrupt verdict=%s (%d chars)",
                        verdict,
                        len(text),
                    )
                    self.spawn(
                        self.backend.post_event(
                            self.plan.interview_id,
                            "audio.false_interrupt_discard",
                            {"text": text[:160], "verdict": verdict, "source": "gpt_live_turn"},
                        )
                    )
                    self.director._cancel_early()
                    self.director._finals = []
                    raise StopResponse()
            if text.strip() and not is_candidate_speech(text):
                logger.info("gpt_live ignoring non-word audio (%d chars): %s", len(text), text[:80])
                raise StopResponse()
            if text.strip():
                try:
                    now = asyncio.get_running_loop().time()
                except RuntimeError:
                    now = 0.0
                if now < self._gpt_live_ignore_until:
                    raise StopResponse()
                before = (self._gpt_live_last_user or "").strip()
                joined = self._gpt_live_coalesce_transcript(text.strip(), now=now)
                if joined == before:
                    raise StopResponse()
                # Still debounce — turn_completed can fire on a mid-answer STT segment.
                self._gpt_live_schedule_drive(source="user_turn")
                logger.info(
                    "GPT-Live user_turn scheduled chars=%d ready=%s text=%s",
                    len(joined),
                    self._gpt_live_ready_enough(joined),
                    joined[:80],
                )
            raise StopResponse()

        # Ambient noise during / right after greeting: discard — do not advance Flow.
        if not self._listening_armed:
            logger.info("discarding pre-arm user audio (%d chars): %s", len(text), text[:80])
            self.spawn(
                self.backend.post_event(
                    self.plan.interview_id,
                    "audio.preamble_discard",
                    {"text": text[:160], "chars": len(text)},
                )
            )
            raise StopResponse()

        # A cough, a hum, "uh" — not an answer. Stay on the question and do not ask them to repeat.
        if not is_candidate_speech(text):
            logger.info("ignoring non-word audio (%d chars): %s", len(text), text[:80])
            self._floor.note_agent_busy()
            self.spawn(
                self.backend.post_event(
                    self.plan.interview_id,
                    "audio.noise_ignored",
                    {"text": text[:160], "chars": len(text)},
                )
            )
            raise StopResponse()

        # Mid-question ward noise that briefly paused TTS: interviewer already resumed — drop junk.
        now = asyncio.get_running_loop().time()
        if now < self._discard_user_until:
            verdict = classify_answer(text)
            if verdict in ("noise", "weak") or len(text.strip()) < 24:
                logger.info(
                    "discarding post-false-interrupt audio verdict=%s (%d chars): %s",
                    verdict,
                    len(text),
                    text[:80],
                )
                self.spawn(
                    self.backend.post_event(
                        self.plan.interview_id,
                        "audio.false_interrupt_discard",
                        {"text": text[:160], "verdict": verdict},
                    )
                )
                self.director._cancel_early()
                self.director._finals = []
                raise StopResponse()

        self._turn_index += 1
        if self.latency is not None:
            self.latency.on_hook_start(self._turn_index)

        detected = detect_script_language(text)
        events: list[tuple[str, dict[str, Any]]] = []
        if detected and detected != self.flow.state.language:
            events.append(("language.detected", {"from": self.flow.state.language, "to": detected}))

        # Ack filler BEFORE Director — bucket from STT heuristics / prior turn, never Director sentiment.
        filler_note = ""
        fillers: FillerPlayer | None = self.session_ref.get("fillers")
        bucket = filler_bucket_from_text(text, previous_empathy=self._previous_empathy)
        if fillers is not None and not self.flow.done and classify_answer(text) == "substantive":
            picked = fillers.pick(self.flow.state.language, text, bucket=bucket)
            if picked is not None:
                filler_text, frames = picked
                if self.latency is not None:
                    self.latency.on_filler_start()
                self.session.say(filler_text, audio=frames_iter(frames), add_to_chat_ctx=False)
                self._suppress_lead = True
                filler_note = (
                    f'\nYou have already said "{filler_text}" out loud as your reaction. Do not open with another '
                    "acknowledgement; continue straight on from it."
                )

        elapsed_min = (datetime.now(timezone.utc) - self._started_at).total_seconds() / 60.0
        t0 = datetime.now(timezone.utc)
        if elapsed_min >= settings.v2_max_minutes and not self.flow.done:
            move = self.flow.force_complete("time")
        else:
            move = await self.director.decide(text)
        self._retune_endpointing()
        if self.latency is not None:
            self.latency.on_director_done((datetime.now(timezone.utc) - t0).total_seconds())
        self._current_tone = move.tone or tone_for_kind(move.kind)
        self._empathy_hint = bucket == "empathetic" or self._current_tone in ("gentle", "reassuring")
        self._previous_empathy = self._empathy_hint
        self._interrupted = False
        self.director.note_user(text)

        self._record_user_move(move, text, events)

        logger.info("move=%s stage=%s", move.kind, self.flow.state.stage)
        if self._interrupted and move.kind not in ("repeat", "rephrase", "ask_repeat", "reask_invalid"):
            move.directive += (
                " They answered while you were still speaking. Acknowledge what they just said and ask only "
                "what this directive says."
            )
        if move.verbatim:
            # The mobile step is one fixed sentence. The dialogue model was adding the next
            # question ("what is your age?") in the same breath as the number read-back.
            self.director.note_assistant(move.verbatim)
            self.session.say(move.verbatim, allow_interruptions=True)
            if self.latency is not None:
                self.latency.on_hook_end()
            self._finish_if_needed(move)
            raise StopResponse()
        turn_ctx.add_message(
            role="system",
            content=(
                f"CONTROLLER DIRECTIVE: {move.directive}\n"
                f"{native_script_reminder(self.flow.state.language)}{filler_note}"
            ),
        )
        if self.latency is not None:
            self.latency.on_hook_end()
        self._finish_if_needed(move)


class CascadeInterviewAgent(InterviewAgent):
    """Cascade STT/LLM/TTS path — exposes switch_language as a LiveKit tool.

    GPT-Live client delegation has no tool channel, so the base InterviewAgent
    must stay tool-free; only this subclass registers the function tool.
    """

    @function_tool()
    async def switch_language(self, language_code: str) -> str:
        """Switch interview language mid-call. language_code is en-IN, hi-IN, te-IN, ta-IN, kn-IN, ml-IN, bn-IN, mr-IN, gu-IN, pa-IN, or od-IN."""
        return await super().switch_language(language_code)


async def _run_gpt_live_session(
    ctx: JobContext,
    *,
    settings: Any,
    backend: BackendClient,
    interview_id: str,
    plan: InterviewPlan,
    flow: InterviewFlow,
    director: Director,
    language: str,
    wants_avatar: bool,
) -> None:
    """Full-duplex GPT-Live path: model owns STT+voice; Director/Flow via client delegation."""
    from livekit.plugins.openai.realtime import GPTLiveModel

    try:
        noise = build_noise_cancellation(settings)
    except SessionRefused:
        await _abort_refused_session(ctx, backend)
        return
    gpt_voice = settings.gpt_live_voice_for(language)
    gpt_voice_label = (
        f"custom:{gpt_voice.get('id', '?')}" if isinstance(gpt_voice, dict) else str(gpt_voice)
    )
    logger.info(
        "GPT-Live session model=%s voice=%s language=%s noise=%s",
        settings.gpt_live_model,
        gpt_voice_label,
        language,
        "on" if noise is not None else "off",
    )

    # Do NOT attach Silero VAD here. GPT-Live owns server-side turn detection; pairing it with
    # client VAD was chopping answers into ~0.5s scraps (last_final_transcript_time=null,
    # source=vad) so Director kept returning ask_repeat — felt like "not hearing".
    # Model-controlled barge-in still works; local playback stop is secondary on this path.
    llm = GPTLiveModel(
        model=settings.gpt_live_model,
        voice=gpt_voice,
        delegation="client",
        api_key=settings.openai_api_key,
    )

    session_ref: dict[str, Any] = {"job_ctx": ctx}
    agent = InterviewAgent(
        plan=plan,
        flow=flow,
        director=director,
        backend=backend,
        session_ref=session_ref,
        gpt_live=True,
        tts_provider=f"gpt_live:{gpt_voice_label}",
    )
    director._is_listening_armed = agent.is_listening_armed

    try:
        session = AgentSession(
            llm=llm,
            user_away_timeout=float(settings.silence_nudge_seconds),
            discard_audio_if_uninterruptible=True,
            # Default 3s AEC warmup after first remote audio delays barge-in setup; keep short.
            aec_warmup_duration=0.5,
        )
    except TypeError:
        try:
            session = AgentSession(
                llm=llm,
                user_away_timeout=float(settings.silence_nudge_seconds),
                discard_audio_if_uninterruptible=True,
            )
        except TypeError:
            session = AgentSession(
                llm=llm,
                user_away_timeout=float(settings.silence_nudge_seconds),
            )
    session_ref["session"] = session

    watchdog = TurnWatchdog(
        session=session,
        backend=backend,
        interview_id=interview_id,
        settings=settings,
        is_listening_armed=agent.is_listening_armed,
        get_language=lambda: agent.flow.state.language,
    )
    watchdog.attach()
    latency = LatencyTracker(
        backend=backend,
        interview_id=interview_id,
        enabled=bool(settings.voice_latency_log),
        spawn=agent.spawn,
    )
    agent.latency = latency
    latency.attach(session)

    agent.spawn(
        backend.post_event(
            interview_id,
            "voice.session_config",
            {
                "voice_provider": "gpt_live",
                "gpt_live_model": settings.gpt_live_model,
                "gpt_live_voice": gpt_voice_label,
                "gpt_live_language": language,
                "delegation": "client",
                "stt_provider": "gpt_live_builtin",
                "tts_provider": "gpt_live_builtin",
                "voice_latency_log": settings.voice_latency_log,
                # Cascade fillers / expressiveness intentionally off — model handles pacing.
                "voice_expressiveness": "gpt_live_native",
                "voice_early_filler": False,
                "thinking_filler": False,
            },
        )
    )

    @session.on("conversation_item_added")
    def _on_item(ev):  # noqa: ANN001
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        text = str(getattr(item, "text_content", None) or "").strip()
        if role == "assistant" and text:
            director.note_assistant(text)
            agent.spawn(
                backend.post_transcript(
                    interview_id,
                    role="assistant",
                    text=text,
                    interrupted=bool(agent._interrupted) or None,
                )
            )
            agent._interrupted = False

    @session.on("agent_false_interruption")
    def _on_false_int(ev):  # noqa: ANN001
        resumed = bool(getattr(ev, "resumed", False))
        agent.note_false_interruption(resumed=resumed)
        agent.spawn(
            backend.post_event(
                interview_id,
                "audio.false_interruption",
                {"resumed": resumed, "source": "gpt_live"},
            )
        )

    @session.on("user_state_changed")
    def _on_user_barge(ev):  # noqa: ANN001
        if getattr(ev, "new_state", None) != "speaking":
            return
        # Opening: the mic is recorded, but noise must not count as a barge-in.
        if not agent.is_listening_armed():
            return
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0
        agent._floor.note_speech_start(now)
        if getattr(session, "agent_state", None) == "speaking":
            agent._interrupted = True

    from livekit.agents.voice import room_io

    room_kwargs: dict[str, Any] = {"close_on_disconnect": False}
    # Do not replay mic audio from before the interviewer is ready. That buffer is room
    # noise, and feeding it in makes the first turn happen before the greeting.
    audio_kwargs: dict[str, Any] = {"pre_connect_audio": False}
    if noise is not None:
        audio_kwargs["noise_cancellation"] = noise
    room_kwargs["audio_input"] = room_io.AudioInputOptions(**audio_kwargs)
    start_kwargs: dict[str, Any] = {
        "agent": agent,
        "room": ctx.room,
        "room_options": room_io.RoomOptions(**room_kwargs),
    }

    SilenceMonitor(
        session=session, agent=agent, flow=flow, spacing_s=float(settings.silence_nudge_seconds)
    ).attach()
    ConnectionGuard(room=ctx.room, agent=agent, flow=flow, grace_s=float(settings.reconnect_grace_seconds)).attach()

    avatar_on = False
    if wants_avatar:
        try:
            avatar_on = await _start_tavus_avatar(session, ctx, settings)
        except Exception:  # noqa: BLE001
            logger.exception("Tavus avatar failed to start; continuing voice-only")
        if avatar_on:
            room_kwargs["audio_output"] = False
            start_kwargs["room_options"] = room_io.RoomOptions(**room_kwargs)

    await session.start(**start_kwargs)

    async def _shutdown() -> None:
        await watchdog.post_summary()
        try:
            summary = latency.summary()
            if settings.voice_latency_log and summary.get("turns"):
                await backend.post_event(interview_id, "turn.latency_summary", summary)
                logger.info("turn.latency_summary %s", summary)
        except Exception:  # noqa: BLE001
            logger.exception("latency summary failed")
        await backend.flush()
        await backend.aclose()

    ctx.add_shutdown_callback(_shutdown)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    settings = get_settings()
    interview_id = _parse_interview_id(ctx)
    if not interview_id:
        logger.error("No interviewId in job/room metadata; disconnecting")
        return

    backend = BackendClient()
    try:
        payload = await backend.fetch_plan(interview_id)
    except Exception:
        logger.exception("Failed to fetch plan for %s", interview_id)
        await backend.aclose()
        return

    plan = InterviewPlan.from_api(payload)
    state = ControllerState.from_api(payload)
    blueprint = Blueprint.from_api(plan.blueprint)
    job_meta = _merge_job_payload(ctx)
    wants_avatar = _wants_avatar(payload) or _wants_avatar(job_meta)
    tts_override = _tts_provider_override(payload, job_meta)
    voice_provider = _voice_provider_override(payload, job_meta)
    logger.info(
        "job %s avatar=%s tts=%s voice=%s (plan=%s meta=%s)",
        interview_id,
        wants_avatar,
        tts_override or settings.resolved_tts(),
        voice_provider or "cascade",
        payload.get("avatar"),
        job_meta.get("avatar"),
    )
    # Resume support: a dropped call continues from the persisted flow state instead of starting over.
    flow_state = FlowState.from_dict(state.flow) if state.flow else FlowState(language=state.language or plan.language)
    flow = InterviewFlow(plan, blueprint, flow_state)
    analyzer = TurnAnalyzer(
        blueprint,
        api_key=settings.openai_api_key,
        model=settings.director_model,
        clinical_model=settings.clinical_director_model,
        timeout_s=settings.director_timeout_seconds,
    )
    director = Director(flow, analyzer, recent=plan.recent_transcript)
    # A cold HTTPS connection costs a second on the first real call; do it while the greeting is being prepared.
    asyncio.create_task(analyzer.prewarm())

    language = flow.state.language or plan.language

    if voice_provider == "gpt_live":
        await _run_gpt_live_session(
            ctx,
            settings=settings,
            backend=backend,
            interview_id=interview_id,
            plan=plan,
            flow=flow,
            director=director,
            language=language,
            wants_avatar=wants_avatar,
        )
        return

    llm = build_llm(settings)
    try:
        stt = build_stt(language, settings, keyterms=plan.keyterms)
    except SessionRefused:
        await _abort_refused_session(ctx, backend)
        return
    stt_caps = getattr(stt, "capabilities", None)
    stt_aligned = getattr(stt_caps, "aligned_transcript", False) if stt_caps else False
    logger.info(
        "STT ready provider=%s class=%s aligned_transcript=%s interruption_mode=%s",
        settings.resolved_stt(),
        f"{type(stt).__module__}.{type(stt).__name__}",
        stt_aligned,
        settings.interruption_mode,
    )
    try:
        tts = build_tts(language, settings, provider=tts_override)
    except SessionRefused:
        await _abort_refused_session(ctx, backend)
        return
    mouth = tts_override or settings.resolved_tts()
    if mouth == "elevenlabs" and "elevenlabs" not in type(tts).__module__.lower():
        logger.error("ElevenLabs TTS required but API key missing; refusing session")
        await _abort_refused_session(ctx, backend)
        return
    _tts_opts = getattr(tts, "_opts", None)
    logger.info(
        "TTS ready provider=%s class=%s voice=%s model=%s",
        tts_override or settings.resolved_tts(),
        f"{type(tts).__module__}.{type(tts).__name__}",
        getattr(_tts_opts, "voice_id", None)
        or getattr(_tts_opts, "voice_name", None)
        or getattr(tts, "_voice_name", None)
        or "?",
        getattr(_tts_opts, "model", None) or getattr(_tts_opts, "model_name", None) or "?",
    )
    # OpenAI STT needs Silero VAD; Sarvam realtime STT can run with vad=None
    vad = None
    if settings.resolved_stt() != "sarvam":
        vad = ctx.proc.userdata.get("vad") or build_vad(settings)

    # Scribe on this worker must not swap to OpenAI mid-call. Other STT providers may.
    if settings.resolved_stt() == "elevenlabs_scribe":
        logger.info("Scribe STT required; OpenAI STT fallback not attached")
    else:
        try:
            from livekit.agents.stt import FallbackAdapter

            secondary = build_fallback_stt(settings)
            primary_is_fallback_model = (
                settings.resolved_stt() == "openai" and settings.openai_stt_model == "gpt-4o-mini-transcribe"
            )
            if secondary is not None and settings.resolved_stt() != "mock" and not primary_is_fallback_model:
                stt = FallbackAdapter([stt, secondary])
        except Exception:  # noqa: BLE001
            pass

    try:
        noise = build_noise_cancellation(settings)
    except SessionRefused:
        await _abort_refused_session(ctx, backend)
        return
    logger.info(
        "inbound audio noise_cancellation=%s provider=%s",
        "on" if noise is not None else "off",
        settings.noise_provider,
    )
    session_ref: dict[str, Any] = {}

    session_ref["job_ctx"] = ctx
    agent = CascadeInterviewAgent(
        plan=plan,
        flow=flow,
        director=director,
        backend=backend,
        session_ref=session_ref,
        tts_provider=tts_override or settings.resolved_tts(),
    )
    director._is_listening_armed = agent.is_listening_armed

    detector = build_turn_detector(settings) if vad is not None else None
    turn_handling = build_turn_handling(
        language,
        settings,
        has_vad=vad is not None,
        detector=detector,
        stt_aligned=stt_aligned,
    )
    logger.info(
        "turn handling: detector=%s endpointing=%s interruption=%s preemptive=%s",
        getattr(detector, "model", None) or turn_handling["turn_detection"],
        turn_handling["endpointing"],
        turn_handling["interruption"]["mode"],
        turn_handling["preemptive_generation"]["enabled"],
    )

    session_kwargs: dict[str, Any] = {
        "stt": stt,
        "llm": llm,
        "tts": tts,
        "vad": vad,
        # Marks the candidate "away" after this much quiet; SilenceMonitor turns that into escalating nudges.
        "user_away_timeout": float(settings.silence_nudge_seconds),
        # While opening uses allow_interruptions=False, drop buffered ward noise instead of queuing it.
        "discard_audio_if_uninterruptible": True,
    }
    # Needs both VAD and STT: fires when speech was heard but no transcript arrived.
    transcription_timeout = (
        settings.transcription_timeout_seconds
        if vad is not None and settings.transcription_timeout_seconds > 0
        else None
    )
    # Cap LiveKit LLM retries so one slow OpenAI blip doesn't stack into 20s+ of mute.
    conn_options = None
    try:
        from livekit.agents.types import APIConnectOptions
        from livekit.agents.voice import agent_session as _agent_session_mod

        SessionConnectOptions = getattr(_agent_session_mod, "SessionConnectOptions", None)
        if SessionConnectOptions is not None:
            llm_retries = max(0, int(settings.llm_max_retry))
            conn_options = SessionConnectOptions(
                llm_conn_options=APIConnectOptions(
                    max_retry=llm_retries,
                    retry_interval=0.5,
                    timeout=max(10.0, float(settings.llm_http_timeout_seconds)),
                ),
            )
            logger.info("LLM conn_options max_retry=%s timeout=%.0fs", llm_retries, settings.llm_http_timeout_seconds)
    except Exception:  # noqa: BLE001
        logger.exception("could not set LLM conn_options; using LiveKit defaults")

    # Newer SDKs use turn_handling; older use flat kwargs
    try:
        session = AgentSession(
            **session_kwargs,
            turn_handling=turn_handling,
            transcription_timeout=transcription_timeout,
            **({"conn_options": conn_options} if conn_options is not None else {}),
        )
    except TypeError:
        session = AgentSession(
            **session_kwargs,
            min_endpointing_delay=settings.endpointing_min_delay,
            allow_interruptions=True,
        )

    session_ref["session"] = session
    watchdog = TurnWatchdog(
        session=session,
        backend=backend,
        interview_id=interview_id,
        settings=settings,
        is_listening_armed=agent.is_listening_armed,
        get_language=lambda: agent.flow.state.language,
    )
    watchdog.attach()
    latency = LatencyTracker(
        backend=backend,
        interview_id=interview_id,
        enabled=bool(settings.voice_latency_log),
        spawn=agent.spawn,
    )
    agent.latency = latency
    latency.attach(session)
    logger.info(
        "voice latency log=%s headline=ttfa_vad_ms also=ttfa_confirm_ms stt_aligned=%s",
        settings.voice_latency_log,
        stt_aligned,
    )
    agent.spawn(
        backend.post_event(
            interview_id,
            "voice.session_config",
            {
                "stt_provider": settings.resolved_stt(),
                "stt_aligned_transcript": stt_aligned,
                "interruption_mode": settings.interruption_mode,
                "false_interruption_timeout": settings.false_interruption_timeout,
                "tts_provider": tts_override or settings.resolved_tts(),
                "voice_latency_log": settings.voice_latency_log,
                "preemptive_generation": settings.preemptive_generation,
                "voice_expressiveness": settings.voice_expressiveness,
                "voice_transcript_split": settings.voice_transcript_split,
                "voice_early_filler": settings.voice_early_filler,
                "interruption_min_words": turn_handling["interruption"]["min_words"],
            },
        )
    )
    if settings.resolved_tts() != "mock":
        fillers = FillerPlayer(tts, settings.thinking_filler_probability)
        fillers.prepare(language)
        session_ref["fillers"] = fillers

    early = EarlyFiller(
        session=session,
        fillers=session_ref.get("fillers"),
        language=language,
        enabled=bool(settings.voice_early_filler),
        on_start=(latency.on_filler_start if latency else None),
    )
    early.attach()

    @session.on("conversation_item_added")
    def _on_item(ev):  # noqa: ANN001
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        llm_text = str(getattr(item, "text_content", None) or "")
        if role == "assistant" and llm_text:
            # Prefer post-processed TTS string for chat memory when split is on (no tag echo).
            spoken = (agent._last_spoken or "").strip() or llm_text
            if settings.voice_transcript_split and settings.voice_expressiveness == "engine":
                display = agent._engine.spoken_for_transcript(spoken) if spoken else llm_text
            elif settings.voice_transcript_split:
                display = agent._engine.strip_tags(spoken) if hasattr(agent, "_engine") else spoken
            else:
                display = llm_text
            # Keep Director memory on spoken/plain so the model doesn't copy tags next turn.
            director.note_assistant(display)
            agent.spawn(
                backend.post_transcript(
                    interview_id,
                    role="assistant",
                    text=display,
                    llm_text=llm_text if settings.voice_transcript_split else None,
                    interrupted=bool(agent._interrupted) if settings.voice_transcript_split else None,
                )
            )
            agent._interrupted = False

    @session.on("agent_false_interruption")
    def _on_false_int(ev):  # noqa: ANN001
        resumed = bool(getattr(ev, "resumed", False))
        agent.note_false_interruption(resumed=resumed)
        agent.spawn(
            backend.post_event(
                interview_id,
                "audio.false_interruption",
                {"resumed": resumed},
            )
        )

    # Approximate barge-in: user starts speaking while agent speaks.
    @session.on("user_state_changed")
    def _on_user_barge(ev):  # noqa: ANN001
        if getattr(ev, "new_state", None) != "speaking":
            return
        # Opening: the mic is recorded, but noise must not count as a barge-in.
        if not agent.is_listening_armed():
            return
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0
        agent._floor.note_speech_start(now)
        if getattr(session, "agent_state", None) == "speaking":
            agent._interrupted = True

    # Start analysing as soon as the speech-to-text commits a sentence; the turn is confirmed a little later.
    @session.on("user_input_transcribed")
    def _on_transcribed(ev):  # noqa: ANN001
        text = str(getattr(ev, "transcript", "") or "")
        if not text.strip():
            return
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0
        # Greeting still playing: keep the audio, do not start an answer from it.
        if not agent.is_listening_armed():
            return
        agent._floor.note_transcript(text, now)
        if not getattr(ev, "is_final", False):
            return
        if not is_candidate_speech(text):
            return
        # Ambient barge-in while interviewer was talking — don't start Director on junk.
        if now < agent._discard_user_until:
            return
        director.on_final_transcript(ev.transcript)

    from livekit.agents.voice import room_io

    # A network drop must not end the interview: stay in the room and let the candidate come back.
    room_kwargs: dict[str, Any] = {"close_on_disconnect": False}
    # Do not replay mic audio from before the interviewer is ready. That buffer is room
    # noise, and feeding it in makes the first turn happen before the greeting.
    audio_kwargs: dict[str, Any] = {"pre_connect_audio": False}
    if noise is not None:
        audio_kwargs["noise_cancellation"] = noise
    room_kwargs["audio_input"] = room_io.AudioInputOptions(**audio_kwargs)
    start_kwargs: dict[str, Any] = {
        "agent": agent,
        "room": ctx.room,
        "room_options": room_io.RoomOptions(**room_kwargs),
    }

    SilenceMonitor(
        session=session, agent=agent, flow=flow, spacing_s=float(settings.silence_nudge_seconds)
    ).attach()
    ConnectionGuard(room=ctx.room, agent=agent, flow=flow, grace_s=float(settings.reconnect_grace_seconds)).attach()

    avatar_on = False
    if wants_avatar:
        try:
            avatar_on = await _start_tavus_avatar(session, ctx, settings)
        except Exception:  # noqa: BLE001
            logger.exception("Tavus avatar failed to start; continuing voice-only")
        if avatar_on:
            # Tavus publishes synced A/V; do not also publish agent TTS into the room.
            room_kwargs["audio_output"] = False
            start_kwargs["room_options"] = room_io.RoomOptions(**room_kwargs)

    await session.start(**start_kwargs)

    if settings.thinking_sound_enabled and settings.thinking_sound_volume > 0 and not avatar_on:
        vol = settings.thinking_sound_volume
        background = BackgroundAudioPlayer(
            # Probabilities sum below 1 so some turns stay silent instead of typing every time.
            thinking_sound=[
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=vol, probability=0.4, fade_in=0.3, fade_out=0.4),
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=vol, probability=0.4, fade_in=0.3, fade_out=0.4),
            ],
        )
        try:
            await background.start(room=ctx.room, agent_session=session)
        except Exception:  # noqa: BLE001
            logger.exception("background audio failed to start; continuing without it")

    async def _shutdown() -> None:
        await watchdog.post_summary()
        try:
            summary = latency.summary()
            if settings.voice_latency_log and summary.get("turns"):
                await backend.post_event(interview_id, "turn.latency_summary", summary)
                logger.info("turn.latency_summary %s", summary)
        except Exception:  # noqa: BLE001
            logger.exception("latency summary failed")
        await backend.flush()
        await backend.aclose()

    ctx.add_shutdown_callback(_shutdown)


def prewarm(proc: JobProcess) -> None:
    settings = get_settings()
    try:
        proc.userdata["vad"] = build_vad(settings)
    except Exception as err:  # noqa: BLE001
        logger.warning("VAD prewarm skipped: %s", err)
    # Warm TTS websockets / HTTP so the first greeting is not cold-start slow.
    providers: list[str] = []
    if settings.elevenlabs_api_key:
        providers.append("elevenlabs")
    resolved = settings.resolved_tts()
    if resolved and resolved != "mock" and resolved not in providers:
        providers.append(resolved)
    for provider in providers:
        try:
            tts = build_tts("hi-IN", settings, provider=provider)
            prewarm_fn = getattr(tts, "prewarm", None)
            if callable(prewarm_fn):
                result = prewarm_fn()
                # Sync prewarm hooks may return a coroutine before the job loop exists.
                if asyncio.iscoroutine(result):
                    try:
                        asyncio.run(result)
                    except RuntimeError:
                        result.close()
                        logger.info("TTS prewarm deferred (no loop) provider=%s", provider)
                        continue
            proc.userdata["tts_prewarmed"] = True
            logger.info("TTS prewarmed provider=%s", provider)
        except Exception as err:  # noqa: BLE001
            logger.warning("TTS prewarm skipped for %s: %s", provider, err)


def cli_main() -> None:
    settings = get_settings()
    # Export LiveKit env for the workers framework
    os.environ.setdefault("LIVEKIT_URL", settings.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", settings.livekit_api_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", settings.livekit_api_secret)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.sarvam_api_key:
        os.environ.setdefault("SARVAM_API_KEY", settings.sarvam_api_key)
    if settings.tavus_api_key:
        os.environ.setdefault("TAVUS_API_KEY", settings.tavus_api_key)
    if settings.tavus_face_id:
        os.environ.setdefault("TAVUS_FACE_ID", settings.tavus_face_id)
    if settings.tavus_pal_id:
        os.environ.setdefault("TAVUS_PAL_ID", settings.tavus_pal_id)
    if settings.google_cloud_project:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)
    if settings.google_application_credentials:
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS",
            settings.google_application_credentials,
        )

    logger.warning(
        "worker starting agent_name=%s tavus_key=%s (python main.py dev does not hot-reload; restart after code changes)",
        settings.v2_agent_name,
        "yes" if (settings.tavus_api_key or os.getenv("TAVUS_API_KEY")) else "NO",
    )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=settings.v2_agent_name,
        ),
    )


if __name__ == "__main__":
    cli_main()
