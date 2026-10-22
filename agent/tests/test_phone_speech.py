"""Spoken mobiles: digits are copied, words are stored from the hearing."""

from interview.phone_speech import correct_phone, heard_phone, parse_spoken_phone, trunk_prefix


def test_english_groups_and_single_digits():
    assert parse_spoken_phone("eighty-seven") == "87"
    assert parse_spoken_phone("eighty seven") == "87"
    assert parse_spoken_phone("eight, seven") == "87"
    assert parse_spoken_phone("nine eight eighty-seven six") == "98876"
    assert parse_spoken_phone("double nine") == "99"
    assert parse_spoken_phone("chaar so chalees") == ""


def test_digits_are_copied_in_order():
    assert parse_spoken_phone("89, 75, 34, 67, 90") == "8975346790"
    assert trunk_prefix(parse_spoken_phone("+91 98765 43210")) == "9876543210"
    assert parse_spoken_phone("911, 2323. 911, 2323.") == "9112323"
    assert parse_spoken_phone("98765. 43210") == "9876543210"
    assert parse_spoken_phone("८९ ७५") == "8975"


def test_number_words_are_not_guessed_from_a_spelling_list():
    assert parse_spoken_phone("chappan baawan") == ""
    assert parse_spoken_phone("नवासी पचहत्तर चौंतीस सड़सठ नब्बे") == ""
    assert parse_spoken_phone("eighty nine seventy five") == "8975"


def test_a_hearing_stores_words_and_cannot_replace_plain_digits():
    assert heard_phone("नवासी पचहत्तर चौंतीस सड़सठ नब्बे", "8975346790") == "8975346790"
    assert heard_phone("eighty nine, seventy five", "8975") == "8975"
    assert heard_phone("89, 75, 34, 67, 90", "1111111111") == "8975346790"
    assert heard_phone("yes", "9876543210") == ""
    assert heard_phone("haan", "9876543210") == ""


def test_correction_replaces_only_the_named_part():
    prev = "9112323549"
    assert correct_phone(prev, "3549 nahi 3550") == "9112323550"
    assert correct_phone(prev, "3550 hai, 3549 nahi") == "9112323550"
    assert correct_phone(prev, "last four 3550") == "9112323550"
    assert correct_phone(prev, "3550 last") == "9112323550"
    assert correct_phone(prev, "nahi, number hai 9112323549") == prev
    assert correct_phone(prev, "nahi") == ""
    assert correct_phone("9112323", "540") == "9112323540"
    assert correct_phone("1112323549", "नहीं, नहीं, start में 911, बाकी का सही है।") == "9112323549"
    assert correct_phone("911", "28") == "911"
    assert correct_phone(prev, "pehli char 9811") == "9811323549"
