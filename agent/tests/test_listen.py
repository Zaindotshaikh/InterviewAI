"""Noise is not an answer. Words are. A loud room does not hold the turn open."""

from interview.listen import ListenFloor, is_candidate_speech, looks_finished


def test_noise_and_fillers_are_not_speech():
    for text in ("", "...", "…", "uh", "hmm", "हम्म", "(cough)", "[noise]", "a", "uh um"):
        assert is_candidate_speech(text) is False, text


def test_real_words_and_digits_are_speech():
    for text in ("पुणे", "Pune", "okay", "haan", "yes", "5", "9112323549", "I check vitals"):
        assert is_candidate_speech(text) is True, text


def test_words_inside_noise_still_count():
    assert is_candidate_speech("uh पुणे") is True


def test_finished_sentence():
    assert looks_finished("पुणे।") is True
    assert looks_finished("I work in Pune") is False


def test_noise_does_not_hold_the_floor():
    floor = ListenFloor()
    floor.note_speech_start(0.0)
    floor.note_transcript("uh", 0.2)
    assert floor.decide(1.0, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"
    assert floor.decide(2.3, user_speaking=True, min_hold=0.25, max_hold=2.3) == "release"


def test_a_period_does_not_cut_them_off_while_they_are_still_speaking():
    """Scribe writes 'पुणे.' in the middle of 'पुणे और बांग्लादेश'. That is not the end."""
    floor = ListenFloor()
    floor.note_transcript("पुणे।", 1.0)
    assert floor.decide(1.3, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"
    floor.note_transcript("पुणे और बांग्लादेश", 1.5)
    assert floor.decide(2.0, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"
    assert floor.decide(3.8, user_speaking=True, min_hold=0.25, max_hold=2.3) == "commit"


def test_unfinished_words_wait_until_the_max_hold():
    floor = ListenFloor()
    floor.note_transcript("I work in", 1.0)
    assert floor.decide(1.4, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"
    assert floor.decide(3.3, user_speaking=True, min_hold=0.25, max_hold=2.3) == "commit"


def test_new_words_reset_the_hold():
    floor = ListenFloor()
    floor.note_transcript("I work", 1.0)
    floor.note_transcript("I work in Pune", 3.0)
    assert floor.decide(3.2, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"


def test_quiet_room_is_left_to_normal_endpointing():
    floor = ListenFloor()
    floor.note_transcript("पुणे।", 1.0)
    assert floor.decide(5.0, user_speaking=False, min_hold=0.25, max_hold=2.3) == "wait"


def test_agent_speaking_clears_an_open_listen():
    floor = ListenFloor()
    floor.note_transcript("पुणे।", 1.0)
    floor.note_agent_busy()
    assert floor.decide(4.0, user_speaking=True, min_hold=0.25, max_hold=2.3) == "wait"
