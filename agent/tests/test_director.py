"""Director + analyzer wiring with a fake OpenAI client (no network, no LiveKit)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from interview.analysis import TurnAnalyzer
from interview.director import Director
from interview.flow import InterviewFlow
from interview.flow_state import FlowState
from tests.test_flow import blueprint, make_plan  # noqa: F401  (fixture re-export)


class FakeClient:
    def __init__(self, replies: list[object], delay: float = 0.0) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.delay = delay
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
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
