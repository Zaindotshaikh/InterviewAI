"""Snapshot: Move.kind + stage transitions must stay stable (voice refactor non-negotiable)."""

import json
from pathlib import Path

import pytest

from interview.analysis import SlotUpdate, TurnAnalysis
from interview.blueprint import Blueprint
from interview.flow import InterviewFlow
from interview.plan import InterviewPlan

BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"


@pytest.fixture(scope="module")
def blueprint() -> Blueprint:
    return Blueprint.from_api(json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")))


def _flow(blueprint: Blueprint) -> InterviewFlow:
    plan = InterviewPlan(
        interview_id="snap",
        language="hi-IN",
        stt_mode="codemix",
        target_minutes=8,
        company_name="Kreeda Labs",
        interviewer_name="Aven",
        role_title="Staff Nurse",
        criteria=[],
        keyterms=[],
        glossary_hints=[],
        steps=[],
        system_prompt="test",
        candidate_name="Priya",
    )
    return InterviewFlow(plan, blueprint)


def test_opening_to_screening_kind_snapshot(blueprint: Blueprint):
    flow = _flow(blueprint)
    move = flow.opening()
    assert move.kind == "opening"
    assert flow.stage == "screening"
    assert move.tone is None  # Flow never sets tone


def test_screening_city_capture_stays_screening(blueprint: Blueprint):
    flow = _flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            slot_updates=[SlotUpdate(field="city", value="Pune", confidence=0.9)],
        )
    )
    assert flow.stage == "screening"
    assert move.kind  # some ask/confirm kind
