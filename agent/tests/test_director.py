"""Director + analyzer wiring with a fake OpenAI client (no network, no LiveKit)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from interview.analysis import TurnAnalyzer, heuristic_analysis
from interview.director import Director
from interview.flow import InterviewFlow
from interview.flow_state import FlowState
from tests.test_flow import blueprint, make_plan  # noqa: F401  (fixture re-export)


class FakeClient:
    def __init__(self, replies: list[object], delay: float = 0.0) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.models: list[str] = []
        self.systems: list[str] = []
        self.schemas: list[dict] = []
        self.payloads: list[str] = []
        self.delay = delay
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        self.models.append(str(kwargs.get("model") or ""))
        messages = kwargs.get("messages") or []
        self.systems.append(str(messages[0]["content"]) if messages else "")
        self.schemas.append(kwargs["response_format"]["json_schema"]["schema"])
        self.payloads.append(str(messages[1]["content"]) if len(messages) > 1 else "")
        await asyncio.sleep(self.delay)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])


CITY = {
    "intent": "answer",
    "intelligibility": "clear",
    "slot_updates": [{"field": "city", "value": "Pune", "confidence": 0.95}],
}


def build(blueprint, client, state=None):  # noqa: F811
    flow = InterviewFlow(make_plan(), blueprint, state)
    analyzer = TurnAnalyzer(blueprint, api_key="x", model="m", client=client, timeout_s=1.0)
    return Director(flow, analyzer), flow


def test_screening_uses_fast_model_and_clinical_uses_stronger_model(blueprint):  # noqa: F811
    client = FakeClient([CITY, CITY])
    analyzer = TurnAnalyzer(
        blueprint,
        api_key="x",
        model="gpt-4o-mini",
        clinical_model="gpt-4o",
        client=client,
        timeout_s=1.0,
    )

    async def go():
        fallback = heuristic_analysis("Pune")
        await analyzer.analyze("city answer", clinical=False, fallback=fallback)
        await analyzer.analyze("clinical answer", clinical=True, fallback=fallback)

    asyncio.run(go())
    assert client.models == ["gpt-4o-mini", "gpt-4o"]
    assert "slot_updates" in client.schemas[0]["properties"]
    assert "Screening extraction" in client.systems[0]
    clinical_props = client.schemas[1]["properties"]
    assert "clinical" in clinical_props
    assert "slot_updates" not in clinical_props
    assert "care_updates" not in clinical_props
    assert "confirmation" not in clinical_props
    assert "experience_level" not in clinical_props
    assert "Screening extraction" not in client.systems[1]
    assert "Clinical grading" in client.systems[1]


def test_decide_uses_analysis_and_records_slot(blueprint):  # noqa: F811
    director, flow = build(blueprint, FakeClient([CITY]))
    flow.opening()

    async def go():
        return await director.decide("Pune ke liye apply kar rahi hoon")

    asyncio.run(go())
    assert flow.state.slots["city"].value == "Pune"


def test_early_analysis_is_reused_when_transcript_matches(blueprint):  # noqa: F811
    client = FakeClient([CITY], delay=0.05)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("Pune ke liye apply kar rahi hoon")
        await asyncio.sleep(0.01)
        await director.decide("Pune ke liye apply kar rahi hoon")

    asyncio.run(go())
    assert client.calls == 1
    assert flow.state.slots["city"].value == "Pune"


def test_two_finals_in_one_turn_are_analyzed_once(blueprint):  # noqa: F811
    """Scribe can commit 'nine eight seven' then 'six five four'. That is one turn."""
    client = FakeClient([CITY], delay=0.05)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("nine eight seven")
        director.on_final_transcript("six five four")
        await director.decide("nine eight seven six five four")

    asyncio.run(go())
    assert client.calls == 1
    assert "nine eight seven six five four" in client.payloads[0]


def test_punctuation_only_keeps_the_running_grade(blueprint):  # noqa: F811
    client = FakeClient([CITY], delay=0.05)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("I check the pulse.")
        director.on_final_transcript(".")
        await director.decide("I check the pulse")

    asyncio.run(go())
    assert client.calls == 1


def test_changed_transcript_reruns_analysis(blueprint):  # noqa: F811
    client = FakeClient([CITY])
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("Pune")
        await asyncio.sleep(0.01)
        await director.decide("Pune ke liye apply kar rahi hoon")

    asyncio.run(go())
    assert client.calls == 2


def test_analyst_failure_falls_back_and_never_raises(blueprint):  # noqa: F811
    director, flow = build(blueprint, FakeClient([RuntimeError("boom")]))
    flow.opening()
    move = asyncio.run(director.decide("haan ji"))
    assert move is not None
    assert director.analyzer.failures == 1


def test_noise_skips_the_analyst(blueprint):  # noqa: F811
    client = FakeClient([CITY])
    director, flow = build(blueprint, client)
    flow.opening()
    move = asyncio.run(director.decide(""))
    assert client.calls == 0
    assert move.kind == "ask_repeat"


def test_recent_turns_and_last_question_tracking(blueprint):  # noqa: F811
    director, flow = build(blueprint, FakeClient([CITY]))
    director.note_assistant("Which city are you applying for?")
    assert flow.state.last_question.startswith("Which city")
    director.note_assistant("Okay, thanks.")
    assert flow.state.last_question.startswith("Which city")
    for i in range(20):
        director.note_user(f"turn {i}")
    assert len(director.recent) <= 8


def test_resume_from_persisted_state_does_not_regreet(blueprint):  # noqa: F811
    director, flow = build(blueprint, FakeClient([CITY]))
    flow.opening()
    asyncio.run(director.decide("Pune"))
    saved = json.loads(json.dumps(flow.state.to_dict()))
    director2, flow2 = build(blueprint, FakeClient([CITY]), FlowState.from_dict(saved))
    move = flow2.opening()
    assert move.kind == "resume"
    assert flow2.state.slots["city"].value == "Pune"
