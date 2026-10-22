"""Spoken mobiles: mixed language, groups, hundreds, and corrections."""

from interview.phone_speech import correct_phone, parse_spoken_phone, trunk_prefix


def test_pairs_hundreds_and_mixed_languages():
    assert parse_spoken_phone("chappan baawan") == "5652"
    assert parse_spoken_phone("छप्पन बावन") == "5652"
    assert parse_spoken_phone("nau sau sataasi") == "987"
    assert parse_spoken_phone("nine hundred eighty seven") == "987"
    assert parse_spoken_phone("nine एक 1 two तीन 2 chappan baawan") == "9112325652"
    assert trunk_prefix(parse_spoken_phone("+91 98765 43210")) == "9876543210"
    assert parse_spoken_phone("double nine one two") == "9912"
    assert parse_spoken_phone("911, 2323. 911, 2323.") == "9112323"
    assert parse_spoken_phone("98765. 43210") == "9876543210"


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
