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
    native_script_reminder,
    sanitize_candidate_text,
    spoken_style,
)
from interview.director import Director
from interview.liveness import ConnectionGuard, SilenceMonitor
from providers import (
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
        provider = getattr(inner, "provider", "") or ""
        try:
            if "sarvam" in provider.lower():
                inner.update_options(language=code)
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
    ) -> None:
        voice = get_settings().google_tts_voice
        instructions = (
            f"{plan.system_prompt}\n\n{BASE_VOICE_RULES}\n\n{spoken_style(plan.language, voice)}\n\n"
            f"{native_script_reminder(plan.language)}"
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
        self._disfluency = Disfluency(
            get_settings().hesitation_rate,
            use_pause_tags=False,
            phrase_pause_rate=get_settings().phrase_pause_rate,
        )
        # Set when a pre-rendered reaction was just played, so the reply's first sentence gets no um.
        self._suppress_lead = False
        self._greeting_pending = True

    async def tts_node(self, text, model_settings):  # noqa: ANN001
        tts = self.session.tts
        self._disfluency.use_pause_tags = bool(getattr(getattr(tts, "_opts", None), "use_markup", False))
        skip_first, self._suppress_lead = self._suppress_lead, False
        opening, self._greeting_pending = self._greeting_pending, False
        shaped = self._disfluency.apply(
            text,
            self.flow.state.language,
            skip_first=skip_first,
            opening=opening,
        )
        async for frame in Agent.default.tts_node(self, shaped, model_settings):
            yield frame

    @function_tool()
    async def switch_language(self, language_code: str) -> str:
        """Switch interview language mid-call. language_code must be like hi-IN, ta-IN, te-IN, kn-IN, ml-IN, en-IN."""
        profile = get_profile(language_code)
        session: AgentSession | None = self.session_ref.get("session")
        if session is None:
            return f"Unable to switch; stay on {self.flow.state.language}"

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
        try:
            await self.session.generate_reply(instructions=f"CONTROLLER DIRECTIVE: {move.directive}")
        except Exception:  # noqa: BLE001
            logger.exception("generate_reply failed for %s", move.kind)

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
        resuming = self.flow.state.stage != "opening"
        if resuming:
            for turn in self.plan.recent_transcript:
                if turn["role"] == "assistant":
                    self.director.note_assistant(turn["text"])
                else:
                    self.director.note_user(turn["text"])
            await self._rehydrate()
        move = self.flow.resume() if resuming else self.flow.opening()
        await self.backend.post_event(
            self.plan.interview_id, "interview.agent_entered", {"resumed": resuming, "stage": self.flow.state.stage}
        )
        await self.speak_move(move)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:  # noqa: ANN001
        raw = getattr(new_message, "text_content", None) or getattr(new_message, "content", "") or ""
        if isinstance(raw, list):
            raw = " ".join(str(x) for x in raw)
        text = sanitize_candidate_text(str(raw))
        settings = get_settings()

        detected = detect_script_language(text)
        events: list[tuple[str, dict[str, Any]]] = []
        if detected and detected != self.flow.state.language:
            events.append(("language.detected", {"from": self.flow.state.language, "to": detected}))

        # Play the short acknowledgement first, so the analyst call below is covered by speech rather than silence.
        filler_note = ""
        fillers: FillerPlayer | None = self.session_ref.get("fillers")
        if fillers is not None and not self.flow.done and classify_answer(text) == "substantive":
            picked = fillers.pick(self.flow.state.language, text)
            if picked is not None:
                filler_text, frames = picked
                self.session.say(filler_text, audio=frames_iter(frames), add_to_chat_ctx=False)
                self._suppress_lead = True
                filler_note = (
                    f'\nYou have already said "{filler_text}" out loud as your reaction. Do not open with another '
                    "acknowledgement; continue straight on from it."
                )

        elapsed_min = (datetime.now(timezone.utc) - self._started_at).total_seconds() / 60.0
        if elapsed_min >= settings.v2_max_minutes and not self.flow.done:
            move = self.flow.force_complete("time")
        else:
            move = await self.director.decide(text)
        self.director.note_user(text)

        self._turn_index += 1
        self.spawn(
            self.backend.post_transcript(
                self.plan.interview_id, role="user", text=text, turn_index=self._turn_index
            )
        )
        self.spawn(self._persist(events + move.events))

        logger.info("move=%s stage=%s", move.kind, self.flow.state.stage)
        turn_ctx.add_message(
            role="system",
            content=(
                f"CONTROLLER DIRECTIVE: {move.directive}\n"
                f"{native_script_reminder(self.flow.state.language)}{filler_note}"
            ),
        )
        self._finish_if_needed(move)


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
    logger.info(
        "job %s avatar=%s tts=%s (plan=%s meta=%s)",
        interview_id,
        wants_avatar,
        tts_override or settings.resolved_tts(),
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
    llm = build_llm(settings)
    stt = build_stt(language, settings, keyterms=plan.keyterms)
    tts = build_tts(language, settings, provider=tts_override)
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

    # Fallback adapter when available
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

    noise = build_noise_cancellation(settings)
    session_ref: dict[str, Any] = {}

    session_ref["job_ctx"] = ctx
    agent = InterviewAgent(plan=plan, flow=flow, director=director, backend=backend, session_ref=session_ref)

    detector = build_turn_detector(settings) if vad is not None else None
    turn_handling = build_turn_handling(language, settings, has_vad=vad is not None, detector=detector)
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
    }
    # Needs both VAD and STT: fires when speech was heard but no transcript arrived.
    transcription_timeout = (
        settings.transcription_timeout_seconds
        if vad is not None and settings.transcription_timeout_seconds > 0
        else None
    )
    # Newer SDKs use turn_handling; older use flat kwargs
    try:
        session = AgentSession(
            **session_kwargs,
            turn_handling=turn_handling,
            transcription_timeout=transcription_timeout,
        )
    except TypeError:
        session = AgentSession(
            **session_kwargs,
            min_endpointing_delay=settings.endpointing_min_delay,
            allow_interruptions=True,
        )

    session_ref["session"] = session
    watchdog = TurnWatchdog(session=session, backend=backend, interview_id=interview_id, settings=settings)
    watchdog.attach()
    if settings.resolved_tts() != "mock":
        fillers = FillerPlayer(tts, settings.thinking_filler_probability)
        fillers.prepare(language)
        session_ref["fillers"] = fillers

    @session.on("conversation_item_added")
    def _on_item(ev):  # noqa: ANN001
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None) or ""
        if role == "assistant" and text:
            director.note_assistant(str(text))
            agent.spawn(backend.post_transcript(interview_id, role="assistant", text=str(text)))

    # Start analysing as soon as the speech-to-text commits a sentence; the turn is confirmed a little later.
    @session.on("user_input_transcribed")
    def _on_transcribed(ev):  # noqa: ANN001
        if getattr(ev, "is_final", False) and ev.transcript:
            director.on_final_transcript(ev.transcript)

    from livekit.agents.voice import room_io

    # A network drop must not end the interview: stay in the room and let the candidate come back.
    room_kwargs: dict[str, Any] = {"close_on_disconnect": False}
    if noise is not None:
        room_kwargs["audio_input"] = room_io.AudioInputOptions(noise_cancellation=noise)
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

    if settings.thinking_sound_volume > 0 and not avatar_on:
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
        await backend.flush()
        await backend.aclose()

    ctx.add_shutdown_callback(_shutdown)


def prewarm(proc: JobProcess) -> None:
    settings = get_settings()
    try:
        proc.userdata["vad"] = build_vad(settings)
    except Exception as err:  # noqa: BLE001
        logger.warning("VAD prewarm skipped: %s", err)
    # Prewarm TTS when Sarvam is configured
    if settings.resolved_tts() == "sarvam" and settings.sarvam_api_key:
        try:
            tts = build_tts("hi-IN", settings)
            if hasattr(tts, "prewarm"):
                tts.prewarm()
            proc.userdata["tts_prewarmed"] = True
        except Exception as err:  # noqa: BLE001
            logger.warning("TTS prewarm skipped: %s", err)


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
