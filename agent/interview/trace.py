"""Bodies for the private call file. Policy stays in InterviewFlow; this only describes what already happened."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

_MARKS = {
    "vad_speech_end": "speechEnd",
    "stt_final": "scribeFinal",
    "director_done": "directorDone",
    "reply_audio": "replyAudio",
}
_LATENCY = {
    "stt_final_from_vad_ms": "scribeAfterSpeech",
    "director_ms": "director",
    "reply_from_vad_ms": "replyAfterSpeech",
    "ttfa_vad_ms": "firstAudioAfterSpeech",
    "llm_ttft_ms": "wordingFirstToken",
    "tts_ttfb_ms": "speechFirstByte",
    "eou_delay_ms": "endOfUtterance",
    "transcription_delay_ms": "transcription",
    "filler_from_vad_ms": "fillerAfterSpeech",
}


def line_kind(move: Any) -> str:
    """fixed: must-say line. guided: a suggested line the voice model may word. paraphrase: directive only."""
    if getattr(move, "verbatim", None) and not getattr(move, "scripted", False):
        return "fixed"
    if getattr(move, "verbatim", None):
        return "guided"
    return "paraphrase"


def focus_label(focus: dict[str, Any] | None) -> str:
    focus = focus or {}
    kind = str(focus.get("type") or "")
    fields = focus.get("fields")
    if isinstance(fields, list) and fields:
        target = "+".join(str(item) for item in fields)
    else:
        target = str(focus.get("field") or focus.get("item") or "")
    if kind and target:
        return f"{kind}:{target}"
    return kind or target


def focus_attempt(state: Any) -> int | None:
    focus = getattr(state, "focus", None) or {}
    fields = focus.get("fields")
    if isinstance(fields, list) and fields:
        names = [str(item) for item in fields]
    elif focus.get("field"):
        names = [str(focus["field"])]
    else:
        names = []
    slots = getattr(state, "slots", {}) or {}
    attempts = [int(slots[name].attempts) for name in names if name in slots]
    if not attempts:
        return None
    return max(attempts)


def slot_rows(state: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field, slot in (getattr(state, "slots", {}) or {}).items():
        status = str(getattr(slot, "status", "") or "")
        value = getattr(slot, "value", None)
        if status == "empty" and value in (None, ""):
            continue
        rows.append(
            {
                "field": str(field),
                "value": value,
                "status": status or "empty",
                "confidence": round(float(getattr(slot, "confidence", 0.0) or 0.0), 2),
                "attempts": int(getattr(slot, "attempts", 0) or 0),
            }
        )
    return rows


def open_body(*, language: str, started_at: datetime, settings: Any) -> dict[str, Any]:
    fallback = (getattr(settings, "llm_fallback_model", "") or "").strip()
    models: dict[str, str] = {
        "screening": str(settings.director_model),
        "clinical": str(settings.clinical_director_model),
        "wording": str(settings.llm_model),
        "speechToText": str(settings.resolved_stt()),
        "textToSpeech": str(settings.elevenlabs_model),
        "voiceLanguage": language,
    }
    if fallback and fallback != settings.llm_model:
        models["wordingFallback"] = fallback
    return {
        "op": "open",
        "language": language,
        "startedAt": started_at.isoformat(),
        "build": os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "local",
        "models": models,
    }


def turn_body(
    *,
    index: int,
    move: Any,
    state: Any,
    analysis: Any,
    commit: str,
    heard: str,
    analyst_model: str,
) -> dict[str, Any]:
    source = str(getattr(analysis, "source", "") or "unknown")
    analyst: dict[str, str] = {"source": source}
    intent = str(getattr(analysis, "intent", "") or "")
    if intent:
        analyst["intent"] = intent
    if source == "llm" and analyst_model:
        analyst["model"] = analyst_model
    body: dict[str, Any] = {
        "op": "turn",
        "index": index,
        "stage": str(getattr(state, "stage", "") or ""),
        "focus": focus_label(getattr(state, "focus", None)),
        "move": str(getattr(move, "kind", "") or ""),
        "line": line_kind(move),
        "heard": (heard or "").strip(),
        "commit": commit if commit in ("short_answer", "normal") else "normal",
        "analyst": analyst,
    }
    attempt = focus_attempt(state)
    if attempt is not None:
        body["attempt"] = attempt
    return body


def timing_body(
    *,
    index: int,
    session_mono: float,
    marks: dict[str, float],
    latency: dict[str, Any],
) -> dict[str, Any] | None:
    timeline: dict[str, int] = {}
    for src, name in _MARKS.items():
        if src not in marks:
            continue
        ms = int(round((marks[src] - session_mono) * 1000))
        if ms >= 0:
            timeline[name] = ms
    latency_ms: dict[str, int] = {}
    for src, name in _LATENCY.items():
        value = latency.get(src)
        if isinstance(value, (int, float)):
            latency_ms[name] = int(round(value))
    if not timeline and not latency_ms:
        return None
    body: dict[str, Any] = {"op": "turn", "index": index}
    if timeline:
        body["timeline"] = {"fromSessionStartMs": timeline}
    if latency_ms:
        body["latencyMs"] = latency_ms
    return body
