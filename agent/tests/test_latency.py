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
