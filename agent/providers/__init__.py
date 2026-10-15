"""STT / TTS / LLM / noise provider factories."""

from __future__ import annotations

import logging
import os
from typing import Any

from livekit.agents.stt import StreamAdapter
from livekit.plugins import google as google_plugin
from livekit.plugins import noise_cancellation as noise_cancellation_plugin
from livekit.plugins import openai as openai_plugin
from livekit.plugins import sarvam
from livekit.plugins import silero

from config import Settings, get_settings
from interview.language import get_profile

logger = logging.getLogger("interview-v2.providers")

_SARVAM_LLM_MODELS = {"gemma4", "sarvam-105b", "glm5.2", "sarvam-105b-conversations"}

# Locales with Chirp 3 HD voices; Odia has none, so it falls back to Indian English
_CHIRP3_LOCALES = {"en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "bn-IN", "gu-IN", "pa-IN"}
# Indic locales where Gemini TTS is GA; others fall back to Chirp 3 HD
_GEMINI_TTS_LOCALES = {"en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN"}


def _google_credentials_available(settings: Settings) -> bool:
    """True if a credentials file or Application Default Credentials are present."""
    path = settings.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.isfile(path):
        return True
    # gcloud auth application-default login (no SA key needed)
    candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "gcloud", "application_default_credentials.json"),
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
    ]
    return any(os.path.isfile(p) for p in candidates if p)


def uses_gemini_tts(language: str, settings: Settings) -> bool:
    return settings.google_tts_model.startswith("gemini") and language in _GEMINI_TTS_LOCALES


def google_voice_for(language: str, settings: Settings) -> tuple[str, str]:
    """Return (locale, voice name) for a language code under the configured Google TTS model."""
    if uses_gemini_tts(language, settings):
        return language, settings.google_tts_voice
    locale = language if language in _CHIRP3_LOCALES else "en-IN"
    if locale != language:
        logger.warning("No Chirp 3 HD voice for %s; using %s", language, locale)
    return locale, f"{locale}-Chirp3-HD-{settings.google_tts_voice}"


def build_vad(settings: Settings | None = None):
    """Silero VAD — required for non-streaming STT (OpenAI)."""
    settings = settings or get_settings()
    return silero.VAD.load(
        min_speech_duration=max(0.05, settings.vad_min_speech_ms / 1000.0),
        min_silence_duration=max(0.2, settings.vad_min_silence_ms / 1000.0),
        activation_threshold=settings.vad_sot_threshold,
    )


def _wrap_openai_stt(stt: Any, settings: Settings):
    """Batch-only OpenAI STT models need a VAD StreamAdapter for live turns."""
    if stt.capabilities.streaming:
        return stt
    return StreamAdapter(stt=stt, vad=build_vad(settings))


def openai_stt_languages(language: str) -> list[str]:
    """Primary language plus English so code-mixed speech (Hinglish/Tanglish) stays in-script."""
    primary = language.split("-")[0]
    return [primary] if primary == "en" else [primary, "en"]


def build_openai_stt(language: str, settings: Settings, keyterms: list[str] | None = None):
    model = settings.openai_stt_model
    kwargs: dict[str, Any] = {"model": model, "api_key": settings.openai_api_key}
    profile = get_profile(language)
    if model.startswith(("gpt-transcribe", "gpt-live-transcribe")):
        kwargs["language"] = openai_stt_languages(language)
        if keyterms:
            kwargs["keywords"] = keyterms[:40]
    else:
        kwargs["language"] = language.split("-")[0]
    kwargs["prompt"] = (
        f"Nursing job interview in India. Candidate speaks {profile.label} mixed with English "
        "(code-mixed, informal slang). Transcribe exactly as spoken; keep "
        f"{profile.label} words in native script and English words in Latin script. Do not translate."
    )
    return _wrap_openai_stt(openai_plugin.STT(**kwargs), settings)


def _openai_llm(model: str, settings: Settings):
    """Voice OpenAI LLM with a streaming-friendly httpx timeout (plugin default read=5s is too tight)."""
    import httpx

    read_s = max(5.0, float(settings.llm_http_timeout_seconds))
    return openai_plugin.LLM(
        model=model,
        api_key=settings.openai_api_key,
        max_retries=0,
        timeout=httpx.Timeout(connect=10.0, read=read_s, write=10.0, pool=5.0),
    )


def build_llm(settings: Settings | None = None):
    settings = settings or get_settings()
    provider = settings.resolved_llm()

    if provider == "mock":
        if settings.openai_api_key:
            return _openai_llm(settings.llm_model, settings)
        raise RuntimeError("mock/openai LLM requires OPENAI_API_KEY")

    if provider == "sarvam":
        model = settings.llm_model if settings.llm_model in _SARVAM_LLM_MODELS else "sarvam-105b"
        return sarvam.LLM(model=model, api_key=settings.sarvam_api_key)

    primary = _openai_llm(settings.llm_model, settings)
    fallback_model = (settings.llm_fallback_model or "").strip()
    if fallback_model and fallback_model != settings.llm_model:
        try:
            from livekit.agents.llm import FallbackAdapter

            secondary = _openai_llm(fallback_model, settings)
            logger.info(
                "voice LLM primary=%s fallback=%s http_read=%.0fs",
                settings.llm_model,
                fallback_model,
                settings.llm_http_timeout_seconds,
            )
            return FallbackAdapter([primary, secondary])
        except Exception:  # noqa: BLE001
            logger.exception("LLM FallbackAdapter unavailable; using primary only")

    logger.info(
        "voice LLM model=%s http_read=%.0fs (Director stays %s)",
        settings.llm_model,
        settings.llm_http_timeout_seconds,
        settings.director_model,
    )
    return primary


def _scribe_language_hints(language: str) -> tuple[str, list[str]]:
    """Primary + secondary language codes for Scribe v2 realtime code-mix."""
    primary = (language or "en-IN").split("-")[0].lower()
    # Always allow English code-mix; Indic pairs get Hindi as a bridge when useful.
    secondary = ["en"]
    if primary not in ("en", "hi"):
        secondary.append("hi")
    secondary = [c for c in secondary if c != primary]
    return primary, secondary


def build_elevenlabs_scribe_stt(language: str, settings: Settings, keyterms: list[str] | None = None):
    """ElevenLabs Scribe v2 realtime with word timestamps for adaptive interruption A/B."""
    from livekit.plugins import elevenlabs

    api_key = settings.elevenlabs_api_key or os.environ.get("ELEVEN_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("elevenlabs_scribe requires ELEVENLABS_API_KEY / ELEVEN_API_KEY")

    primary, secondary = _scribe_language_hints(language)
    # Realtime keyterms: up to 50 terms, ≤20 chars each (plugin docs).
    trimmed: list[str] = []
    for term in keyterms or []:
        t = " ".join(str(term).split())[:20].strip()
        if t and t.lower() not in {x.lower() for x in trimmed}:
            trimmed.append(t)
        if len(trimmed) >= 50:
            break

    # Manual commit never finalizes until ~36s of audio — phone digits die as partials
    # and LiveKit fires transcription_timeout. Server VAD commits on silence so Flow
    # sees FINAL transcripts (digits, city, yes/no) on each pause.
    server_vad = {
        "vad_silence_threshold_secs": 1.5,
        "vad_threshold": 0.4,
        "min_speech_duration_ms": 100,
        "min_silence_duration_ms": 100,
    }
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "model": "scribe_v2_realtime",
        "language_code": primary,
        "secondary_languages": secondary,
        "include_timestamps": True,
        "sample_rate": 16000,
        "server_vad": server_vad,
    }
    if trimmed:
        kwargs["keyterms"] = trimmed
    stt = elevenlabs.STT(**kwargs)
    aligned = getattr(getattr(stt, "capabilities", None), "aligned_transcript", None)
    logger.info(
        "ElevenLabs Scribe STT model=scribe_v2_realtime lang=%s secondary=%s aligned=%s "
        "commit=server_vad silence=%.1fs keyterms=%d",
        primary,
        secondary,
        aligned,
        server_vad["vad_silence_threshold_secs"],
        len(trimmed),
    )
    return stt


def build_stt(language: str, settings: Settings | None = None, keyterms: list[str] | None = None):
    settings = settings or get_settings()
    provider = settings.resolved_stt()
    profile = get_profile(language)

    if provider == "mock":
        return _wrap_openai_stt(
            openai_plugin.STT(model="gpt-4o-mini-transcribe", api_key=settings.openai_api_key),
            settings,
        )

    if provider == "elevenlabs_scribe":
        try:
            return build_elevenlabs_scribe_stt(language, settings, keyterms)
        except Exception as err:  # noqa: BLE001
            fallback = settings.stt_scribe_fallback
            logger.warning(
                "elevenlabs_scribe STT failed (%s); fallback=%s",
                err,
                fallback,
            )
            if fallback == "openai":
                return build_openai_stt(language, settings, keyterms)
            raise

    if provider == "sarvam":
        # Prefer realtime streaming class when available
        stt_cls = getattr(sarvam, "STTStreaming", None)
        kwargs: dict[str, Any] = {
            "language": language,
            "api_key": settings.sarvam_api_key,
        }
        if stt_cls is not None:
            kwargs.update(
                {
                    "stream_type": "fast",
                    "mode": profile.stt_mode,
                    "endpointing": "vad",
                    "sample_rate": 16000,
                    "vad_min_silence_ms": settings.vad_min_silence_ms,
                    "vad_min_speech_ms": settings.vad_min_speech_ms,
                    "vad_sot_threshold": settings.vad_sot_threshold,
                }
            )
            # keyterms / prompt when supported
            if keyterms:
                prompt = "Nursing interview. Terms: " + ", ".join(keyterms[:40])
                kwargs["prompt"] = prompt[:500]
            try:
                return stt_cls(**kwargs)
            except TypeError:
                # Older plugin signature
                safe = {k: v for k, v in kwargs.items() if k in ("language", "api_key", "mode", "stream_type")}
                return stt_cls(**safe)

        # Legacy STT
        try:
            return sarvam.STT(
                language=language,
                model="saaras:v4",
                mode=profile.stt_mode,
                api_key=settings.sarvam_api_key,
            )
        except TypeError:
            return sarvam.STT(language=language, api_key=settings.sarvam_api_key)

    return build_openai_stt(language, settings, keyterms)


def elevenlabs_language(language: str) -> str:
    """ElevenLabs wants a short language code (hi, mr, en), not a BCP-47 locale."""
    return (language or "en").split("-")[0].lower()


def elevenlabs_voice_for(language: str, settings: Settings) -> str:
    """Sarah for English; Alice / ELEVENLABS_VOICE_ID_LOCAL for Indic locales."""
    code = elevenlabs_language(language)
    if code in ("en", ""):
        return settings.elevenlabs_voice_id
    return settings.elevenlabs_voice_id_local or settings.elevenlabs_voice_id


def build_tts(language: str, settings: Settings | None = None, *, provider: str | None = None):
    settings = settings or get_settings()
    provider = provider or settings.resolved_tts()
    profile = get_profile(language)

    if provider == "mock":
        return openai_plugin.TTS(model="gpt-4o-mini-tts", voice="alloy", api_key=settings.openai_api_key)

    if provider == "elevenlabs":
        from livekit.plugins import elevenlabs

        api_key = settings.elevenlabs_api_key or os.environ.get("ELEVEN_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            logger.warning("TTS_PROVIDER=elevenlabs but no ELEVENLABS_API_KEY; falling back to OpenAI TTS")
            provider = "openai"
        else:
            voice_id = elevenlabs_voice_for(language, settings)
            logger.info(
                "ElevenLabs TTS voice=%s lang=%s model=%s",
                voice_id,
                elevenlabs_language(language),
                settings.elevenlabs_model,
            )
            return elevenlabs.TTS(
                voice_id=voice_id,
                model=settings.elevenlabs_model,
                api_key=api_key,
                language=elevenlabs_language(language),
            )

    if provider == "google" and not _google_credentials_available(settings):
        logger.warning("TTS_PROVIDER=google but no Google credentials found; falling back to OpenAI TTS")
        provider = "openai"

    if provider == "google":
        from google.cloud import texttospeech as google_tts

        locale, voice_name = google_voice_for(language, settings)
        google_kwargs: dict[str, Any] = {
            "language": locale,
            "voice_name": voice_name,
            "speaking_rate": settings.google_speaking_rate,
            # Streaming only accepts PCM/OGG_OPUS; Chirp 3 unary rejects PCM, but the agent always streams
            "audio_encoding": google_tts.AudioEncoding.PCM,
            "use_streaming": True,
            "sample_rate": 24000,
        }
        if uses_gemini_tts(language, settings):
            google_kwargs["model_name"] = settings.google_tts_model
            google_kwargs["prompt"] = settings.google_tts_style
        else:
            # Markup input lets Chirp honour [pause short] tags from the disfluency layer.
            google_kwargs["use_markup"] = True
        if settings.google_application_credentials:
            google_kwargs["credentials_file"] = settings.google_application_credentials
        return google_plugin.TTS(**google_kwargs)

    if provider == "sarvam":
        kwargs: dict[str, Any] = {
            "model": "bulbul:v3",
            "speaker": profile.tts_speaker,
            "api_key": settings.sarvam_api_key,
        }
        # language_code vs target_language_code across plugin versions
        try:
            return sarvam.TTS(
                **kwargs,
                language_code=language,
                speech_sample_rate=24000,
                output_audio_codec="linear16",
                min_buffer_size=30,
                pace=0.85,
                temperature=0.5,
            )
        except TypeError:
            try:
                return sarvam.TTS(**kwargs, target_language_code=language)
            except TypeError:
                return sarvam.TTS(speaker=profile.tts_speaker, api_key=settings.sarvam_api_key)

    return openai_plugin.TTS(model="gpt-4o-mini-tts", voice="alloy", api_key=settings.openai_api_key)


def build_noise_cancellation(settings: Settings | None = None):
    """Inbound audio cleanup before VAD/STT.

    - krisp → Krisp BVC (background *voice* + noise cancellation; preferred for ward chatter)
    - aicoustics → ai-coustics Quail Voice Focus L (primary-speaker isolation A/B)
    - none → passthrough
    Never stack client + agent enhanced NC on the same stream.
    """
    settings = settings or get_settings()
    provider = settings.noise_provider
    if provider == "none":
        logger.info("noise cancellation disabled (NOISE_PROVIDER=none)")
        return None

    if provider == "krisp":
        try:
            # BVC isolates the near-field speaker and suppresses other talkers — NC alone is not enough.
            if hasattr(noise_cancellation_plugin, "BVC"):
                opts = noise_cancellation_plugin.BVC()
                logger.info("noise cancellation: Krisp BVC (background voice + noise)")
                return opts
            if hasattr(noise_cancellation_plugin, "NC"):
                opts = noise_cancellation_plugin.NC()
                logger.warning("noise cancellation: Krisp NC only (no BVC in plugin — env noise, not other voices)")
                return opts
        except Exception as err:  # noqa: BLE001
            logger.warning("Krisp noise cancellation unavailable: %s", err)
            return None

    if provider == "aicoustics":
        try:
            from livekit.plugins import ai_coustics

            model = getattr(ai_coustics.EnhancerModel, "QUAIL_VF_L", None) or getattr(
                ai_coustics.EnhancerModel, "QUAIL_VF_S", None
            )
            if model is None:
                logger.warning("ai-coustics installed but Voice Focus model missing")
                return None
            params = None
            if hasattr(ai_coustics, "ModelParameters"):
                try:
                    params = ai_coustics.ModelParameters(enhancement_level=0.8)
                except Exception:  # noqa: BLE001
                    params = None
            kwargs: dict[str, Any] = {"model": model}
            if params is not None:
                kwargs["model_parameters"] = params
            opts = ai_coustics.audio_enhancement(**kwargs)
            logger.info("noise cancellation: ai-coustics Voice Focus (%s)", getattr(model, "name", model))
            return opts
        except ImportError:
            logger.warning(
                "NOISE_PROVIDER=aicoustics but livekit-plugins-ai-coustics is not installed "
                "(pip install livekit-plugins-ai-coustics)"
            )
            return None
        except Exception as err:  # noqa: BLE001
            logger.warning("ai-coustics noise cancellation unavailable: %s", err)
            return None

    logger.warning("unknown NOISE_PROVIDER=%s — disabling", provider)
    return None


def build_fallback_stt(settings: Settings | None = None):
    """Optional secondary STT (OpenAI) when primary fails."""
    settings = settings or get_settings()
    if not settings.openai_api_key:
        return None
    return _wrap_openai_stt(
        openai_plugin.STT(model="gpt-4o-mini-transcribe", api_key=settings.openai_api_key),
        settings,
    )
