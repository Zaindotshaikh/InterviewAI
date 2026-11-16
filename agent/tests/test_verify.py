"""QA guardrails: facts are checked against the resume and common sense, and every re-ask gives its reason."""

from datetime import date

from interview.analysis import SlotUpdate, TurnAnalysis
from interview.flow import REASON_CLAUSES, Move
from interview.verify import (
    ResumeFacts,
    body_issue,
    check_experience,
    check_qualification,
    names_a_workplace,
    nursing_qualification,
    resume_facts,
)

from tests.test_flow import blueprint, make_flow, say  # noqa: F401  (blueprint is a fixture)

RESUME = """Registered Nurse (Staff Nurse) | 28 years
PROFESSIONAL SUMMARY
B.Sc. Nursing graduate with 3 years 8 months clinical experience in multi-specialty hospital settings.
EDUCATION
- B.Sc. Nursing, Bharati Vidyapeeth College of Nursing, Pune (2018 - 2022)
WORK EXPERIENCE
1) Staff Nurse
   Apollo Hospitals, Pune | July 2023 - Present (about 2 years 3 months)
"""


# ------------------------------------------------------------------------------------------- pure checks


def test_resume_total_beats_age_and_job_lines():
    facts = resume_facts(RESUME, today=date(2026, 11, 13))
    assert round(facts.years or 0, 2) == 3.67
    assert facts.qualifications == frozenset({"B.Sc Nursing"})


def test_resume_years_fall_back_to_work_dates_without_double_counting():
    text = "WORK EXPERIENCE\nA | Jan 2022 - Dec 2022\nB | Jun 2022 - Dec 2023\nEDUCATION\nGNM (2015 - 2018)\n"
    facts = resume_facts(text, today=date(2026, 1, 1))
    assert 1.8 <= (facts.years or 0) <= 2.0  # Jan 2022 .. Dec 2023, overlap counted once
    assert facts.qualifications == frozenset({"GNM"})


def test_experience_conflict_needs_a_gap_of_a_year():
    facts = ResumeFacts(years=3.67)
    assert check_experience(3, facts) is None
    assert check_experience(4, facts) is None
    assert check_experience(1, facts) is not None
    assert check_experience(2, facts) is not None
    assert check_experience(0, facts) is not None
    assert check_experience(1, ResumeFacts()) is None  # no resume figure: nothing to compare


def test_qualification_must_be_nursing_and_match_resume():
    facts = ResumeFacts(qualifications=frozenset({"B.Sc Nursing"}))
    assert check_qualification("B.Sc Nursing", facts) is None
    assert check_qualification("Post Basic B.Sc Nursing", facts) is None
    wrong = check_qualification("B.Tech", facts)
    assert wrong is not None and wrong.kind == "not_nursing" and "B.Sc Nursing" in wrong.expected
    other = check_qualification("GNM", facts)
    assert other is not None and other.kind == "resume_mismatch"
    assert check_qualification("GNM", ResumeFacts()) is None
    assert check_qualification("Btech", ResumeFacts()).kind == "not_nursing"
    assert nursing_qualification("बीएससी नर्सिंग") == "B.Sc Nursing"


def test_body_must_be_a_human_body():
    assert body_issue(170, 70) is None
    assert body_issue(150, 48) is None
    assert body_issue(200, 40) is not None
    assert body_issue(155, 125) is not None


# ----------------------------------------------------------------------------------------- flow behaviour


def _screening_to_education(flow):
    flow.opening()
    flow.apply(say(("city", "Pune")))
    flow.apply(say(("phone", "98765 43210")))
    flow.apply(TurnAnalysis(confirmation_field="phone", confirmation="confirmed"))


def test_wrong_qualification_is_probed_again_and_never_accepted(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _screening_to_education(flow)
    move = flow.apply(say(("qualification", "B.Tech"), ("qualification_year", "2019")))
    assert move.kind == "verify"
    assert "B.Sc Nursing" in move.directive and "not a nursing qualification" in move.directive
    assert flow.state.slots["qualification"].status == "empty"
    assert str(flow.state.slots["qualification_year"].value) == "2019"

    # Second irrelevant answer: probed again, not accepted.
    again = flow.apply(say(("qualification", "B.Tech")))
    assert again.kind == "verify"
    assert "already asked" in again.directive
    assert flow.state.slots["qualification"].status == "empty"
    third = flow.apply(say(("qualification", "BCA")))
    assert third.kind == "verify"

    # Still irrelevant after the last probe: bounded, and never recorded as the qualification.
    last = flow.apply(say(("qualification", "12th pass")))
    assert last.kind != "verify"
    slot = flow.state.slots["qualification"]
    assert slot.status == "unknown" and slot.value is None
    assert "not a nursing qualification" in slot.evidence


def test_unanswered_qualification_check_never_keeps_a_non_nursing_value(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _screening_to_education(flow)
    assert flow.apply(say(("qualification", "B.Tech"))).kind == "verify"
    for word in ("hmm okay", "let me think", "well then", "so basically", "right so", "umm sure"):
        flow.apply(TurnAnalysis(intent="answer", intelligibility="clear", raw_utterance=word))
    slot = flow.state.slots["qualification"]
    assert slot.status != "captured" or nursing_qualification(slot.value) is not None


def test_confirmed_qualification_asks_only_the_year(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _screening_to_education(flow)
    assert flow.apply(say(("qualification", "B.Tech"))).kind == "verify"
    year = flow.apply(say(("qualification", "B.Sc Nursing"), raw_utterance="अ, हाँ, आप B.Sc Nursing ही हैं।"))
    assert year.kind == "ask_field"
    assert year.reason == ""
    assert "still need this detail" not in year.directive
    assert year.directive.startswith("They confirmed their qualification is B.Sc Nursing.")
    assert year.verbatim and "साल" in year.verbatim
    assert flow.state.focus.get("ids") == ["qualification_year"]


def test_qualification_corrected_after_verification_is_kept(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _screening_to_education(flow)
    assert flow.apply(say(("qualification", "B.Tech"), ("qualification_year", "2022"))).kind == "verify"
    flow.apply(say(("qualification", "B.Sc Nursing")))
    slot = flow.state.slots["qualification"]
    assert slot.value == "B.Sc Nursing" and slot.status in ("captured", "confirmed")
    assert not flow.state.verify_prev


def test_matching_qualification_is_not_questioned(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _screening_to_education(flow)
    move = flow.apply(say(("qualification", "B.Sc Nursing"), ("qualification_year", "2022")))
    assert move.kind != "verify"


def _to_experience(flow):
    _screening_to_education(flow)
    flow.apply(say(("qualification", "B.Sc Nursing"), ("qualification_year", "2022")))
    flow.apply(say(("height_cm", "165"), ("weight_kg", "60")))
    flow.apply(TurnAnalysis(confirmation_field="body", confirmation="confirmed", raw_utterance="haan"))


def test_experience_far_from_resume_is_verified(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _to_experience(flow)
    move = flow.apply(say(("experience_years", "1"), ("experience_settings", "ward")))
    assert move.kind == "verify"
    assert "3 years 8 months" in move.directive and "1 year" in move.directive
    assert flow.state.slots["experience_years"].status == "empty"
    assert flow.state.experience_level == "unknown"

    # Still far from the resume: probed again instead of accepted.
    again = flow.apply(say(("experience_years", "2")))
    assert again.kind == "verify"
    assert "already asked" in again.directive
    assert flow.state.slots["experience_years"].status == "empty"

    settled = flow.apply(say(("experience_years", "3")))
    assert settled.kind != "verify"
    assert float(flow.state.slots["experience_years"].value) == 3.0


def test_experience_that_never_matches_is_bounded_and_flagged(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _to_experience(flow)
    assert flow.apply(say(("experience_years", "1"), ("experience_settings", "Apex Hospital"))).kind == "verify"
    assert flow.apply(say(("experience_years", "1"))).kind == "verify"
    assert flow.apply(say(("experience_years", "1"))).kind == "verify"
    last = flow.apply(say(("experience_years", "1")))
    assert last.kind != "verify"
    slot = flow.state.slots["experience_years"]
    assert slot.status in ("captured", "confirmed") and "unverified" in slot.evidence


def test_experience_without_a_hospital_name_asks_for_it(blueprint):
    flow, _ = make_flow(blueprint)
    _to_experience(flow)
    move = flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU in a private hospital")))
    assert move.kind == "ask_field" and flow.state.focus.get("workplace")
    assert "hospital" in move.directive and "name" in move.directive

    # Another generic reply asks again, with a reason.
    again = flow.apply(TurnAnalysis(intent="answer", raw_utterance="private hospital only"))
    assert again.kind == "ask_field" and again.reason == "not_given"

    named = flow.apply(TurnAnalysis(intent="answer", raw_utterance="Fortis Hospital"))
    assert named.kind in ("ask_care", "ask_care_item")
    assert "Fortis" in str(flow.state.slots["experience_settings"].value)


def test_hospital_name_ask_is_bounded_and_skipped_for_named_or_fresher(blueprint):
    flow, _ = make_flow(blueprint)
    _to_experience(flow)
    assert flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU"))).kind == "ask_field"
    assert flow.apply(TurnAnalysis(intent="answer", raw_utterance="ICU")).kind == "ask_field"
    assert flow.apply(TurnAnalysis(intent="answer", raw_utterance="ward")).kind == "ask_field"
    last = flow.apply(TurnAnalysis(intent="answer", raw_utterance="private hospital"))
    assert last.kind in ("ask_care", "ask_care_item")  # three asks, then it moves on

    named, _ = make_flow(blueprint)
    _to_experience(named)
    assert named.apply(say(("experience_years", "3"), ("experience_settings", "ICU at Apollo Hospital"))).kind in (
        "ask_care",
        "ask_care_item",
    )

    fresher, _ = make_flow(blueprint)
    _to_experience(fresher)
    assert fresher.apply(say(("experience_years", "0"), ("experience_settings", "internship"))).kind != "ask_field"


def test_names_a_workplace():
    assert names_a_workplace("Apollo Hospital")
    assert names_a_workplace("अपोलो हॉस्पिटल में")
    assert names_a_workplace("ICU at Fortis")
    assert not names_a_workplace("ICU in a private hospital")
    assert not names_a_workplace("प्राइवेट अस्पताल में आईसीयू")
    assert not names_a_workplace("ward, 3 years")
    assert not names_a_workplace("ICU in Pune", exclude="Pune")


def test_workplace_after_the_years_check_does_not_close_it(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _to_experience(flow)
    assert flow.apply(say(("experience_years", "1"), ("experience_settings", "ward"))).kind == "verify"
    follow = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="अ, Apex Hospital में काम किया।",
            slot_updates=[
                SlotUpdate("experience_years", "1", 0.97, ""),
                SlotUpdate("experience_settings", "Apex Hospital", 0.89, ""),
            ],
        )
    )
    assert follow.kind == "verify"
    assert "3 years 8 months" in follow.directive
    assert "Apex" in follow.directive
    assert "Apollo" in follow.directive
    assert flow.state.slots["experience_years"].status == "empty"
    assert flow.state.slots["experience_settings"].value == "Apex Hospital"


def test_experience_close_to_resume_is_accepted(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _to_experience(flow)
    move = flow.apply(say(("experience_years", "3"), ("experience_settings", "ICU")))
    assert move.kind != "verify"


def test_unanswered_verification_keeps_the_first_answer(blueprint):
    flow, _ = make_flow(blueprint, resume=RESUME)
    _to_experience(flow)
    assert flow.apply(say(("experience_years", "1"), ("experience_settings", "ward"))).kind == "verify"
    for word in ("hmm okay", "let me think", "well then", "so basically", "right so", "umm sure"):
        flow.apply(TurnAnalysis(intent="answer", intelligibility="clear", raw_utterance=word))
    assert flow.state.slots["experience_years"].status in ("captured", "unknown", "confirmed")
    assert flow.state.verifications["experience_years"] >= 1


def test_impossible_body_combination_is_checked_once(blueprint):
    flow, _ = make_flow(blueprint)
    _screening_to_education(flow)
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    move = flow.apply(say(("height_cm", "200"), ("weight_kg", "40")))
    assert move.kind == "verify"
    assert move.reason == "verify"
    assert flow.state.slots["height_cm"].status == "empty" and flow.state.slots["weight_kg"].status == "empty"

    again = flow.apply(say(("height_cm", "200"), ("weight_kg", "40")))
    assert again.kind == "confirm"  # read-back still follows, no second challenge


def test_swapped_height_and_weight_are_read_back(blueprint):
    flow, _ = make_flow(blueprint)
    _screening_to_education(flow)
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    move = flow.apply(
        TurnAnalysis(
            intent="answer",
            raw_utterance="अ, height है 80 kg और वज़न है 511।",
            slot_updates=[SlotUpdate("weight_kg", "80", 0.9, "")],
        )
    )
    assert move.kind == "confirm"
    assert move.verbatim and "बदल" in move.verbatim
    assert flow.state.slots["height_cm"].value == 180
    assert flow.state.slots["weight_kg"].value == 80


def test_normal_body_goes_straight_to_readback(blueprint):
    flow, _ = make_flow(blueprint)
    _screening_to_education(flow)
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    assert flow.apply(say(("height_cm", "165"), ("weight_kg", "60"))).kind == "confirm"


# ---------------------------------------------------------------------------------------------- re-asks


def test_unclear_body_answer_asks_for_height_and_weight_with_a_reason(blueprint):
    flow, _ = make_flow(blueprint)
    _screening_to_education(flow)
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    assert flow.state.focus.get("ids") == ["height_cm", "weight_kg"]
    flow.apply(TurnAnalysis(intelligibility="unclear"))
    second = flow.apply(TurnAnalysis(intelligibility="unclear"))
    assert second.kind == "ask_repeat"
    assert second.reason == "audio"
    assert REASON_CLAUSES["audio"] in second.directive
    assert "height and weight" in second.directive


def test_partial_transcript_says_the_line_was_choppy(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(TurnAnalysis(intent="answer", intelligibility="partial", raw_utterance="pu"))
    assert move.kind == "ask_repeat"
    assert move.reason == "choppy"
    assert "choppy" in move.directive


def test_answer_without_the_asked_detail_does_not_claim_bad_audio(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    move = flow.apply(TurnAnalysis(intent="answer", intelligibility="clear", raw_utterance="I like my job"))
    assert move.kind == "ask_repeat"
    assert move.reason == "not_given"
    assert "you still need this detail" in move.directive


def test_invalid_value_says_it_does_not_look_right(blueprint):
    flow, _ = make_flow(blueprint)
    _screening_to_education(flow)
    flow.apply(say(("qualification", "GNM"), ("qualification_year", "2019")))
    move = flow.apply(say(("height_cm", "20"), ("weight_kg", "60")))
    assert move.kind == "reask_invalid"
    assert move.reason == "invalid"
    assert "does not look right" in move.directive
    assert "could not hear them" in move.directive  # only inside the 'do not say' instruction


def test_same_question_twice_in_a_row_must_say_why(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.state.focus = {"type": "slots", "ids": ["city"]}
    first = flow._guard_repeat(Move("ask_field", "Ask the city."))
    second = flow._guard_repeat(Move("ask_field", "Ask the city."))
    assert first.reason == ""
    assert second.reason == "not_given"
    assert "still need this detail" in second.directive


def test_late_second_piece_of_an_answer_is_ignored_not_asked_again(blueprint):
    flow, _ = make_flow(blueprint)
    flow.opening()
    flow.apply(TurnAnalysis(intent="answer", raw_utterance="पुणे, पुणे", slot_updates=[SlotUpdate("city", "Pune", 0.9, "")]))
    assert flow.state.focus.get("type") == "slots"  # the next question (phone) is already out
    tail = flow.apply(TurnAnalysis(intent="answer", raw_utterance="पुणे, पुणे और बैंगलोर"))
    assert tail.kind == "hold"
    assert tail.directive == ""


