"""Flow policy tests: the client's scenarios, driven with hand-built analyses (no LLM, no LiveKit)."""

import json
from pathlib import Path

import pytest

from interview.analysis import (
    CareUpdate,
    ClinicalGrade,
    SlotUpdate,
    TurnAnalysis,
    heuristic_analysis,
)
from interview.blueprint import Blueprint
from interview.flow import InterviewFlow
from interview.flow_state import FlowState
from interview.plan import InterviewPlan, classify_answer

BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"


@pytest.fixture(scope="module")
def blueprint() -> Blueprint:
    return Blueprint.from_api(json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")))


def make_plan(resume: str = "") -> InterviewPlan:
    return InterviewPlan(
        interview_id="t1",
        language="hi-IN",
        stt_mode="codemix",
        target_minutes=20,
        company_name="Kreeda Labs",
        interviewer_name="Aven",
        role_title="Staff Nurse",
        criteria=[],
        keyterms=[],
        glossary_hints=[],
        steps=[],
        system_prompt="",
        candidate_name="Priya",
        resume_text=resume,
    )


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make_flow(blueprint, state=None, resume=""):
    clock = Clock()
    return InterviewFlow(make_plan(resume), blueprint, state, clock=clock), clock


def say(*updates: tuple[str, str], **kw) -> TurnAnalysis:
    return TurnAnalysis(slot_updates=[SlotUpdate(f, v, kw.pop("conf", 0.9), "") for f, v in updates], **kw)


def care(item: str, stance: str, reason: str = "") -> TurnAnalysis:
    return TurnAnalysis(care_updates=[CareUpdate(item, stance, reason)])


def grade(quality: str, covered=(), missing=(), red_flags=(), **kw) -> TurnAnalysis:
    return TurnAnalysis(
        clinical=ClinicalGrade(
            area_id="x", quality=quality, covered=list(covered), missing=list(missing), red_flags=list(red_flags), quote="q", summary_en="s"
        ),
        **kw,
    )


def fill_screening(flow: InterviewFlow) -> None:
    """Walk the whole screening happy path up to (and including) the care cluster question."""
    flow.opening()
    flow.apply(say(("city", "Pune")))
    flow.apply(say(("phone", "98765 43210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    flow.apply(say(("height_cm", "5 feet 4 inches"), ("weight_kg", "58 kg")))
    flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU at a private hospital")))


# ----------------------------------------------------------------------------------------------- screening


def test_opening_greets_and_asks_the_first_screening_question(blueprint):
    flow, _ = make_flow(blueprint)
    move = flow.opening()
    assert flow.stage == "screening"
    assert "Priya" in move.directive and "city" in move.directive.lower()


def test_one_utterance_can_fill_several_fields_and_phone_is_read_back(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), ("phone", "+91 98765 43210")))
    assert flow.state.slots["city"].value == "Pune"
    assert flow.state.slots["phone"].value == "9876543210"
    assert move.kind == "confirm" and "98765, 43210" in move.directive


def test_misheard_phone_is_asked_again_not_stored(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    move = flow.apply(say(("phone", "98765 432")))
    assert move.kind == "reask_invalid"
    assert flow.state.slots["phone"].status == "empty"


def test_denied_readback_clears_the_number_and_asks_again(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    move = flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="denied"))
    assert flow.state.slots["phone"].status == "empty"
    assert move.kind == "ask_field" and "mobile" in move.directive.lower()


def test_low_confidence_hearing_is_read_back_even_for_plain_fields(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), conf=0.4))
    assert move.kind == "confirm" and "Pune" in move.directive


def test_height_and_weight_normalised_and_unbelievable_values_rejected(blueprint):
    flow, _ = make_flow(blueprint)
    fill_screening(flow)
    assert flow.state.slots["height_cm"].value == 163
    assert flow.state.slots["weight_kg"].value == 58

    flow2, _ = make_flow(blueprint)
    flow2.opening()
    flow2.apply(say(("city", "Pune"), ("height_cm", "400")))
    assert flow2.state.slots["height_cm"].status == "empty"


def test_candidate_who_does_not_know_their_weight_is_not_pestered(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    flow.apply(say(("height_cm", "160")))  # weight missing -> asked on its own
    assert flow.state.focus["ids"] == ["weight_kg"]
    flow.apply(TurnAnalysis(intent="dont_know"))
    assert flow.state.slots["weight_kg"].status == "unknown"
    assert flow.state.focus.get("ids") != ["weight_kg"]


def test_fresher_is_recorded_as_such(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("experience_years", "0")))
    assert flow.state.experience_level == "fresher"


# ------------------------------------------------------------------------------------- diaper care gate


def reach_care(flow):
    fill_screening(flow)
    assert flow.state.focus["type"] == "care"


def test_care_cluster_is_asked_after_all_details(blueprint):
    flow, _ = make_flow(blueprint)
    fill_screening(flow)
    assert flow.state.care_intro_done and flow.stage == "screening"


def test_refusing_diaper_care_is_persuaded_twice_then_the_candidate_stops_there(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)

    m1 = flow.apply(care("diaper_care", "refuses", "not comfortable"))
    assert m1.kind == "persuade" and "essential" in m1.directive.lower()
    assert flow.stage == "screening"

    m2 = flow.apply(care("diaper_care", "refuses", "still no"))
    assert m2.kind == "persuade" and m2.directive != m1.directive

    m3 = flow.apply(care("diaper_care", "refuses", "no"))
    assert m3.completed and m3.end_session and m3.kind == "gate_failed"
    assert flow.state.gate_failed == "diaper_care"
    assert flow.state.outcome == "screened_out"
    assert flow.stage == "ended"
    assert not any(p.status != "pending" for p in flow.state.areas.values())  # never reached clinical
    assert any(e[0] == "gate.failed" for e in m3.events)


def test_persuasion_that_works_lets_the_candidate_continue_to_clinical(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    flow.apply(care("diaper_care", "hesitant", "never done it"))
    move = flow.apply(care("diaper_care", "willing_with_training"))
    assert flow.stage == "clinical" or move.kind in ("ask_care_item", "clinical_question")
    assert flow.state.gate_failed is None


def test_comfortable_with_everything_goes_straight_to_clinical(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    move = flow.apply(
        TurnAnalysis(
            care_updates=[CareUpdate(c.id, "comfortable") for c in blueprint.care_items],
        )
    )
    assert flow.stage == "clinical" and move.kind == "clinical_question"


def test_discomfort_with_a_non_essential_item_is_recorded_but_does_not_gate(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    flow.apply(
        TurnAnalysis(
            care_updates=[
                CareUpdate("diaper_care", "comfortable"),
                CareUpdate("hygiene_bathing", "comfortable"),
                CareUpdate("toileting_bedpan", "hesitant", "squeamish"),
                CareUpdate("lifting_repositioning", "comfortable"),
            ]
        )
    )
    assert flow.stage == "clinical"
    assert flow.state.care["toileting_bedpan"].stance == "hesitant"
    assert flow.state.gate_failed is None


def test_evasive_answers_about_diaper_care_count_as_hesitation(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    flow.apply(TurnAnalysis(care_updates=[CareUpdate(c.id, "comfortable") for c in blueprint.care_items if not c.gate]))
    moves = [flow.apply(TurnAnalysis()) for _ in range(6)]
    assert any(m.kind == "persuade" for m in moves)


def test_diaper_refusal_intent_without_care_updates_still_persuades_twice(blueprint):
    """Plain no/idk with no care_updates must still hit the diaper gate, not skip past it."""
    flow, _ = make_flow(blueprint)
    reach_care(flow)

    m1 = flow.apply(TurnAnalysis(intent="refusal"))
    assert m1.kind == "persuade"
    assert flow.state.care["diaper_care"].stance == "refuses"
    assert flow.state.care["diaper_care"].persuasions == 1

    m2 = flow.apply(TurnAnalysis(intent="dont_know"))
    assert m2.kind == "persuade"
    assert flow.state.care["diaper_care"].persuasions == 2

    m3 = flow.apply(TurnAnalysis(intent="refusal"))
    assert m3.kind == "gate_failed" and m3.end_session
    assert flow.state.gate_failed == "diaper_care"


def test_diaper_clear_yes_after_hesitation_is_recovered_without_llm_care_updates(blueprint):
    """Regression: 'हाँ शॉर्ट में कर सकता हूँ' / 'ready' must clear hesitant even if care_updates is empty."""
    from interview.analysis import recover_care_updates

    flow, _ = make_flow(blueprint)
    reach_care(flow)
    m1 = flow.apply(care("diaper_care", "hesitant", "never done it"))
    assert m1.kind == "persuade"
    assert flow.state.care["diaper_care"].persuasions == 1

    recovered = recover_care_updates(
        TurnAnalysis(intent="answer"),
        text="हाँ शॉर्ट में कर सकता हूँ।",
        item_ids=["diaper_care"],
    )
    assert recovered.care_updates and recovered.care_updates[0].stance == "comfortable"
    move = flow.apply(recovered)
    assert flow.state.care["diaper_care"].stance == "comfortable"
    assert flow.state.gate_failed is None
    assert move.kind != "gate_failed"
    assert move.kind != "persuade"


def test_infer_care_accept_ready_phrases():
    from interview.analysis import infer_care_accept

    assert infer_care_accept("हाँ हाँ मैं ready हूँ।") == "comfortable"
    assert infer_care_accept("हाँ मैं ready हूँ। डायपर चेंज करना") == "comfortable"
    assert infer_care_accept("I can do it with training") == "willing_with_training"
    assert infer_care_accept("मैं ये काम नहीं करूँगा") == "refuses"
    assert infer_care_accept("I won't do diaper care") == "refuses"
    assert infer_care_accept("Actually मैंने कभी किया नहीं है क्या ये ज़रूरी है") is None


def test_diaper_idk_on_care_intro_persuades_before_skipping(blueprint):
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    m1 = flow.apply(TurnAnalysis(intent="dont_know"))
    assert m1.kind == "persuade"
    assert flow.state.care["diaper_care"].stance == "hesitant"


# ----------------------------------------------------------------------------------------------- clinical


def reach_clinical(flow, experience=("3", "ICU at a private hospital")):
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    flow.apply(say(("height_cm", "160"), ("weight_kg", "55")))
    flow.apply(say(("experience_years", experience[0]), ("experience_settings", experience[1])))
    flow.apply(TurnAnalysis(care_updates=[CareUpdate(c.id, "comfortable") for c in blueprint_items(flow)]))
    assert flow.stage == "clinical"


def blueprint_items(flow):
    return flow.bp.care_items


def test_icu_candidate_gets_icu_content_and_non_icu_does_not(blueprint):
    icu, _ = make_flow(blueprint)
    reach_clinical(icu)
    assert "critical_care" in icu.state.area_order

    ward, _ = make_flow(blueprint)
    reach_clinical(ward, experience=("2", "general ward in a clinic"))
    assert "critical_care" not in ward.state.area_order
    assert {"medication_safety", "emergency_response"} <= set(ward.state.area_order)


def test_experienced_candidates_start_harder_than_freshers(blueprint):
    exp, _ = make_flow(blueprint)
    reach_clinical(exp, experience=("6", "ward"))
    fresher, _ = make_flow(blueprint)
    reach_clinical(fresher, experience=("0", "internship"))
    assert exp.state.areas[exp.state.current_area].level == 2
    assert fresher.state.areas[fresher.state.current_area].level == 1


def test_partial_answer_is_probed_then_the_flow_moves_on(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    first = flow.state.current_area
    m1 = flow.apply(grade("partial", covered=["x"], missing=["y"]))
    m2 = flow.apply(grade("partial", covered=["x"], missing=["y"]))
    assert (m1.kind, m2.kind) == ("probe", "probe")
    m3 = flow.apply(grade("partial", covered=["x"], missing=["y"]))
    assert m3.kind == "clinical_question"
    assert flow.state.areas[first].status == "done"
    assert flow.state.current_area != first


def test_probe_directive_never_leaks_the_answer_as_a_statement(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    move = flow.apply(grade("partial", covered=[], missing=[]))
    assert "never say them" in move.directive and "without telling them the answer" in move.directive


def test_strong_first_answer_deepens_once_then_moves_on(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("0", "internship"))
    first = flow.state.current_area
    m1 = flow.apply(grade("correct"))
    assert m1.kind == "deepen" and flow.state.areas[first].level == 2
    m2 = flow.apply(grade("correct"))
    assert m2.kind == "clinical_question"
    assert flow.state.areas[first].outcome == "adequate" or flow.state.areas[first].outcome == "strong"


def test_wrong_answer_is_challenged_not_corrected(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    move = flow.apply(grade("incorrect", red_flags=["would not start CPR"]))
    assert move.kind == "challenge"
    assert "Do not give the correct answer" in move.directive
    again = flow.apply(grade("incorrect", red_flags=["would not start CPR"]))
    assert again.kind == "probe_simpler"  # exactly one easier retry, then we stop pressing
    last = flow.apply(grade("incorrect", red_flags=["would not start CPR"]))
    first_area = flow.state.area_order[0]
    assert flow.state.areas[first_area].outcome == "unsafe"
    assert last.kind in ("clinical_question", "wrap_up")


def test_dont_know_moves_on_immediately(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("6", "ward"))
    first = flow.state.current_area
    m1 = flow.apply(TurnAnalysis(intent="dont_know"))
    assert flow.state.areas[first].outcome == "unknown"
    assert m1.kind == "clinical_question"
    assert "scaffold" not in m1.kind


def test_too_many_dont_knows_ends_the_clinical_round_gracefully(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    moves = [flow.apply(TurnAnalysis(intent="dont_know")) for _ in range(6)]
    assert any(m.kind == "wrap_up" for m in moves)
    assert flow.state.dont_know_total >= blueprint.limits.max_dont_know_total


def test_vague_answer_is_clarified_once(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    move = flow.apply(grade("partial", needs_clarification=True) if False else TurnAnalysis(clinical=ClinicalGrade(quality="partial", needs_clarification=True)))
    assert move.kind == "clarify"


def test_contradiction_is_probed_and_the_clinical_decision_resumes_after(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    area = flow.state.current_area
    a = grade("partial", covered=["x"], missing=["y"])
    a.contradictions = [{"claim_a": "3 years in ICU", "claim_b": "never worked in ICU", "note": "conflict"}]
    move = flow.apply(a)
    assert move.kind == "probe_contradiction" and "3 years in ICU" in move.directive
    assert flow.state.areas[area].probes == 0  # decision deferred, not consumed
    resumed = flow.apply(TurnAnalysis(gist_en="It was an internship, not a job"))
    assert resumed.kind == "probe"
    assert flow.state.contradictions[0]["resolved"]


def test_contradiction_together_with_dont_know_is_not_lost(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("6", "ward"))
    area = flow.state.current_area
    a = TurnAnalysis(
        intent="dont_know",
        contradictions=[{"claim_a": "3 years ICU", "claim_b": "never in ICU", "note": "n"}],
    )
    assert flow.apply(a).kind == "probe_contradiction"
    assert flow.state.areas[area].dont_knows == 0
    resumed = flow.apply(TurnAnalysis(gist_en="was ward only", intent="dont_know"))
    assert flow.state.areas[area].dont_knows == 1
    assert flow.state.areas[area].outcome == "unknown"
    assert resumed.kind == "clinical_question"


def test_contradiction_probes_are_capped(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    kinds = []
    for i in range(6):
        a = grade("partial", missing=["y"])
        a.contradictions = [{"claim_a": f"a{i}", "claim_b": f"b{i}", "note": "n"}]
        kinds.append(flow.apply(a).kind)
    assert kinds.count("probe_contradiction") <= blueprint.limits.max_contradiction_probes


# ----------------------------------------------------------------------------------- candidate behaviour


def test_unclear_audio_asks_to_repeat_then_offers_noise_help_and_recovers(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    bad = TurnAnalysis(intelligibility="unclear")
    kinds = [flow.apply(bad).kind for _ in range(3)]
    assert kinds == ["ask_repeat", "ask_repeat", "noise_help"]
    assert flow.state.unclear_total == 3
    flow.apply(say(("city", "Pune")))
    assert flow.state.unclear_streak == 0
    assert flow.state.slots["city"].value == "Pune"  # unclear turns never stored garbage


def test_unclear_turns_do_not_advance_or_penalise_clinical_progress(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    area = flow.state.current_area
    flow.apply(TurnAnalysis(intelligibility="unclear"))
    assert flow.state.areas[area].probes == 0 and not flow.state.areas[area].evidence


@pytest.mark.parametrize(
    ("intent", "kind"),
    [("repeat_request", "repeat"), ("rephrase_request", "rephrase"), ("off_topic", "redirect"), ("candidate_question", "answer_question")],
)
def test_requests_and_questions_do_not_advance_the_interview(blueprint, intent, kind):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    area, level = flow.state.current_area, flow.state.areas[flow.state.current_area].level
    move = flow.apply(TurnAnalysis(intent=intent))
    assert move.kind == kind
    assert flow.state.current_area == area and flow.state.areas[area].level == level
    assert flow.state.areas[area].probes == 0


def test_answers_to_candidate_questions_come_from_the_faq_only(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(TurnAnalysis(intent="candidate_question"))
    assert "recruitment team" in move.directive and "Never invent" in move.directive


def test_nervous_candidate_gets_reassurance_first(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), nervous=True))
    assert move.directive.startswith("The candidate sounds nervous")
    assert flow.state.nervous_events == 1


def test_wanting_to_stop_is_confirmed_before_ending(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    first = flow.apply(TurnAnalysis(intent="wants_to_stop"))
    assert first.kind == "confirm_stop" and not first.completed
    second = flow.apply(TurnAnalysis(intent="wants_to_stop"))
    assert second.completed and flow.state.outcome == "withdrew"


def test_long_silence_escalates_then_ends_as_incomplete(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    kinds = [flow.silence(level).kind for level in (1, 2, 3, 4)]
    assert kinds == ["silence_nudge", "silence_rephrase", "silence_check", "silence_end"]
    assert flow.state.outcome == "incomplete_silence"


# ------------------------------------------------------------------------------------ closing and limits


def test_closing_offers_questions_then_says_goodbye(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    for _ in range(40):
        if flow.stage != "clinical":
            break
        flow.apply(grade("partial", missing=["y"]))
    assert flow.stage == "closing"
    answer = flow.apply(TurnAnalysis(intent="candidate_question"))
    assert answer.kind == "closing_answer" and not answer.completed
    bye = flow.apply(TurnAnalysis())
    assert bye.completed and bye.end_session and flow.state.outcome == "completed"


def test_clinical_round_stops_after_the_target_number_of_areas(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    for _ in range(60):
        if flow.stage != "clinical":
            break
        flow.apply(grade("correct"))
    done = [a for a in flow.state.areas.values() if a.status == "done"]
    assert len(done) == blueprint.limits.clinical_areas_target


def test_hard_time_cap_ends_the_interview(blueprint):
    flow, clock = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    clock.t = blueprint.limits.hard_cap_minutes * 60 + 1
    move = flow.apply(grade("partial", missing=["y"]))
    assert move.completed and flow.state.outcome == "time"


def test_running_over_the_clinical_budget_stops_deepening_and_probing(blueprint):
    flow, clock = make_flow(blueprint)
    reach_clinical(flow, experience=("0", "internship"))
    clock.t = (blueprint.limits.clinical_target_minutes + 3) * 60
    move = flow.apply(grade("correct"))
    assert move.kind != "deepen"


# ------------------------------------------------------------------------------------ persistence/resume


def test_state_round_trips_through_json_and_a_new_flow_continues_the_same_interview(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    flow.apply(grade("partial", covered=["a"], missing=["b"]))
    saved = json.loads(json.dumps(flow.state.to_dict()))

    restored, _ = make_flow(blueprint, FlowState.from_dict(saved))
    assert restored.state.to_dict() == flow.state.to_dict()
    assert restored.stage == "clinical"
    assert restored.state.slots["phone"].status == "confirmed"
    move = restored.opening()  # an agent restart calls opening(); it must resume, not re-greet
    assert move.kind == "resume" and restored.state.interruptions == 1
    assert "Priya" not in move.directive


def test_unknown_keys_in_saved_state_are_ignored(blueprint):
    state = FlowState.from_dict({"stage": "clinical", "future_field": 1, "slots": {"city": {"value": "X", "extra": 1}}})
    assert state.stage == "clinical" and state.slots["city"].value == "X"


# ----------------------------------------------------------------------------------- analysis plumbing


def test_analysis_parser_tolerates_garbage_and_drops_unknown_enums():
    a = TurnAnalysis.from_dict(
        {
            "intent": "banana",
            "intelligibility": None,
            "slot_updates": [{"field": "city", "value": "Pune"}, {"field": "", "value": "x"}, {"field": "phone", "value": " "}],
            "care_updates": [{"item": "diaper_care", "stance": "maybe"}],
            "clinical": {"quality": "correct", "covered_point_ids": ["a"]},
            "contradictions": [{"claim_a": "x"}],
        }
    )
    assert a.intent == "answer" and a.intelligibility == "clear"
    assert [u.field for u in a.slot_updates] == ["city"]
    assert a.care_updates == [] and a.contradictions == []
    assert a.clinical is not None and a.clinical.covered == ["a"]


def test_clinical_quality_none_means_no_clinical_attempt():
    assert TurnAnalysis.from_dict({"clinical": {"quality": "none"}}).clinical is None


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("pata nahi", "dont_know"),
        ("idk", "dont_know"),
        ("dunno", "dont_know"),
        ("मला माहित नाही", "dont_know"),
        ("मुझे नहीं पता", "dont_know"),
        ("can you repeat that please", "repeat_request"),
        ("समझ नहीं आया", "rephrase_request"),
        ("hmm", "filler_only"),
        ("I worked in the ICU for three years", "answer"),
    ],
)
def test_heuristic_fallback_understands_the_basics_in_several_languages(text, intent):
    assert heuristic_analysis(text).intent == intent


def test_heuristic_fallback_reads_confirmation_and_phone():
    assert heuristic_analysis("haan sahi hai", pending_field="phone", pending_value="9876543210").confirmation == "confirmed"
    assert heuristic_analysis("nahi galat hai", pending_field="phone", pending_value="9876543210").confirmation == "denied"
    assert heuristic_analysis("my number is 98765 43210").slot_updates[0].value == "9876543210"


def test_analysis_payload_carries_the_rubric_only_for_the_current_question(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    payload = json.loads(flow.analysis_payload("answer text", "question text", []))
    assert payload["stage"] == "clinical"
    ctx = payload["clinical_context"]
    assert ctx["area_id"] == flow.state.current_area and ctx["key_points"] and "level" in ctx
    assert payload["fields_being_collected"] == []


def test_classify_noise():
    assert classify_answer("") == "noise"
    assert classify_answer("((noise))") == "noise"
    assert classify_answer("um") == "weak"
    assert classify_answer("I worked three years in the ICU ward handling night shifts") == "substantive"
