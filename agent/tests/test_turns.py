import asyncio
from types import SimpleNamespace

from config import Settings
from interview.speech import SpeechArbiter
from interview.turns import (
    MAX_BACKEND_EVENTS,
    REPEAT_DIRECTIVE,
    TurnWatchdog,
    apply_language_profile,
    build_turn_handling,
    detector_covers,
    endpointing_options,
    summarize,
)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_detector_covers_only_hindi_and_english():
    assert detector_covers("hi-IN") and detector_covers("en-IN")
    for lang in ("mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"):
        assert not detector_covers(lang)


def test_uncovered_languages_get_a_higher_silence_floor():
    s = _settings()
    assert endpointing_options("hi-IN", s)["min_delay"] == s.endpointing_min_delay
    assert endpointing_options("mr-IN", s)["min_delay"] == s.endpointing_min_delay_uncovered
    assert s.endpointing_min_delay_uncovered > s.endpointing_min_delay


def test_without_the_detector_every_language_uses_the_safe_floor():
    s = _settings(turn_detector_enabled=False)
    assert endpointing_options("hi-IN", s)["min_delay"] == s.endpointing_min_delay_uncovered


def test_max_delay_never_below_min_delay():
    s = _settings(endpointing_max_delay=0.2, endpointing_min_delay_uncovered=0.8)
    opts = endpointing_options("mr-IN", s)
    assert opts["max_delay"] >= opts["min_delay"]


def test_turn_handling_uses_detector_adaptive_interruptions_and_no_preemptive_by_default():
    detector = object()
    handling = build_turn_handling("hi-IN", _settings(), has_vad=True, detector=detector)
    assert handling["turn_detection"] is detector
    assert handling["interruption"]["mode"] == "adaptive"
    assert handling["interruption"]["resume_false_interruption"] is True
    assert handling["interruption"]["min_words"] >= 2
    assert handling["interruption"]["false_interruption_timeout"] >= 1.5
    assert handling["preemptive_generation"] == {"enabled": False}
    assert handling["endpointing"]["mode"] == "dynamic"


def test_no_align_stt_requires_more_words_to_barge_in():
    s = _settings(interruption_min_words=2, interruption_min_words_no_align=3)
    aligned = build_turn_handling("hi-IN", s, has_vad=True, stt_aligned=True)
    bare = build_turn_handling("hi-IN", s, has_vad=True, stt_aligned=False)
    assert aligned["interruption"]["min_words"] == 2
    assert bare["interruption"]["min_words"] == 3


def test_turn_handling_falls_back_to_vad_then_stt():
    assert build_turn_handling("hi-IN", _settings(), has_vad=True)["turn_detection"] == "vad"
    no_vad = build_turn_handling("hi-IN", _settings(), has_vad=False)
    assert no_vad["turn_detection"] == "stt"
    assert no_vad["interruption"]["mode"] == "vad"


def test_apply_language_profile_updates_the_session_and_survives_errors():
    calls = []

    class Session:
        def update_options(self, **kw):
            calls.append(kw)

    s = _settings()
    apply_language_profile(Session(), "mr-IN", s)
    assert calls[0]["endpointing_opts"]["min_delay"] == s.endpointing_min_delay_uncovered

    class Broken:
        def update_options(self, **kw):
            raise RuntimeError("boom")

    apply_language_profile(Broken(), "hi-IN", s)  # must not raise


def test_summarize():
    out = summarize([0.4, 0.8, 1.2], {"transcription_timeouts": 1})
    assert out["turns"] == 3 and out["eou_delay_median_s"] == 0.8 and out["eou_delay_max_s"] == 1.2
    assert out["transcription_timeouts"] == 1
    assert summarize([], {})["turns"] == 0


class _FakeSession:
    def __init__(self, agent_state="listening", salvage_transcript=""):
        self.agent_state = agent_state
        self.handlers = {}
        self.replies = []
        self.salvage_transcript = salvage_transcript
        self.commits = []

    def on(self, name, cb):
        self.handlers[name] = cb

    def generate_reply(self, **kw):
        self.replies.append(kw)

    def commit_user_turn(self, **kw):
        self.commits.append(kw)

        async def _done():
            return self.salvage_transcript

        return _done()


class _FakeBackend:
    def __init__(self):
        self.events = []

    async def post_event(self, interview_id, event_type, data=None):
        self.events.append((event_type, data))


def _watchdog(session, backend, **settings):
    arb = SpeechArbiter()
    wd = TurnWatchdog(
        session=session,
        backend=backend,
        interview_id="i1",
        settings=_settings(**settings),
        speak=arb.play,
    )
    wd.attach()
    return wd


def test_missing_transcript_asks_the_candidate_to_repeat_with_a_cap():
    async def run():
        session, backend = _FakeSession(), _FakeBackend()
        wd = _watchdog(session, backend, max_repeat_prompts=2)
        ev = SimpleNamespace(speech_duration=8.0)
        for _ in range(4):
            session.handlers["user_transcription_timeout"](ev)
            await asyncio.sleep(0.05)
        assert [r["instructions"] for r in session.replies] == [REPEAT_DIRECTIVE] * 2
        assert wd.summary()["transcription_timeouts"] == 4
        assert wd.summary()["repeat_prompts"] == 2
        assert len(session.commits) == 4

    asyncio.run(run())


def test_transcription_timeout_salvages_interim_instead_of_repeating():
    async def run():
        session, backend = _FakeSession(salvage_transcript="number hai 9112323549"), _FakeBackend()
        wd = _watchdog(session, backend)
        session.handlers["user_transcription_timeout"](SimpleNamespace(speech_duration=4.0))
        await asyncio.sleep(0.05)
        assert session.replies == []
        assert len(session.commits) == 1
        assert wd.summary()["interim_salvages"] == 1
        assert wd.summary()["repeat_prompts"] == 0

    asyncio.run(run())


def test_transcription_timeout_skips_salvage_before_listening_is_armed():
    async def run():
        session, backend = _FakeSession(salvage_transcript="बाहर कहीं जाना"), _FakeBackend()
        wd = TurnWatchdog(
            session=session,
            backend=backend,
            interview_id="i1",
            settings=_settings(),
            is_listening_armed=lambda: False,
        )
        wd.attach()
        session.handlers["user_transcription_timeout"](SimpleNamespace(speech_duration=4.0))
        await asyncio.sleep(0.05)
        assert session.commits == []
        assert session.replies == []
        assert wd.summary()["preamble_skips"] == 1
        assert wd.summary()["interim_salvages"] == 0
        assert backend.events[-1][0] == "audio.preamble_skip"

    asyncio.run(run())


def test_does_not_talk_over_the_agent():
    async def run():
        session = _FakeSession(agent_state="speaking")
        _watchdog(session, _FakeBackend())
        session.handlers["user_transcription_timeout"](SimpleNamespace(speech_duration=5.0))
        await asyncio.sleep(0.05)
        assert session.replies == []
        assert session.commits == []

    asyncio.run(run())


def test_watchdog_repeat_skips_when_arbiter_busy():
    async def run():
        session, backend = _FakeSession(), _FakeBackend()
        arb = SpeechArbiter()
        held = asyncio.Event()

        class Held:
            def interrupt(self, force=False):
                held.set()

            async def wait_for_playout(self):
                await held.wait()

        await arb.play("director", lambda: Held(), wait=False)
        wd = TurnWatchdog(
            session=session,
            backend=backend,
            interview_id="i1",
            settings=_settings(),
            speak=arb.play,
        )
        wd.attach()
        session.handlers["user_transcription_timeout"](SimpleNamespace(speech_duration=8.0))
        await asyncio.sleep(0.05)
        assert session.replies == []
        assert session.commits == []
        assert wd.summary()["repeat_prompts"] == 0
        held.set()
        await asyncio.sleep(0.02)

    asyncio.run(run())


def test_records_eou_delays_ignores_other_metrics_and_posts_summary():
    async def run():
        session, backend = _FakeSession(), _FakeBackend()
        wd = _watchdog(session, backend)
        eou = SimpleNamespace(
            type="eou_metrics", end_of_utterance_delay=0.6, transcription_delay=0.2, on_user_turn_completed_delay=0.05
        )
        session.handlers["metrics_collected"](SimpleNamespace(metrics=eou))
        session.handlers["metrics_collected"](SimpleNamespace(metrics=SimpleNamespace(type="llm_metrics")))
        session.handlers["agent_false_interruption"](SimpleNamespace(resumed=True))
        await wd.post_summary()
        event_type, data = backend.events[-1]
        assert event_type == "turn.summary"
        assert data["turns"] == 1 and data["false_interruptions"] == 1

    asyncio.run(run())


def test_backend_events_are_capped():
    async def run():
        session, backend = _FakeSession(), _FakeBackend()
        _watchdog(session, backend, max_repeat_prompts=0)
        for _ in range(MAX_BACKEND_EVENTS + 10):
            session.handlers["user_transcription_timeout"](SimpleNamespace(speech_duration=1.0))
        await asyncio.sleep(0.05)
        assert len(backend.events) == MAX_BACKEND_EVENTS

    asyncio.run(run())
