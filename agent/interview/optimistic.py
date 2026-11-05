"""Speak the next screening question before the analyst returns.

Default off (OPTIMISTIC_SCREENING). The next question is chosen inside InterviewFlow.apply,
after it has written the slots. This path runs that apply on a copy, assuming the focused
field was answered, and speaks that move. The live flow is applied only when the real
analysis arrives.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from interview.analysis import SlotUpdate, TurnAnalysis
from interview.flow import InterviewFlow, Move
from interview.flow_state import FlowState
from interview.plan import classify_answer

_BODY_FIELDS = frozenset({"height_cm", "weight_kg"})
_REPAIR_INTENTS = frozenset({"repeat_request", "rephrase_request", "refusal"})


def optimistic_eligible(flow: InterviewFlow, text: str, *, enabled: bool) -> bool:
    """Non-phone, non-body slot turns with a substantive answer of at least two words."""
    if not enabled or flow.done or flow.state.stage != "screening":
        return False
    focus = flow.state.focus or {}
    if focus.get("type") != "slots":
        return False
    ids = [str(i) for i in (focus.get("ids") or [])]
    if not ids:
        return False
    for fid in ids:
        if fid == "phone" or fid in _BODY_FIELDS:
            return False
        spec = flow.bp.field_spec(fid)
        if spec is not None and spec.kind == "phone":
            return False
    if classify_answer(text) != "substantive":
        return False
    return len([w for w in text.split() if w.strip()]) >= 2


def needs_repair(analysis: TurnAnalysis | None) -> bool:
    """Unclear, a repeat or refusal, or a denied value. The spoken ask may be wrong."""
    if analysis is None:
        return False
    if analysis.intelligibility == "unclear":
        return True
    if analysis.intent in _REPAIR_INTENTS:
        return True
    return analysis.confirmation == "denied"


def preview_filled_move(flow: InterviewFlow, text: str) -> Move | None:
    """Next ask if the focused field were filled. Does not touch the live flow."""
    focus_ids = [str(i) for i in ((flow.state.focus or {}).get("ids") or [])]
    if not focus_ids:
        return None
    clone = InterviewFlow(
        flow.plan,
        flow.bp,
        FlowState.from_dict(flow.state.to_dict()),
        clock=flow._clock,
    )
    field = focus_ids[0]
    assumed = TurnAnalysis(
        intent="answer",
        intelligibility="clear",
        slot_updates=[SlotUpdate(field, text.strip(), 0.9, text.strip()[:80])],
        raw_utterance=text,
        source="llm",
    )
    move = clone.apply(assumed)
    if move.kind not in ("ask_field", "ask_care", "ask_care_item"):
        return None
    if move.kind == "ask_field":
        new_ids = [str(i) for i in ((clone.state.focus or {}).get("ids") or [])]
        if new_ids == focus_ids:
            return None
    return move


async def run_optimistic_turn(
    *,
    flow: InterviewFlow,
    text: str,
    analyze: Callable[[], Awaitable[TurnAnalysis]],
    speak: Callable[[Move], Any],
    enabled: bool,
) -> tuple[Move, list[str]]:
    """Speak a preview, then analyze, then apply the real result on the live flow.

    A repair move is queued instead of being spoken when the real analysis rejects
    the assumption. The returned move is the one that was spoken.
    """
    order: list[str] = []
    preview = preview_filled_move(flow, text) if optimistic_eligible(flow, text, enabled=enabled) else None
    if preview is not None:
        order.append("speak")
        speak(preview)
    analysis = await analyze()
    order.append("analyze")
    real = flow.apply(analysis)
    order.append("apply")
    if preview is not None and needs_repair(analysis):
        flow.queue_repair(real)
        return preview, order
    if preview is None:
        order.append("speak")
        speak(real)
    return (preview or real), order
