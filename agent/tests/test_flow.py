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


def make_plan(resume: str = "", language: str = "hi-IN") -> InterviewPlan:
    return InterviewPlan(
        interview_id="t1",
        language=language,
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


def make_flow(blueprint, state=None, resume="", language: str = "hi-IN"):
    clock = Clock()
    return InterviewFlow(make_plan(resume, language=language), blueprint, state, clock=clock), clock


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
    dive = flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU at a private hospital")))
    assert dive.kind == "experience_dive"
    flow.apply(TurnAnalysis(intent="answer", gist_en="Monitoring, meds, and ventilator care in ICU"))


# ----------------------------------------------------------------------------------------------- screening


def test_opening_greets_and_asks_the_first_screening_question(blueprint):
    flow, _ = make_flow(blueprint)
    move = flow.opening()
    assert flow.stage == "screening"
    assert "Priya" in move.directive and "city" in move.directive.lower()


def test_opening_gujarati_uses_gujarati_script_and_no_hindi(blueprint):
    flow, _ = make_flow(blueprint, language="gu-IN")
    move = flow.opening()
    assert flow.stage == "screening"
    assert "નમસ્તે" in move.directive
    assert "Gujarati" in move.directive
    assert "Hindi/English/mix is fine" not in move.directive
    assert "नमस्ते" not in move.directive


def test_short_answers_ready_by_focus_not_fixed_length(blueprint):
    """One-word replies are valid when the live question expects a short fact / yes-no."""
    flow, _ = make_flow(blueprint)
    flow.opening()
    assert flow.expects_short_answer()
    assert flow.state.focus.get("type") == "slots"
    assert "slots" in flow.focus_lock_summary() and "city" in flow.focus_lock_summary()
    assert flow.utterance_ready_for_focus("PUNE")
    assert flow.utterance_ready_for_focus("Goa")
    assert flow.utterance_ready_for_focus("ने और मुंबई")
    assert not flow.utterance_ready_for_focus("um")
    assert not flow.utterance_ready_for_focus("")
    assert not flow.utterance_ready_for_focus("\ufffd")

    flow.apply(say(("city", "Pune")))
    assert flow.state.focus.get("type") == "slots"
    # Phone must not fire on the first digit-word — wait for a fuller number.
    assert "phone" in (flow.focus_lock_summary() or "")
    assert not flow.utterance_ready_for_focus("nine")
    assert not flow.utterance_ready_for_focus("nine double one")
    assert flow.utterance_ready_for_focus("saade paach she")
    assert flow.utterance_ready_for_focus("nine double one two three two three five four nine")

    flow.apply(say(("phone", "9876543210")))
    assert flow.state.focus.get("type") == "confirm"
    assert flow.expects_short_answer()
    assert "confirm" in flow.focus_lock_summary()
    assert flow.utterance_ready_for_focus("haan")
    assert flow.utterance_ready_for_focus("yes")
    assert flow.utterance_ready_for_focus("nahi")

    fill_screening(flow)
    # After screening, clinical questions should not treat filler as ready.
    if flow.state.focus.get("type") == "clinical":
        assert not flow.expects_short_answer()
        assert "clinical" in flow.focus_lock_summary()
        assert not flow.utterance_ready_for_focus("ok")
        assert flow.utterance_ready_for_focus(
            "I check vitals every hour and escalate if BP drops suddenly"
        )


def test_two_digit_phone_groups_are_read_back(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    move = flow.apply(TurnAnalysis(intent="answer", raw_utterance="89, 75, 34, 67, 90"))
    assert flow.state.slots["phone"].value == "8975346790"
    assert move.kind == "confirm"
    assert "8, 9, 7, 5, 3, 4, 6, 7, 9, 0" in move.directive


def test_a_wording_is_stored_from_the_hearing(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.focus = {"type": "slots", "ids": ["phone"]}
    move = flow.apply(TurnAnalysis(intent="answer", raw_utterance="saade paach she", phone_hint="550"))
    assert flow.state.slots["phone"].value == "550"
    assert move.kind == "confirm"
    assert "5, 5, 0" in move.directive
    flow2, _ = make_flow(blueprint)
    flow2.opening()
    flow2.state.focus = {"type": "slots", "ids": ["phone"]}
    flow2.apply(TurnAnalysis(intent="answer", raw_utterance="साडे पाचशे", phone_hint="550"))
    assert flow2.state.slots["phone"].value == "550"


def test_a_short_phrase_is_not_completed_into_a_mobile(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.focus = {"type": "slots", "ids": ["phone"]}
    move = flow.apply(TurnAnalysis(intent="answer", raw_utterance="the number I said", phone_hint="8975346790"))
    assert flow.state.slots["phone"].status == "empty"
    assert move.kind == "ask_repeat"


def test_digits_are_not_replaced_by_a_hearing(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.focus = {"type": "slots", "ids": ["phone"]}
    flow.apply(TurnAnalysis(intent="answer", raw_utterance="89, 75, 34, 67, 90", phone_hint="1111111111"))
    assert flow.state.slots["phone"].value == "8975346790"


def test_weight_and_height_from_one_answer(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.stage = "screening"
    flow.state.focus = {"type": "slots", "ids": ["height_cm", "weight_kg"]}
    flow.apply(TurnAnalysis(intent="answer", raw_utterance="weight 50 kg and height 144 cm"))
    assert flow.state.slots["weight_kg"].value == 50
    assert flow.state.slots["height_cm"].value == 144
    flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="वजन पचास किलो है और कद एक सौ चौवालीस सेंटीमीटर है",
        )
    )
    assert flow.state.slots["weight_kg"].value == 50
    assert flow.state.slots["height_cm"].value == 144


def test_one_utterance_can_fill_several_fields_and_phone_is_read_back(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), ("phone", "+91 98765 43210")))
    assert flow.state.slots["city"].value == "Pune"
    assert flow.state.slots["phone"].value == "9876543210"
    assert move.kind == "confirm" and "9, 8, 7, 6, 5, 4, 3, 2, 1, 0" in move.directive


def test_short_phone_is_read_back_then_rejected_after_they_agree(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    move = flow.apply(say(("phone", "98765 432")))
    assert move.kind == "confirm"
    assert flow.state.slots["phone"].value == "98765432"
    move = flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed", raw_utterance="yes"))
    assert move.kind == "reask_invalid"
    assert "9, 8, 7, 6, 5, 4, 3, 2" in move.directive
    assert "not a complete mobile" in move.directive
    assert flow.state.slots["phone"].status == "empty"
    assert "only for the recruitment" not in move.directive.lower()


def test_mixed_language_phone_groups_are_caught(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="nine एक 1 two तीन 2 chappan baawan",
            phone_hint="9112325652",
            slot_updates=[SlotUpdate("phone", "91", 0.4)],
        )
    )
    assert flow.state.slots["phone"].value == "9112325652"
    assert move.kind == "confirm"
    assert "9, 1, 1, 2, 3, 2, 5, 6, 5, 2" in move.directive


def test_a_fragment_on_readback_asks_for_the_full_number(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9112323549")))
    move = flow.apply(
        TurnAnalysis(
            confirmation_field="phone",
            confirmation="denied",
            raw_utterance="3550 hai, 3549 nahi",
        )
    )
    assert flow.state.slots["phone"].status == "empty"
    assert move.kind == "ask_field"
    assert "mobile" in move.directive.lower()


def test_a_full_restatement_replaces_the_number(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9112323549")))
    move = flow.apply(
        TurnAnalysis(
            confirmation_field="phone",
            confirmation="denied",
            raw_utterance="9112323550",
        )
    )
    assert flow.state.slots["phone"].value == "9112323550"
    assert move.kind == "confirm"
    assert "9, 1, 1, 2, 3, 2, 3, 5, 5, 0" in move.directive


def test_repeating_the_same_grouped_number_confirms_once_then_moves_on(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    said = "911, 23, 23, 5, 4, 9."
    first = flow.apply(TurnAnalysis(intent="answer", raw_utterance=said, slot_updates=[]))
    assert first.kind == "confirm"
    assert flow.state.slots["phone"].value == "9112323549"
    assert "9, 1, 1, 2, 3, 2, 3, 5, 4, 9" in first.directive
    second = flow.apply(TurnAnalysis(intent="answer", raw_utterance=said, slot_updates=[]))
    assert flow.state.slots["phone"].status == "confirmed"
    assert second.kind == "ask_field"
    assert "qualification" in second.directive.lower()


def test_same_digits_after_no_are_accepted(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9112323549")))
    move = flow.apply(
        TurnAnalysis(
            confirmation_field="phone",
            confirmation="denied",
            raw_utterance="nahi, number hai 9112323549",
        )
    )
    assert flow.state.slots["phone"].value == "9112323549"
    assert flow.state.slots["phone"].status == "confirmed"
    assert move.kind == "ask_field"
    assert "qualification" in move.directive.lower()


def test_city_tail_does_not_pretend_the_number_was_missed(blueprint):
    """The rest of the city answer must not be scored as a failed first ask for the mobile number."""
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="पुणे, पुणे और बैंगलोर, ब",
            slot_updates=[SlotUpdate("city", "पुणे", 0.9)],
        )
    )
    assert move.kind == "ask_field"
    assert flow.state.slots["phone"].attempts == 1
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="पुणे, पुणे और बांग्लादेश।",
            slot_updates=[SlotUpdate("city", "पुणे और बांग्लादेश", 0.9)],
        )
    )
    assert "you could not hear their" not in move.directive.lower()
    assert "do not say you could not hear" in move.directive.lower()
    assert move.kind == "ask_field"
    assert "mobile number" in move.directive.lower()
    assert flow.state.slots["phone"].status == "empty"
    assert flow.state.slots["phone"].attempts == 1
    assert flow.state.slots["city"].value == "पुणे और बांग्लादेश"


def test_repeated_phone_phrase_is_read_back_and_not_skipped(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    move = flow.apply(
        TurnAnalysis(intent="answer", raw_utterance="911, 2323. 911, 2323.", slot_updates=[])
    )
    assert flow.state.slots["phone"].value == "9112323"
    assert move.kind == "confirm"
    assert "qualification" not in move.directive.lower()
    assert "9, 1, 1, 2, 3, 2, 3" in move.directive


def test_the_rest_of_a_short_number_is_read_back(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    first = flow.apply(TurnAnalysis(intent="answer", raw_utterance="911, 2323.", slot_updates=[]))
    assert first.kind == "confirm"
    assert flow.state.slots["phone"].value == "9112323"
    second = flow.apply(TurnAnalysis(intent="answer", raw_utterance="540", slot_updates=[]))
    assert flow.state.slots["phone"].value == "9112323540"
    assert second.kind == "confirm"
    assert "qualification" not in second.directive.lower()


def test_a_too_long_number_stays_on_the_phone_question(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    flow.state.slots["phone"].attempts = 3
    move = flow.apply(TurnAnalysis(intent="answer", raw_utterance="123456789012345", slot_updates=[]))
    assert move.kind == "reask_invalid"
    assert flow.state.slots["phone"].status == "empty"
    assert "qualification" not in move.directive.lower()
    assert "mobile number" in move.directive.lower()


def test_a_scrap_does_not_rewrite_the_readback(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune")))
    first = flow.apply(TurnAnalysis(intent="answer", raw_utterance="111-2323-549.", slot_updates=[]))
    assert flow.state.slots["phone"].value == "1112323549"
    assert first.verbatim == "मैंने सुना 1, 1, 1, 2, 3, 2, 3, 5, 4, 9. क्या यह सही है?"
    age = flow.apply(TurnAnalysis(intent="answer", raw_utterance="28", slot_updates=[]))
    assert flow.state.slots["phone"].value == "1112323549"
    assert flow.state.slots["phone"].status == "captured"
    assert age.kind == "confirm"
    assert "2, 8" not in (age.verbatim or "")
    flow2, _ = make_flow(blueprint)
    flow2.opening()
    flow2.apply(say(("city", "Pune"), ("phone", "1112323549")))
    move = flow2.apply(
        TurnAnalysis(
            intent="answer",
            confirmation="denied",
            raw_utterance="नहीं, नहीं, start में 911, बाकी का सही है।",
            slot_updates=[],
        )
    )
    assert flow2.state.slots["phone"].status == "empty"
    assert move.kind == "ask_field"
    assert "mobile" in move.directive.lower()


def test_garbled_city_says_it_could_not_hear_then_asks_again(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            gist_en="location",
            raw_utterance="उन्हें location.",
            slot_updates=[SlotUpdate("city", "उन्हें location.", 0.8)],
        )
    )
    assert flow.state.slots["city"].status == "empty"
    assert move.kind == "ask_repeat"
    assert "could not hear" in move.directive.lower()
    assert "which city" in move.directive.lower()
    move = flow.apply(say(("city", "Pune")))
    assert flow.state.slots["city"].value == "Pune"
    assert move.kind == "ask_field"


def test_denied_readback_clears_the_number_and_asks_again(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    move = flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="denied"))
    assert flow.state.slots["phone"].status == "empty"
    assert move.kind == "ask_field" and "mobile" in move.directive.lower()


def test_low_confidence_plain_fields_skip_confirm_only_phone_reads_back(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), conf=0.4))
    assert flow.state.slots["city"].status == "confirmed"
    assert move.kind != "confirm"
    assert "mobile" in move.directive.lower() or "phone" in move.directive.lower()


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
    from interview.analysis import infer_care_accept, recover_care_updates

    assert infer_care_accept("हाँ हाँ मैं ready हूँ।") == "comfortable"
    assert infer_care_accept("हाँ मैं ready हूँ। डायपर चेंज करना") == "comfortable"
    assert infer_care_accept("I can do it with training") == "willing_with_training"
    assert infer_care_accept("मैं ये काम नहीं करूँगा") == "refuses"
    assert infer_care_accept("I won't do diaper care") == "refuses"
    # "nothing much, I give medicines" is the previous answer, not a diaper no.
    assert (
        infer_care_accept(
            "ज्यादा कुछ नहीं, सबको दवाई-ववाई देने का, सलाइन चढ़ाने का, उतारने का सब करता हूँ।"
        )
        is None
    )
    assert infer_care_accept("Actually मैंने कभी किया नहीं है क्या ये ज़रूरी है") is None
    # Demo bug: हाँ about ICU experience is not care consent.
    assert (
        infer_care_accept("हाँ, मैंने तीन साल का आईसीयू वार्ड में मेरा एक्सपीरियंस है इनामदार हॉस्पिटल में")
        is None
    )
    # Care-intro: short clear yes recovers every focused item (avoids re-asking diaper).
    multi = recover_care_updates(
        TurnAnalysis(intent="answer"),
        text="हाँ हाँ मैं ready हूँ।",
        item_ids=["diaper_care", "hygiene_bathing", "toileting_bedpan", "lifting_repositioning"],
    )
    assert len(multi.care_updates) == 4
    assert {u.stance for u in multi.care_updates} == {"comfortable"}
    # ICU-style हाँ on intro still must not recover.
    multi_icu = recover_care_updates(
        TurnAnalysis(intent="answer"),
        text="हाँ, मैंने तीन साल का आईसीयू वार्ड में मेरा एक्सपीरियंस है इनामदार हॉस्पिटल में",
        item_ids=["diaper_care", "hygiene_bathing", "toileting_bedpan", "lifting_repositioning"],
    )
    assert multi_icu.care_updates == []


def test_one_diaper_no_persuades_and_does_not_end(blueprint):
    """Saying they are not comfortable once explains the duty. It does not end the interview."""
    from interview.analysis import recover_care_updates

    flow, _ = make_flow(blueprint)
    reach_care(flow)
    earlier = "ज्यादा कुछ नहीं, सबको दवाई-ववाई देने का, सलाइन चढ़ाने का, उतारने का सब करता हूँ।"
    items = [str(i) for i in flow.state.focus["items"]]
    move = flow.apply(
        recover_care_updates(TurnAnalysis(intent="answer", raw_utterance=earlier), text=earlier, item_ids=items)
    )
    assert move.kind != "gate_failed"
    assert flow.state.care["diaper_care"].persuasions == 0
    said = "अ, नहीं, नहीं, diaper care से मैं ज्यादा comfortable नहीं हूँ।"
    move = flow.apply(
        recover_care_updates(TurnAnalysis(intent="answer", raw_utterance=said), text=said, item_ids=["diaper_care"])
    )
    assert move.kind == "persuade"
    assert flow.state.gate_failed is None
    assert flow.state.care["diaper_care"].persuasions == 1


def test_care_intro_short_yes_skips_per_item_diaper_reask(blueprint):
    """Clear हाँ on care intro should clear the checklist, not re-ask diaper in another format."""
    from interview.analysis import recover_care_updates

    flow, _ = make_flow(blueprint)
    reach_care(flow)
    assert flow.state.focus.get("type") == "care" and len(flow.state.focus.get("items") or []) > 1
    recovered = recover_care_updates(
        TurnAnalysis(intent="answer"),
        text="हाँ।",
        item_ids=[str(i) for i in flow.state.focus["items"]],
    )
    move = flow.apply(recovered)
    assert all(flow.state.care_state(c.id).stance == "comfortable" for c in blueprint.care_items)
    assert move.kind != "ask_care_item"
    assert move.kind != "ask_care"
    assert flow.stage == "clinical" or move.kind == "clinical_question"


def test_care_intro_icu_yes_does_not_skip_diaper_ask(blueprint):
    """Regression: experience-style हाँ during care intro must not mark all care comfortable."""
    flow, _ = make_flow(blueprint)
    reach_care(flow)
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            care_updates=[
                CareUpdate(
                    c.id,
                    "comfortable",
                    reason="recovered from clear yes/no",
                    evidence="हाँ, मैंने तीन साल का आईसीयू वार्ड में मेरा एक्सपीरियंस है",
                )
                for c in blueprint.care_items
            ],
        )
    )
    assert all(flow.state.care_state(c.id).stance == "unknown" for c in blueprint.care_items)
    assert move.kind in ("ask_care", "ask_care_item", "persuade")
    assert flow.stage == "screening"


def test_experience_dive_runs_before_care(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    flow.apply(say(("height_cm", "160"), ("weight_kg", "55")))
    move = flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU Apollo")))
    assert move.kind == "experience_dive"
    assert flow.state.focus["type"] == "experience_dive"
    assert not flow.state.experience_dive_done
    after = flow.apply(TurnAnalysis(intent="answer", gist_en="Handled ICU monitoring and meds"))
    assert flow.state.experience_dive_done
    assert after.kind == "ask_care" or flow.state.focus.get("type") == "care"


def test_salary_holdout_does_not_invent_numbers(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(intent="candidate_question", gist_en="What is the salary? Tell me or I will not answer.")
    )
    assert move.kind == "salary_holdout"
    assert "cannot quote" in move.directive.lower() or "recruitment team" in move.directive.lower()


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
    flow.apply(TurnAnalysis(intent="answer", gist_en="Day to day ICU nursing duties"))
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
    flow.state.claims.append("3 years in ICU")
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
    flow.state.claims.append("3 years ICU")
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


def test_unclear_audio_asks_to_repeat_then_soft_skips_stuck_field(blueprint):
    """Garbled audio clarifies twice, then soft-skips the stuck focus (no infinite loop)."""
    flow, _ = make_flow(blueprint)
    flow.opening()
    assert flow.state.focus.get("type") == "slots"
    bad = TurnAnalysis(intelligibility="unclear")
    m1 = flow.apply(bad)
    m2 = flow.apply(bad)
    m3 = flow.apply(bad)
    assert m1.kind == "ask_repeat" and m2.kind == "ask_repeat"
    # Third unclear on same focus soft-skips (city → unknown) and advances.
    assert m3.kind in ("ask_field", "ask_repeat", "noise_help", "confirm")
    assert any(e[0] == "focus.soft_skip" for e in m3.events) or flow.state.slots["city"].status == "unknown"
    assert flow.state.unclear_total == 3
    # Clear answer still captures; never stores garbage from unclear turns.
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    assert flow.state.unclear_streak == 0


def test_filler_haan_with_care_updates_is_not_treated_as_unclear(blueprint):
    """Short हाँ recovered as care consent must advance, not ask_repeat."""
    from interview.analysis import recover_care_updates

    flow, _ = make_flow(blueprint)
    reach_care(flow)
    recovered = recover_care_updates(
        TurnAnalysis(intent="filler_only"),
        text="हाँ।",
        item_ids=[str(i) for i in flow.state.focus["items"]],
    )
    move = flow.apply(recovered)
    assert move.kind != "ask_repeat"
    assert all(flow.state.care_state(c.id).stance == "comfortable" for c in blueprint.care_items)


def test_compound_candidate_question_still_captures_phone(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(
            intent="candidate_question",
            gist_en="my number is 9876543210, what is the salary?",
            slot_updates=[SlotUpdate("phone", "9876543210", 0.9, "9876543210")],
        )
    )
    assert move.kind in ("salary_holdout", "answer_question")
    assert flow.state.slots["phone"].value == "9876543210"


def test_partial_intelligibility_forces_phone_confirm(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(
            intelligibility="partial",
            intent="answer",
            slot_updates=[
                SlotUpdate("city", "Pune", 0.9),
                SlotUpdate("phone", "9876543210", 0.9),
            ],
        )
    )
    assert flow.state.slots["city"].status == "confirmed"
    assert flow.state.slots["city"].confidence >= 0.6  # partial must not clamp non-confirm fields
    assert flow.state.slots["phone"].status == "captured"
    assert flow.state.slots["phone"].confidence < 0.6
    assert move.kind == "confirm" and "9, 8, 7, 6" in move.directive


def test_unclear_turns_do_not_advance_or_penalise_clinical_progress(blueprint):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    area = flow.state.current_area
    flow.apply(TurnAnalysis(intelligibility="unclear"))
    assert flow.state.areas[area].probes == 0 and not flow.state.areas[area].evidence


@pytest.mark.parametrize(
    ("intent", "kind"),
    [
        ("repeat_request", "repeat"),
        ("rephrase_request", "rephrase"),
        # Fact-less off-topic (ambient STT) → unclear, not a redirect that invents the next ask.
        ("off_topic", "ask_repeat"),
        ("candidate_question", "answer_question"),
    ],
)
def test_requests_and_questions_do_not_advance_the_interview(blueprint, intent, kind):
    flow, _ = make_flow(blueprint)
    reach_clinical(flow, experience=("1", "ward"))
    area, level = flow.state.current_area, flow.state.areas[flow.state.current_area].level
    move = flow.apply(TurnAnalysis(intent=intent))
    assert move.kind == kind
    assert flow.state.current_area == area and flow.state.areas[area].level == level
    assert flow.state.areas[area].probes == 0


def test_off_topic_with_screening_facts_still_redirects(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(
        TurnAnalysis(intent="off_topic", slot_updates=[SlotUpdate("city", "Pune")])
    )
    assert move.kind == "redirect"
    assert flow.state.slots["city"].status == "captured"


def test_factless_off_topic_is_treated_as_noise_not_progress(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    before = dict(flow.state.focus)
    move = flow.apply(TurnAnalysis(intent="off_topic", intelligibility="clear"))
    assert move.kind == "ask_repeat"
    assert any(e[0] == "audio.off_topic_as_noise" for e in move.events)
    assert flow.state.focus.get("type") == before.get("type")


def test_a_clear_side_remark_is_answered_then_the_question_returns(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.last_question = "Which city are you applying for?"
    before = dict(flow.state.focus)
    move = flow.apply(
        TurnAnalysis(intent="off_topic", intelligibility="clear", gist_en="the fan in this room is too loud")
    )
    assert move.kind == "aside"
    assert "fan" in move.directive
    assert "Which city" in move.directive
    assert flow.state.focus.get("type") == before.get("type")
    assert flow.state.slots["city"].status == "empty"


def test_an_answer_that_includes_a_side_remark_is_acknowledged(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(say(("city", "Pune"), aside="the room is very cold"))
    assert "room is very cold" in move.directive
    assert flow.state.slots["city"].value == "Pune"


def test_experience_question_starts_from_the_resume_then_moves_to_nursing(blueprint):
    flow, _ = make_flow(blueprint, resume="Staff nurse, 3 years ICU, Apollo Hospital Pune")
    flow.opening()
    flow.apply(say(("city", "Pune"), ("phone", "9876543210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    asked = flow.apply(say(("height_cm", "160"), ("weight_kg", "55")))
    assert asked.kind == "ask_field"
    assert "Apollo" in asked.directive
    assert "ONE question" in asked.directive
    mismatch = say(("experience_years", "1"), ("experience_settings", "ward"))
    mismatch.resume_mismatch = "resume says 3 years ICU at Apollo; they said 1 year on a ward"
    check = flow.apply(mismatch)
    assert check.kind == "resume_check"
    assert "Apollo" in check.directive
    assert flow.state.resume_crosscheck_done
    clarified = flow.apply(TurnAnalysis(intent="answer", gist_en="The resume is old. I work on a ward now."))
    assert clarified.kind == "experience_dive"
    assert "resume" in clarified.directive.lower()
    nursing = flow.apply(TurnAnalysis(intent="answer", gist_en="I check vitals and give medicines", resume_mismatch="still conflicts"))
    assert nursing.kind != "resume_check"
    assert flow.state.experience_dive_done
    assert nursing.kind in ("ask_care", "ask_care_item")


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
    phone = heuristic_analysis("my number is 98765 43210")
    assert phone.slot_updates[0].value == "9876543210"
    assert phone.slot_updates[0].confidence <= 0.55


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("I want to stop the interview", "wants_to_stop"),
        ("बंद करो", "wants_to_stop"),
        ("I won't answer that", "refusal"),
        ("नहीं बताऊँगा", "refusal"),
        ("tell me a joke", "off_topic"),
    ],
)
def test_heuristic_recovers_stop_refuse_off_topic(text, intent):
    assert heuristic_analysis(text).intent == intent


def test_heuristic_short_haan_is_filler_unless_confirming():
    assert heuristic_analysis("हाँ").intent == "filler_only"
    a = heuristic_analysis("हाँ", pending_field="phone", pending_value="9876543210")
    assert a.intent == "answer" and a.confirmation == "confirmed"


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
