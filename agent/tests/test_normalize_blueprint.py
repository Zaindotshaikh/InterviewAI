import json
from datetime import date
from pathlib import Path

import pytest

from interview.blueprint import Blueprint
from interview.normalize import (
    normalize_height_cm,
    spoken_height_phrase,
    normalize_phone,
    normalize_weight_kg,
    normalize_year,
    normalize_years_experience,
    parse_height_and_weight,
    spoken_groups,
)

BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("98765 43210", "9876543210"),
        ("+91-98765-43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("0919876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("9123456789", "9123456789"),
        ("9 8 7 6 5 4 3 2 1 0", "9876543210"),
    ],
)
def test_phone_normalisation(raw, expected):
    assert normalize_phone(raw).value == expected


@pytest.mark.parametrize("raw", ["", "98765432101234"])
def test_phone_rejects_bad_numbers(raw):
    assert not normalize_phone(raw).ok


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("98765", "98765"),
        ("1234567890", "1234567890"),
    ],
)
def test_phone_keeps_heard_digits_for_readback(raw, expected):
    assert normalize_phone(raw).value == expected


def test_phone_is_read_as_single_digits():
    assert spoken_groups("9876543210") == "9, 8, 7, 6, 5, 4, 3, 2, 1, 0"


@pytest.mark.parametrize(
    ("raw", "cm"),
    [
        ("5 feet 4 inches", 163),
        ("5'2\"", 157),
        ("5 feet 11 inches", 180),
        ("5 ft 11", 180),
        ("5 11", 180),
        ("5.11", 180),
        ("162", 162),
        ("162 cm", 162),
        ("1.62 m", 162),
        ("5.4", 163),
        ("five", None),
    ],
)
def test_height(raw, cm):
    r = normalize_height_cm(raw)
    assert (r.value if r.ok else None) == cm


@pytest.mark.parametrize("raw", ["400", "50", "5 feet 15 inches"])
def test_height_rejects_impossible(raw):
    assert not normalize_height_cm(raw).ok


@pytest.mark.parametrize(
    ("raw", "city"),
    [
        ("Carol", "Kerala"),
        ("kerla", "Kerala"),
        ("Kerala", "Kerala"),
        ("Bombay", "Mumbai"),
        ("Bangalore", "Bengaluru"),
        ("Pune", "Pune"),
    ],
)
def test_city_stt_repairs(raw, city):
    from interview.normalize import plausible_city

    ok, cleaned = plausible_city(raw)
    assert ok and cleaned == city


def test_height_and_weight_stay_on_their_own_units():
    assert parse_height_and_weight("My weight is 50 kg and my height is 144 cm") == (144, 50)
    assert parse_height_and_weight("144 cm and 50 kg") == (144, 50)
    assert parse_height_and_weight("50kg 144cm") == (144, 50)
    assert parse_height_and_weight("कद 144 सेंटीमीटर और वजन 50 किलो") == (144, 50)
    assert parse_height_and_weight("70 165") == (165, 70)
    assert parse_height_and_weight("165 70") == (165, 70)
    assert parse_height_and_weight("165 and 70") == (165, 70)
    assert parse_height_and_weight("5 feet 11 inches and 70 kg") == (180, 70)
    assert parse_height_and_weight("70 kg 5 11") == (180, 70)
    assert parse_height_and_weight("5 11 70") == (180, 70)
    assert parse_height_and_weight("5.11 and 65 kg") == (180, 65)


def test_confirm_phrase_keeps_spoken_height_unit():
    assert spoken_height_phrase("5 feet 11 inches and 70 kg", 180) == "5 feet 11 inches"
    assert spoken_height_phrase("70 kg 5 11", 180) == "5 feet 11 inches"
    assert spoken_height_phrase("5.11 and 65 kg", 180) == "5 feet 11 inches"
    assert spoken_height_phrase("160 cm 55 kg", 160) == "160 centimetres"
    assert spoken_height_phrase("55 kg and 160 cm", 160) == "160 centimetres"


def test_weight():
    assert normalize_weight_kg("58 kg").value == 58
    assert normalize_weight_kg("130 lbs").value == 59
    assert not normalize_weight_kg("12 kg").ok
    assert not normalize_weight_kg("sixty").ok


def test_year():
    today = date(2026, 10, 4)
    assert normalize_year("2019", today=today).value == 2019
    assert normalize_year("passed in 2021", today=today).value == 2021
    assert normalize_year("19", today=today).value == 2019
    assert not normalize_year("1950", today=today).ok
    assert not normalize_year("2040", today=today).ok


def test_years_of_experience():
    assert normalize_years_experience("3").value == 3
    assert normalize_years_experience("2.5 years").value == 2.5
    assert normalize_years_experience("6 months").value == 0.5
    assert normalize_years_experience("fresher").value == 0
    assert not normalize_years_experience("90").ok


def test_the_shipped_blueprint_is_well_formed():
    bp = Blueprint.from_api(json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")))
    assert [f.id for f in bp.fields][:2] == ["city", "phone"]  # client's order
    assert bp.field_spec("phone").confirm
    assert [c.id for c in bp.gate_items] == ["diaper_care"]
    assert len(bp.care_item("diaper_care").persuasion) >= 2
    assert len(bp.areas) >= 8 and {t.id for t in bp.tiers} >= {"tier_1", "not_eligible", "needs_review"}
    for area in bp.areas:
        assert {lv.level for lv in area.levels} == {1, 2, 3}, area.id
        for lv in area.levels:
            assert lv.seed and lv.key_points, (area.id, lv.level)
        ids = [k.id for lv in area.levels for k in lv.key_points]
        assert len(ids) == len(set(ids)), f"duplicate key point ids in {area.id}"


def test_missing_blueprint_falls_back_to_a_minimal_one():
    bp = Blueprint.from_api(None)
    assert bp.areas and not bp.fields and not bp.gate_items
