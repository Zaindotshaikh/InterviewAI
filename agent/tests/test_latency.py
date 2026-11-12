"""Unit tests for latency percentile helpers (Phase 1)."""

from interview.latency import percentile, summarize_turns


def test_percentile_empty():
    assert percentile([], 50) is None


def test_percentile_p50_p95():
    vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(vals, 50) == 50.0
    assert percentile(vals, 95) == 100.0
    assert percentile([42], 50) == 42.0


def test_summarize_turns():
    turns = [
        {"ttfa_vad_ms": 800, "ttfa_confirm_ms": 400, "director_ms": 200},
        {"ttfa_vad_ms": 1200, "ttfa_confirm_ms": 500, "director_ms": 300},
        {"ttfa_vad_ms": 900, "ttfa_confirm_ms": 450},
    ]
    s = summarize_turns(turns)
    assert s["turns"] == 3
    assert s["ttfa_vad_ms"]["n"] == 3
    assert s["ttfa_vad_ms"]["p50"] is not None
    assert s["director_ms"]["n"] == 2


class _Backend:
    async def post_event(self, *a, **k):
        return None


def _tracker():
    from interview.latency import LatencyTracker

    return LatencyTracker(backend=_Backend(), interview_id="t", enabled=True, spawn=lambda c: c.close())


def test_pre_hook_marks_survive_into_the_turn(monkeypatch):
    import interview.latency as lat

    clock = {"t": 100.0}
    monkeypatch.setattr(lat.time, "monotonic", lambda: clock["t"])
    tr = _tracker()
    tr._mark_latest("vad_speech_end")
    clock["t"] = 100.8
    tr._mark_latest("stt_final")
    clock["t"] = 101.2
    tr.on_hook_start(1)
    clock["t"] = 103.0
    tr.on_director_done(1.8, early_hit=False, analyst_tokens=120)
    clock["t"] = 103.5
    tr.on_tts_text()
    clock["t"] = 104.2
    tr.on_reply_audio()
    tr._mark("first_audio")
    tr._finalize(force=False)
    turn = tr._turns[0]
    assert turn["reply_from_vad_ms"] == 4200.0
    assert turn["reply_from_confirm_ms"] == 3000.0
    assert turn["stt_final_from_vad_ms"] == 800.0
    assert turn["tts_text_after_director_ms"] == 500.0
    assert turn["early_analysis"] == "miss"
    assert turn["analyst_tokens"] == 120


def test_newest_vad_end_wins_before_the_hook(monkeypatch):
    import interview.latency as lat

    clock = {"t": 10.0}
    monkeypatch.setattr(lat.time, "monotonic", lambda: clock["t"])
    tr = _tracker()
    tr._mark_latest("vad_speech_end")
    clock["t"] = 12.0
    tr._mark_latest("vad_speech_end")
    assert tr._cur["mono_marks"]["vad_speech_end"] == 12.0


def test_reply_marks_ignored_outside_a_turn():
    tr = _tracker()
    tr.on_tts_text()
    tr.on_reply_audio()
    assert tr._cur is None
