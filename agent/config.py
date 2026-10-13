"""Environment and provider selection for the v2 interview agent."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderMode = Literal["mock", "openai", "sarvam"]
SttProvider = Literal["openai", "sarvam", "elevenlabs_scribe", "mock"]
TtsProvider = Literal["openai", "sarvam", "google", "elevenlabs", "mock"]
LlmProvider = Literal["openai", "sarvam", "mock"]
NoiseProvider = Literal["none", "krisp", "aicoustics"]
SttFallback = Literal["openai", "none"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LiveKit
    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    v2_agent_name: str = "interview-v2"

    # Backend control plane
    backend_url: str = "http://127.0.0.1:3001"
    v2_internal_secret: str = "dev-v2-internal-secret-change-me"

    # Providers
    provider_mode: ProviderMode = "openai"
    stt_provider: SttProvider | None = None
    tts_provider: TtsProvider | None = None
    llm_provider: LlmProvider | None = None
    llm_model: str = "gpt-4o-mini"
    noise_provider: NoiseProvider = "none"
    fallback_stt_key: str | None = None
    # When STT_PROVIDER=elevenlabs_scribe fails to build/connect, fall back (default openai).
    stt_scribe_fallback: SttFallback = "openai"
    # Persist per-turn turn.latency events (additive; default on for Phase 1 baselines).
    voice_latency_log: bool = True
    # legacy = LLM writes EL tags; engine = post-processor owns ≤1 tag (EL TTS only).
    voice_expressiveness: Literal["legacy", "engine"] = "engine"
    voice_sigh_rate: float = 0.15
    voice_umm_rate: float = 0.25
    voice_pause_rate: float = 0.55
    voice_express_cooldown_turns: int = 2
    # Store text (= TTS-bound) + llmText separately; scoring uses text.
    voice_transcript_split: bool = True
    # Optional Director empathyTone field (default off — timeout uses kind→tone).
    director_empathy_tone: bool = False
    # Phase 3: start ack on VAD silence + interim; cancel if speech resumes.
    voice_early_filler: bool = False
    # Soft keyboard while thinking (0 volume still disables).
    thinking_sound_enabled: bool = True
    # Mid-call TTS fallback when ElevenLabs fails (google = Chirp).
    tts_fallback_on_error: Literal["none", "google"] = "google"
    # Raise when STT has no word alignment so हाँ/जी don't barge in.
    interruption_min_words_no_align: int = 2

    # API keys
    openai_api_key: str | None = None
    sarvam_api_key: str | None = None
    tavus_api_key: str | None = None
    tavus_face_id: str | None = None
    tavus_pal_id: str | None = None
    # ElevenLabs (opt-in via /elevenlabs-interviewer or TTS_PROVIDER=elevenlabs)
    elevenlabs_api_key: str | None = None
    # Default English voice: Sarah (premade — works on free API).
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    # Indic languages: Alice (premade, free API). Sujata (4mCfn38CsM9hGLvDrPxv) needs a paid plan.
    elevenlabs_voice_id_local: str = "Xb7hH8MSUJpSbSDYk0k2"
    # eleven_v4_turbo = realtime (~100ms); eleven_v4 = max quality (slower). Both support 90+ languages.
    elevenlabs_model: str = "eleven_v4_turbo"
    aic_sdk_license: str | None = None
    google_application_credentials: str | None = None
    google_cloud_project: str | None = None

    # Google Chirp 3 HD voice (Kore, Aoede, Leda = female; Charon, Puck, Orus = male)
    google_tts_voice: str = "Kore"
    # Chirp 3: 1.0 is the unadjusted model pace (sounds rushed on a live call). 0.25–2.0.
    # Interview speech lands closer to 0.85 (~15% slower), which matches conversational human speed.
    google_speaking_rate: float = 0.85
    # chirp_3 (~0.3s to first audio) or gemini-2.5-flash-tts (style-controllable, ~1s to first audio)
    google_tts_model: str = "chirp_3"
    google_tts_style: str = (
        "You are a friendly Indian HR interviewer talking to a nurse candidate. "
        "Speak warmly and conversationally at a relaxed, human pace, like a real person on a phone interview. Do not rush."
    )

    # gpt-live-transcribe streams and accepts a language list for code-switched speech
    openai_stt_model: str = "gpt-live-transcribe"

    # Interview behaviour
    # Hard stop for the whole call; the blueprint's own hard cap applies too (the lower one wins).
    v2_max_minutes: int = 25
    # --- Interview director (per-turn analyst that reads the candidate and steers the flow) ---
    # Reads each answer (intent, extracted facts, clinical grade, contradictions) as structured JSON.
    director_model: str = "gpt-4o"
    # Model used while grading clinical answers; same default.
    clinical_director_model: str = "gpt-4o"
    # Give up on the analyst after this long and use the rule-based fallback so the call never stalls.
    director_timeout_seconds: float = 4.5
    # Seconds of candidate silence before the first nudge; later levels follow at the same spacing.
    silence_nudge_seconds: int = 12
    # How long a dropped candidate has to rejoin before the interview is ended as incomplete.
    reconnect_grace_seconds: int = 120
    silence_end_seconds: int = 90
    max_consecutive_noise: int = 3
    vad_min_silence_ms: int = 400
    vad_min_speech_ms: int = 100
    vad_sot_threshold: float = 0.6
    interruption_min_words: int = 1
    false_interruption_timeout: float = 1.3

    # --- Turn-taking (policy lives in interview/turns.py) ---
    # Semantic end-of-turn model: waits when the candidate is clearly mid-thought, replies fast when finished.
    turn_detector_enabled: bool = True
    # "dynamic" learns each candidate's own pause length during the call; "fixed" never adapts.
    endpointing_mode: Literal["fixed", "dynamic"] = "dynamic"
    # Floor (s) of silence before replying, for languages the end-of-turn model covers (Hindi, English).
    endpointing_min_delay: float = 0.4
    # Higher floor for languages it does not cover (Marathi, Tamil, Telugu, Kannada, Malayalam),
    # where silence is the only signal and candidates pause more to find words.
    endpointing_min_delay_uncovered: float = 0.8
    # Longest silence (s) the agent will wait while the candidate still seems mid-thought.
    endpointing_max_delay: float = 3.0
    # Dynamic mode adaptation speed: lower learns the candidate's pauses faster (0 < alpha <= 1).
    endpointing_alpha: float = 0.7
    # "adaptive" tells "mm-hmm"/coughs from real interruptions; falls back to "vad" on its own if it errors.
    interruption_mode: Literal["adaptive", "vad"] = "adaptive"
    # Start the LLM before the turn is confirmed. Off: our turn hook edits the chat context every turn,
    # which discards the early result, so it only doubles LLM cost.
    preemptive_generation: bool = False
    # Ask the candidate to repeat when speech was heard but no transcript arrived within this many seconds (0 = off).
    transcription_timeout_seconds: float = 3.0
    # Max times per call the agent asks the candidate to repeat after a missing transcript.
    max_repeat_prompts: int = 3

    # Chance of a short native reaction ("बरं.", "अच्छा.") in the interview voice after the candidate finishes, 0 disables
    thinking_filler_probability: float = 0.6
    # Unused: the greeting never starts with a filler. Kept so existing .env files still load.
    opening_hesitation: bool = False
    # Chance a reply may keep the one "umm," the LLM placed (0 = never speak an um)
    hesitation_rate: float = 0.7
    # Chance that each phrase boundary (comma / conjunction / long-run break) becomes a real pause. 0 = off.
    phrase_pause_rate: float = 0.85
    # Soft keyboard typing while the agent prepares a reply, 0 disables
    thinking_sound_volume: float = 0.25

    def resolved_stt(self) -> SttProvider:
        if self.stt_provider:
            return self.stt_provider
        if self.provider_mode == "sarvam":
            return "sarvam"
        if self.provider_mode == "mock":
            return "mock"
        return "openai"

    def resolved_tts(self) -> TtsProvider:
        if self.tts_provider:
            return self.tts_provider
        if self.provider_mode == "sarvam":
            return "sarvam"
        if self.provider_mode == "mock":
            return "mock"
        return "openai"

    def resolved_llm(self) -> LlmProvider:
        if self.llm_provider:
            return self.llm_provider
        if self.provider_mode == "sarvam":
            return "sarvam"
        if self.provider_mode == "mock":
            return "mock"
        return "openai"


@lru_cache
def get_settings() -> Settings:
    # Map uppercase env vars commonly used in the monorepo
    aliases = {
        "LIVEKIT_URL": "livekit_url",
        "LIVEKIT_API_KEY": "livekit_api_key",
        "LIVEKIT_API_SECRET": "livekit_api_secret",
        "OPENAI_API_KEY": "openai_api_key",
        "SARVAM_API_KEY": "sarvam_api_key",
        "TAVUS_API_KEY": "tavus_api_key",
        "TAVUS_FACE_ID": "tavus_face_id",
        "TAVUS_PAL_ID": "tavus_pal_id",
        "ELEVENLABS_API_KEY": "elevenlabs_api_key",
        "ELEVEN_API_KEY": "elevenlabs_api_key",
        "ELEVENLABS_VOICE_ID": "elevenlabs_voice_id",
        "ELEVENLABS_VOICE_ID_LOCAL": "elevenlabs_voice_id_local",
        "ELEVENLABS_MODEL": "elevenlabs_model",
        "AIC_SDK_LICENSE": "aic_sdk_license",
        "BACKEND_URL": "backend_url",
        "V2_INTERNAL_SECRET": "v2_internal_secret",
        "PROVIDER_MODE": "provider_mode",
        "STT_PROVIDER": "stt_provider",
        "STT_SCRIBE_FALLBACK": "stt_scribe_fallback",
        "VOICE_LATENCY_LOG": "voice_latency_log",
        "VOICE_EXPRESSIVENESS": "voice_expressiveness",
        "VOICE_SIGH_RATE": "voice_sigh_rate",
        "VOICE_UMM_RATE": "voice_umm_rate",
        "VOICE_PAUSE_RATE": "voice_pause_rate",
        "VOICE_EXPRESS_COOLDOWN_TURNS": "voice_express_cooldown_turns",
        "VOICE_TRANSCRIPT_SPLIT": "voice_transcript_split",
        "DIRECTOR_EMPATHY_TONE": "director_empathy_tone",
        "VOICE_EARLY_FILLER": "voice_early_filler",
        "THINKING_SOUND_ENABLED": "thinking_sound_enabled",
        "TTS_FALLBACK_ON_ERROR": "tts_fallback_on_error",
        "INTERRUPTION_MIN_WORDS_NO_ALIGN": "interruption_min_words_no_align",
        "TTS_PROVIDER": "tts_provider",
        "LLM_PROVIDER": "llm_provider",
        "LLM_MODEL": "llm_model",
        "NOISE_PROVIDER": "noise_provider",
        "GOOGLE_APPLICATION_CREDENTIALS": "google_application_credentials",
        "GOOGLE_CLOUD_PROJECT": "google_cloud_project",
        "GOOGLE_TTS_VOICE": "google_tts_voice",
        "GOOGLE_SPEAKING_RATE": "google_speaking_rate",
        "GOOGLE_TTS_MODEL": "google_tts_model",
        "GOOGLE_TTS_STYLE": "google_tts_style",
        "OPENAI_STT_MODEL": "openai_stt_model",
        "THINKING_FILLER_PROBABILITY": "thinking_filler_probability",
        "THINKING_SOUND_VOLUME": "thinking_sound_volume",
        "OPENING_HESITATION": "opening_hesitation",
        "TURN_DETECTOR_ENABLED": "turn_detector_enabled",
        "ENDPOINTING_MODE": "endpointing_mode",
        "ENDPOINTING_MIN_DELAY": "endpointing_min_delay",
        "ENDPOINTING_MIN_DELAY_UNCOVERED": "endpointing_min_delay_uncovered",
        "ENDPOINTING_MAX_DELAY": "endpointing_max_delay",
        "ENDPOINTING_ALPHA": "endpointing_alpha",
        "INTERRUPTION_MODE": "interruption_mode",
        "PREEMPTIVE_GENERATION": "preemptive_generation",
        "TRANSCRIPTION_TIMEOUT_SECONDS": "transcription_timeout_seconds",
        "MAX_REPEAT_PROMPTS": "max_repeat_prompts",
        "HESITATION_RATE": "hesitation_rate",
        "PHRASE_PAUSE_RATE": "phrase_pause_rate",
        "V2_AGENT_NAME": "v2_agent_name",
        "V2_MAX_MINUTES": "v2_max_minutes",
        "DIRECTOR_MODEL": "director_model",
        "CLINICAL_DIRECTOR_MODEL": "clinical_director_model",
        "DIRECTOR_TIMEOUT_SECONDS": "director_timeout_seconds",
        "SILENCE_NUDGE_SECONDS": "silence_nudge_seconds",
        "RECONNECT_GRACE_SECONDS": "reconnect_grace_seconds",
    }
    # Agent .env wins (override=True). Parent server/.env only fills gaps.
    try:
        from dotenv import load_dotenv

        if os.path.exists(".env"):
            load_dotenv(".env", override=True)
        for path in ("../server/.env", "../.env"):
            if os.path.exists(path):
                load_dotenv(path, override=False)
    except Exception:
        pass
    # LiveKit ElevenLabs plugin reads ELEVEN_API_KEY — always mirror the active key.
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    if key:
        os.environ["ELEVENLABS_API_KEY"] = key
        os.environ["ELEVEN_API_KEY"] = key
    # pydantic-settings reads env; aliases above are identical names after lowercasing
    _ = aliases
    return Settings()
