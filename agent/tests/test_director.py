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
    def __init__(self, replies: list[object], delay: float = 0.0, delays: list[float] | None = None) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.models: list[str] = []
        self.systems: list[str] = []
        self.schemas: list[dict] = []
        self.payloads: list[str] = []
        self.max_tokens: list[int] = []
        self.delay = delay
        self.delays = list(delays or [])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        self.models.append(str(kwargs.get("model") or ""))
        messages = kwargs.get("messages") or []
        self.systems.append(str(messages[0]["content"]) if messages else "")
        self.schemas.append(kwargs["response_format"]["json_schema"]["schema"])
        self.payloads.append(str(messages[1]["content"]) if len(messages) > 1 else "")
        self.max_tokens.append(int(kwargs.get("max_tokens") or 0))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        delay = self.delays[self.calls - 1] if self.calls - 1 < len(self.delays) else self.delay
        await asyncio.sleep(delay)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])


def analysis_calls(client: FakeClient) -> int:
    """Count move-path requests. The background enrich call is separate."""
    return sum("new_claims" not in schema.get("properties", {}) for schema in client.schemas)


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
    assert "clinical" not in client.schemas[0]["properties"]
    assert "quality" not in client.schemas[0]["properties"]
    assert "Screening extraction" in client.systems[0]
    assert "Clinical grading" not in client.systems[0]
    clinical_props = client.schemas[1]["properties"]
    assert "quality" in clinical_props
    assert "clinical" not in clinical_props
    assert "slot_updates" not in clinical_props
    assert "care_updates" not in clinical_props
    assert "confirmation" not in clinical_props
    assert "experience_level" not in clinical_props
    assert "Screening extraction" not in client.systems[1]
    assert "Clinical grading" in client.systems[1]
    assert client.max_tokens == [300, 300]


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
    assert analysis_calls(client) == 1
    assert flow.state.slots["city"].value == "Pune"
    assert director.analyzer.last_source == "early_reused"


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
    assert analysis_calls(client) == 1
    payloads = [
        payload
        for payload, schema in zip(client.payloads, client.schemas, strict=True)
        if "new_claims" not in schema.get("properties", {})
    ]
    assert len(payloads) == 1
    assert "nine eight seven six five four" in payloads[0]


def test_punctuation_only_keeps_the_running_grade(blueprint):  # noqa: F811
    client = FakeClient([CITY], delay=0.05)
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("I check the pulse.")
        director.on_final_transcript(".")
        await director.decide("I check the pulse")

    asyncio.run(go())
    assert analysis_calls(client) == 1


def test_changed_transcript_reruns_analysis(blueprint):  # noqa: F811
    client = FakeClient([CITY])
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        director.on_final_transcript("Pune")
        await asyncio.sleep(0.01)
        await director.decide("Pune ke liye apply kar rahi hoon")

    asyncio.run(go())
    assert analysis_calls(client) == 2


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


def test_care_fallback_does_not_fail_the_gate(blueprint):
    from tests.test_flow import reach_care

    client = FakeClient([RuntimeError("analyst down")])
    director, flow = build(blueprint, client)
    reach_care(flow)
    flow.state.care["diaper_care"].stance = "refuses"
    flow.state.care["diaper_care"].persuasions = flow.bp.limits.max_persuasions

    move = asyncio.run(director.decide("I won't answer"))
    assert director.analyzer.last_source == "heuristic"
    assert flow.state.gate_failed is None
    assert flow.state.care["diaper_care"].persuasions == flow.bp.limits.max_persuasions
    assert move.kind in ("ask_care", "ask_care_item")


def test_three_heuristic_care_turns_need_human_review(blueprint):
    from tests.test_flow import reach_care

    client = FakeClient([RuntimeError("analyst down")])
    director, flow = build(blueprint, client)
    reach_care(flow)

    async def go():
        first = await director.decide("I won't answer")
        second = await director.decide("I won't answer")
        third = await director.decide("I won't answer")
        return first, second, third

    first, second, third = asyncio.run(go())
    assert first.kind in ("ask_care", "ask_care_item")
    assert second.kind == "ask_care_confirm"
    assert second.verbatim
    assert third.kind == "needs_human_review"
    assert flow.state.outcome == "needs_human_review"
    assert flow.state.gate_failed is None


def test_llm_care_refusals_still_fail_the_gate(blueprint):
    from tests.test_flow import reach_care

    refusal = {
        "intent": "refusal",
        "intelligibility": "clear",
        "nervous": False,
        "slot_updates": [],
        "confirmation": {"field": "", "result": "none"},
        "care_updates": [{"item": "diaper_care", "stance": "refuses", "reason": "no"}],
        "experience_level": "unknown",
        "answer_depth": "none",
    }
    blank = {
        "new_claims": [],
        "contradictions": [],
        "gist_en": "",
        "aside": "",
        "resume_mismatch": "",
        "quote": "",
        "summary_en": "",
    }
    client = FakeClient([refusal, blank, refusal, blank, refusal, blank])
    director, flow = build(blueprint, client)
    reach_care(flow)

    async def turn(text: str):
        move = await director.decide(text)
        if director._enrich_tasks:
            await asyncio.gather(*director._enrich_tasks)
        return move

    async def go():
        first = await turn("I won't answer")
        second = await turn("I will not tell")
        third = await turn("I refuse to answer")
        return first, second, third

    first, second, third = asyncio.run(go())
    assert first.kind == "persuade"
    assert second.kind == "persuade"
    assert third.kind == "gate_failed"
    assert flow.state.gate_failed == "diaper_care"
    assert director.analyzer.last_source == "llm"


def test_turn_latency_event_includes_analyst_fields():
    from interview.latency import LatencyTracker

    class Backend:
        async def post_event(self, interview_id, event_type, data=None):
            return None

    tracker = LatencyTracker(backend=Backend(), interview_id="i", enabled=True, spawn=lambda coro: coro.close())
    tracker.on_hook_start(3)
    tracker.on_director_done(
        0.2,
        analyst_ms=123.4,
        analyst_source="llm",
        hedged=True,
        schema="lean",
    )
    tracker._finalize(force=True)
    payload = tracker._turns[-1]
    assert payload["director_ms"] == 200.0
    assert payload["analyst_ms"] == 123.4
    assert payload["analyst_source"] == "llm"
    assert payload["hedged"] is True
    assert payload["schema"] == "lean"
    assert "ttfa_confirm_ms" in payload
    assert "llm_ttft_ms" in payload


def test_slow_first_call_is_hedged(blueprint, monkeypatch):
    monkeypatch.setenv("ANALYST_HEDGE_AFTER_SECS", "0.15")
    slow = {
        "intent": "answer",
        "intelligibility": "clear",
        "slot_updates": [{"field": "city", "value": "Slow", "confidence": 0.9}],
    }
    fast = {
        "intent": "answer",
        "intelligibility": "clear",
        "slot_updates": [{"field": "city", "value": "Pune", "confidence": 0.9}],
    }
    client = FakeClient([slow, fast], delays=[2.0, 0.01])
    analyzer = TurnAnalyzer(blueprint, api_key="x", model="m", client=client, timeout_s=1.0)

    result = asyncio.run(analyzer.analyze("Pune", clinical=False, fallback=heuristic_analysis("Pune")))
    assert analyzer.hedged is True
    assert client.calls == 2
    assert result.slot_updates and result.slot_updates[0].value == "Pune"
    assert result.source == "llm"


def test_full_schema_keeps_nested_clinical_fields(blueprint, monkeypatch):
    monkeypatch.setenv("ANALYST_SCHEMA", "full")
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
        await analyzer.analyze("city", clinical=False, fallback=fallback)
        await analyzer.analyze("clinical", clinical=True, fallback=fallback)

    asyncio.run(go())
    assert "clinical" in client.schemas[0]["properties"]
    assert "new_claims" in client.schemas[0]["properties"]
    assert "Clinical grading" in client.systems[0]
    assert "slot_updates" not in client.schemas[1]["properties"]
    assert client.max_tokens == [900, 900]


def test_lean_schema_drops_grading_and_slots(blueprint):
    from interview.analysis import CLINICAL_LEAN_FIELDS, SCREENING_LEAN_FIELDS, build_clinical_lean_schema, build_screening_lean_schema

    screening = build_screening_lean_schema(blueprint)["properties"]
    clinical = build_clinical_lean_schema(blueprint)["properties"]
    assert set(screening) == set(SCREENING_LEAN_FIELDS)
    assert set(clinical) == set(CLINICAL_LEAN_FIELDS)
    for key in ("clinical", "quality", "covered_point_ids", "missing_point_ids", "red_flags", "needs_clarification"):
        assert key not in screening
    assert "slot_updates" not in clinical
    assert "care_updates" not in clinical


def test_lean_fields_keep_the_same_move_kind(blueprint):
    from tests.test_flow import care, grade, make_flow, reach_care, reach_clinical, say

    def kind(analysis, prep):
        flow, _ = make_flow(blueprint)
        prep(flow)
        return flow.apply(analysis).kind

    def opened(flow):
        flow.opening()

    city_full = say(("city", "Pune"), gist_en="from Pune", aside="the room is cold", new_claims=["lives in Pune"])
    assert kind(city_full, opened) == kind(say(("city", "Pune")), opened)

    def at_care(flow):
        reach_care(flow)

    refused = care("diaper_care", "refuses", "not comfortable")
    refused.gist_en = "will not do diaper care"
    refused.new_claims = ["refused diaper care"]
    assert kind(refused, at_care) == kind(care("diaper_care", "refuses", "not comfortable"), at_care)

    def at_clinical(flow):
        reach_clinical(flow, experience=("1", "ward"))

    full_grade = grade("partial", covered=["a"], missing=["b"])
    full_grade.gist_en = "checked the pulse"
    full_grade.new_claims = ["checks pulse"]
    lean_grade = grade("partial", covered=["a"], missing=["b"])
    assert lean_grade.clinical is not None and full_grade.clinical is not None
    lean_grade.clinical.quote = ""
    lean_grade.clinical.summary_en = ""
    assert kind(full_grade, at_clinical) == kind(lean_grade, at_clinical)


def test_previous_turn_enrichment_still_picks_contradiction_and_resume(blueprint):
    from tests.test_flow import grade, make_flow, reach_clinical, say

    clinical, _ = make_flow(blueprint)
    reach_clinical(clinical, experience=("1", "ward"))
    clinical.state.claims.append("3 years in ICU")
    clinical.note_enrichment(
        {
            "new_claims": [],
            "contradictions": [
                {"claim_a": "3 years in ICU", "claim_b": "never worked in ICU", "note": "conflict"}
            ],
            "gist_en": "",
            "aside": "",
            "resume_mismatch": "",
            "quote": "",
            "summary_en": "",
        }
    )
    probed = clinical.apply(grade("partial", covered=["x"], missing=["y"]))
    assert probed.kind == "probe_contradiction"

    bare, _ = make_flow(blueprint)
    reach_clinical(bare, experience=("1", "ward"))
    bare.state.claims.append("3 years in ICU")
    assert bare.apply(grade("partial", covered=["x"], missing=["y"])).kind != "probe_contradiction"

    resume, _ = make_flow(blueprint, resume="Staff nurse, 3 years ICU, Apollo Hospital Pune")
    resume.opening()
    resume.note_enrichment(
        {
            "new_claims": [],
            "contradictions": [],
            "gist_en": "",
            "aside": "",
            "resume_mismatch": "resume says 3 years ICU at Apollo; they said 1 year on a ward",
            "quote": "",
            "summary_en": "",
        }
    )
    checked = resume.apply(say(("experience_years", "1"), ("experience_settings", "ward")))
    assert checked.kind == "resume_check"


def test_stale_enrich_is_skipped_and_fresh_enrich_still_applies(blueprint):
    from tests.test_flow import grade, make_flow, reach_clinical, say

    contra = {
        "new_claims": [],
        "contradictions": [
            {"claim_a": "3 years in ICU", "claim_b": "never worked in ICU", "note": "conflict"}
        ],
        "gist_en": "",
        "aside": "",
        "resume_mismatch": "",
        "quote": "",
        "summary_en": "",
    }
    stale, _ = make_flow(blueprint)
    reach_clinical(stale, experience=("3", "ICU"))
    stale.state.claims.append("3 years in ICU")
    snap = stale.enrich_snapshot()
    stale.note_enrichment(contra, snapshot=snap)
    stale.state.slot("experience_years").value = "1"
    assert stale.apply(grade("partial", covered=["x"], missing=["y"])).kind != "probe_contradiction"

    fresh, _ = make_flow(blueprint)
    reach_clinical(fresh, experience=("3", "ICU"))
    fresh.state.claims.append("3 years in ICU")
    fresh.note_enrichment(contra, snapshot=fresh.enrich_snapshot())
    assert fresh.apply(grade("partial", covered=["x"], missing=["y"])).kind == "probe_contradiction"

    mismatch = {
        "new_claims": [],
        "contradictions": [],
        "gist_en": "",
        "aside": "",
        "resume_mismatch": "resume says 3 years ICU; they said 1 year on a ward",
        "quote": "",
        "summary_en": "",
    }
    resume_stale, _ = make_flow(blueprint, resume="Staff nurse, 3 years ICU, Apollo Hospital Pune")
    resume_stale.opening()
    resume_stale.state.slot("experience_years").value = "1"
    resume_stale.note_enrichment(mismatch, snapshot=resume_stale.enrich_snapshot())
    resume_stale.state.slot("experience_years").value = "5"
    assert (
        resume_stale.apply(say(("experience_years", "1"), ("experience_settings", "ward"))).kind
        != "resume_check"
    )

    resume_fresh, _ = make_flow(blueprint, resume="Staff nurse, 3 years ICU, Apollo Hospital Pune")
    resume_fresh.opening()
    resume_fresh.state.slot("experience_years").value = "1"
    resume_fresh.note_enrichment(mismatch, snapshot=resume_fresh.enrich_snapshot())
    assert (
        resume_fresh.apply(say(("experience_years", "1"), ("experience_settings", "ward"))).kind
        == "resume_check"
    )


def test_enrich_is_scheduled_after_the_move(blueprint):
    enrich = {
        "new_claims": ["lives in Pune"],
        "contradictions": [],
        "gist_en": "from Pune",
        "aside": "",
        "resume_mismatch": "",
        "quote": "",
        "summary_en": "",
    }
    client = FakeClient([CITY, enrich, CITY])
    director, flow = build(blueprint, client)
    flow.opening()

    async def go():
        await director.decide("Pune")
        if director._enrich_tasks:
            await asyncio.gather(*director._enrich_tasks)
        await director.decide("Pune and Baner")

    asyncio.run(go())
    assert "lives in Pune" in flow.state.claims
    assert "new_claims" in client.schemas[1]["properties"]
    assert "slot_updates" not in client.schemas[1]["properties"]
    assert "clinical" not in client.schemas[0]["properties"]


def test_verbatim_cache_plays_static_lines_and_misses_dynamic_ones(caplog):
    import logging

    from interview.flow import CROWD_HELP_LINES, SALARY_HOLDOUT_LINES
    from interview.phone_speech import phone_again_line, phone_ask_line, phone_confirm_line, phone_invalid_line
    from interview.verbatim_cache import VerbatimCache, static_verbatim_lines

    class _Stream:
        def __init__(self) -> None:
            self._done = False

        def push_text(self, text: str) -> None:
            self.text = text

        def end_input(self) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return SimpleNamespace(frame=b"audio")

    class _TTS:
        def stream(self):
            return _Stream()

    lines = static_verbatim_lines("en-IN")
    assert phone_ask_line("en-IN") in lines
    assert phone_again_line("en-IN") in lines
    assert SALARY_HOLDOUT_LINES["en-IN"] in lines
    assert CROWD_HELP_LINES["en-IN"] in lines
    assert phone_invalid_line("en-IN", "98765") not in lines
    assert phone_confirm_line("en-IN", "98765 43210") not in lines
    assert "{" not in "".join(lines)

    cache = VerbatimCache(_TTS())

    async def render():
        cache.prepare("en-IN")
        await cache._tasks["en-IN"]

    asyncio.run(render())
    with caplog.at_level(logging.INFO, logger="interview-agent"):
        hit = cache.lookup(phone_ask_line("en-IN"), language="en-IN")
        miss = cache.lookup(phone_confirm_line("en-IN", "98 76"), language="en-IN")
    assert hit == [b"audio"]
    assert miss is None
    assert any("verbatim cache hit" in rec.message for rec in caplog.records)
    assert any("verbatim cache miss" in rec.message for rec in caplog.records)


def test_screening_analyst_model_stays_mini_until_set(monkeypatch):
    from config import get_settings

    monkeypatch.delenv("SCREENING_ANALYST_MODEL", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().screening_analyst_model == "gpt-4o-mini"
        monkeypatch.setenv("SCREENING_ANALYST_MODEL", "gpt-4.1-mini")
        get_settings.cache_clear()
        assert get_settings().screening_analyst_model == "gpt-4.1-mini"
    finally:
        get_settings.cache_clear()


def test_analyst_eval_fixture_has_labeled_rows():
    from pathlib import Path

    path = Path(__file__).resolve().parent / "fixtures" / "analyst_eval.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 30
    languages = {row["language"] for row in rows}
    assert {"hi-IN", "mr-IN", "ta-IN"} <= languages
    assert any(row["id"] == "phone_digit_groups" for row in rows)
    assert any(row["id"] == "garbled_heuristic" for row in rows)
    assert sum(1 for row in rows if row["stage"] == "clinical") >= 6
    stances = {row["expected_care_stance"] for row in rows}
    assert {"comfortable", "refuses", "hesitant"} <= stances
    for row in rows:
        assert row["expected_intent"]
        assert isinstance(row["expected_slot_updates"], list)
        assert "expected_care_stance" in row
        assert "expected_clinical_quality" in row
    assert any(row.get("needs_review") for row in rows)
