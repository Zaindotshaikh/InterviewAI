"""A resume check must fire for a different hospital, not for the same one spelled another way."""

import pytest

from interview.analysis import TurnAnalysis
from interview.resume_match import is_false_mismatch
from tests.test_flow import blueprint, make_flow  # noqa: F401  (fixture re-export)

RESUME = (
    "Registered Nurse (Staff Nurse). B.Sc. Nursing graduate with 3 years 8 months clinical experience. "
    "1) Staff Nurse, Medical ICU, Apollo Hospitals, Pune, July 2023 - Present. "
    "2) Staff Nurse, General Medicine Ward, Ruby Hall Clinic, Pune, Nov 2022 - June 2023."
)


@pytest.mark.parametrize(
    "note",
    [
        "resume says Apollo Hospitals, Pune; they said Apollo Hospital.",
        "resume says Apollo Hospitals; they said Apollo.",
        "resume says Apollo Hospitals, Pune; they said apollo hospital pune",
        "resume says Ruby Hall Clinic; they said Ruby Hall",
        "resume says Apollo Hospitals, Pune; they said अपोलो हॉस्पिटल",
        "resume says 3 years 8 months; they said 3 years",
        "resume says 3 years 8 months; they said 4 years",
    ],
)
def test_same_place_or_rounded_years_is_not_a_mismatch(note):
    assert is_false_mismatch(note, RESUME)


@pytest.mark.parametrize(
    "note",
    [
        "resume says Apollo Hospitals, Pune; they said Inamdar Hospital.",
        "resume says Apollo Hospitals, Pune; they said Fortis Hospital",
        "resume says 3 years 8 months; they said 8 years",
        "resume says 3 years 8 months; they said 10 years",
        "resume says Apollo Hospitals, Pune; they said इनामदार हॉस्पिटल",
    ],
)
def test_a_different_hospital_or_a_real_years_gap_still_counts(note):
    assert not is_false_mismatch(note, RESUME)


def test_unparseable_or_empty_input_is_never_dropped():
    assert not is_false_mismatch("", RESUME)
    assert not is_false_mismatch("something odd", RESUME, "")
    assert not is_false_mismatch("resume says Apollo; they said Apollo", "")


def _experience_turn(note: str, said: str) -> TurnAnalysis:
    return TurnAnalysis(intent="answer", resume_mismatch=note, raw_utterance=said)


def _flow_at_experience(blueprint):  # noqa: F811
    from tests.test_flow import SlotUpdate, make_flow as build

    flow, _ = build(blueprint, resume=RESUME)
    flow.opening()
    flow.apply(TurnAnalysis(slot_updates=[SlotUpdate("city", "Pune", 0.9, "")]))
    flow.apply(TurnAnalysis(slot_updates=[SlotUpdate("phone", "9876543210", 0.9, "")]))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))
    flow.apply(
        TurnAnalysis(
            slot_updates=[SlotUpdate("qualification", "B.Sc Nursing", 0.9, ""), SlotUpdate("qualification_year", "2022", 0.9, "")]
        )
    )
    flow.apply(
        TurnAnalysis(
            slot_updates=[SlotUpdate("height_cm", "5 feet 11 inches", 0.9, ""), SlotUpdate("weight_kg", "80 kg", 0.9, "")]
        )
    )
    flow.apply(TurnAnalysis(confirmation_field="body", confirmation="confirmed", raw_utterance="haan"))
    return flow


def test_flow_does_not_stop_to_ask_about_apollo_hospital_vs_hospitals(blueprint):  # noqa: F811
    flow = _flow_at_experience(blueprint)
    from tests.test_flow import SlotUpdate

    said = "तीन साल का experience इस ICU ward में काम किया है मैंने, Apollo Hospital में।"
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance=said,
            resume_mismatch="resume says Apollo Hospitals, Pune; they said Apollo Hospital.",
            slot_updates=[
                SlotUpdate("experience_years", "3", 0.9, ""),
                SlotUpdate("experience_settings", "ICU ward, Apollo Hospital", 0.9, ""),
            ],
        )
    )
    assert move.kind != "resume_check"
    assert flow.state.resume_crosscheck_done is False


def test_flow_still_asks_when_the_hospital_really_differs(blueprint):  # noqa: F811
    flow = _flow_at_experience(blueprint)
    from tests.test_flow import SlotUpdate

    said = "तीन साल का experience है, Inamdar Hospital में।"
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance=said,
            resume_mismatch="resume says Apollo Hospitals, Pune; they said Inamdar Hospital.",
            slot_updates=[
                SlotUpdate("experience_years", "3", 0.9, ""),
                SlotUpdate("experience_settings", "Inamdar Hospital", 0.9, ""),
            ],
        )
    )
    assert move.kind == "resume_check"
