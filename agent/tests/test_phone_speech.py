"""Spoken mobiles: digits are copied, words are stored from the hearing."""

from interview.phone_speech import parse_spoken_phone, store_phone, trunk_prefix


def test_digits_are_copied_in_order():
    assert parse_spoken_phone("89, 75, 34, 67, 90") == "8975346790"
    assert trunk_prefix(parse_spoken_phone("+91 98765 43210")) == "9876543210"
    assert parse_spoken_phone("911, 2323. 911, 2323.") == "9112323"
    assert parse_spoken_phone("98765. 43210") == "9876543210"
    assert parse_spoken_phone("८९ ७५") == "8975"


def test_country_code_91_strips_only_when_twelve_digits():
    # Real mobiles often start with 91 — keep all ten digits.
    assert trunk_prefix("9123456789") == "9123456789"
    assert trunk_prefix("9112323549") == "9112323549"
    # Country code + national number.
    assert trunk_prefix("919876543210") == "9876543210"
    assert trunk_prefix("0919876543210") == "9876543210"
    assert trunk_prefix("00919876543210") == "9876543210"
    assert store_phone("919876543210") == "9876543210"
    assert store_phone("my number is 9123456789") == "9123456789"


def test_words_are_stored_from_the_hearing():
    assert store_phone("saade paach she", "550") == "550"
    assert store_phone("साडे पाचशे", "550") == "550"
    assert store_phone("chaar so chalees", "440") == "440"
    assert store_phone("char sau sattar", "470") == "470"
    assert store_phone("eighty-seven", "87") == "87"
    assert store_phone("eight, seven", "87") == "87"
    assert store_phone("double nine", "99") == "99"
    assert store_phone("chappan baawan", "5652") == "5652"
    assert store_phone("नवासी पचहत्तर चौंतीस सड़सठ नब्बे", "8975346790") == "8975346790"
    assert store_phone("nine एक 1 two तीन 2 chappan baawan", "9112325652") == "9112325652"


def test_a_hearing_cannot_replace_plain_digits_or_invent_a_mobile():
    assert store_phone("89, 75, 34, 67, 90", "1111111111") == "8975346790"
    assert store_phone("the number I said", "8975346790") == ""
    assert store_phone("saade paach she", "9876543210") == ""
    assert store_phone("yes", "9876543210") == ""
    assert store_phone("haan", "9876543210") == ""
    assert store_phone("my number is 9876543210", "1111111111") == "9876543210"


def test_wordy_sentences_do_not_keep_scrap_digits_without_a_hearing():
    assert store_phone("3550 hai, 3549 nahi") == ""
    assert store_phone("nine एक 1 two तीन 2") == ""
    assert store_phone("nahi, number hai 9112323549") == "9112323549"
