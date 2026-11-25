"""Tests for the weekly report's LLM safeguards. No network or database needed."""

import datetime as dt

from pipeline.report import (
    build_message,
    number_is_allowed,
    validate_summary,
    week_label,
)

FACTS = {
    "week": "16–22 Nov 2026",
    "towns": [
        {"town": "San Pablo", "rain_mm": 12.4, "rain_days": 3, "last_week_rain_mm": 3.1,
         "change_from_last_week_mm": 9.3, "normal_rain_mm": 45.2, "normal_rain_days": 4.1,
         "percent_of_normal_rain": 27, "hottest_c": 31.6, "coolest_c": 22.9,
         "strongest_wind_kmh": 19.8},
        {"town": "Los Baños", "rain_mm": 0.6, "rain_days": 0, "last_week_rain_mm": 8.0,
         "change_from_last_week_mm": -7.4, "normal_rain_mm": 40.0, "normal_rain_days": 3.9,
         "percent_of_normal_rain": 2, "hottest_c": 32.0, "coolest_c": 23.1,
         "strongest_wind_kmh": 15.2},
    ],
}

GOOD = ("In the week of 16–22 Nov 2026, San Pablo got 12.4 mm of rain over 3 rain days, "
        "9.3 mm more than the week before but only 27% of the normal 45.2 mm. "
        "Los Baños stayed almost dry with 0.6 mm, 7.4 mm less than last week. "
        "Temperatures ranged from 22.9 to 32 °C.")


def test_good_summary_passes():
    assert validate_summary(GOOD, FACTS) == []


def test_invented_number_is_rejected():
    bad = GOOD.replace("12.4 mm", "18.0 mm")
    assert "number 18.0 isn't in the data" in validate_summary(bad, FACTS)


def test_llm_arithmetic_is_rejected():
    # 12.4 + 0.6 = 13.0: a correct sum, but not a number we provided
    bad = GOOD + " Together they received 13.0 mm."
    assert any("13.0" in p for p in validate_summary(bad, FACTS))


def test_rounding_is_allowed():
    assert number_is_allowed("12", {12.4})
    assert number_is_allowed("13", {12.5})       # half-up rounding
    assert number_is_allowed("12.4", {12.4})
    assert not number_is_allowed("12.5", {12.4})  # same decimals must match exactly
    assert not number_is_allowed("14", {12.4})


def test_negative_change_can_be_written_as_less():
    # change_from_last_week_mm is -7.4; "7.4 mm less" must pass
    assert validate_summary(GOOD, FACTS) == []


def test_missing_town_is_rejected():
    bad = GOOD.replace("Los Baños stayed almost dry with 0.6 mm, 7.4 mm less than last week. ", "")
    assert "doesn't mention Los Baños" in validate_summary(bad, FACTS)


def test_town_without_accent_is_accepted():
    assert validate_summary(GOOD.replace("Los Baños", "Los Banos"), FACTS) == []


def test_empty_answer_is_rejected():
    # reasoning models that run out of tokens return empty content
    assert validate_summary("", FACTS) == ["empty answer"]
    assert validate_summary("   ", FACTS) == ["empty answer"]


def test_links_and_mentions_are_rejected():
    assert any("link" in p for p in validate_summary(GOOD + " See http://x.y", FACTS))
    assert any("mention" in p for p in validate_summary(GOOD + " @everyone", FACTS))


def test_too_short_is_rejected():
    assert any("length" in p for p in validate_summary("San Pablo, Los Baños.", FACTS))


def test_fallback_message_has_every_town_and_no_summary():
    message = build_message(FACTS, None, None)
    assert "San Pablo" in message and "Los Baños" in message
    assert "Numbers only this week" in message
    assert len(message) <= 2000


def test_llm_message_names_the_model():
    message = build_message(FACTS, GOOD, "some/model:free")
    assert GOOD in message and "some/model:free" in message


def test_week_label():
    assert week_label(dt.date(2026, 11, 16)) == "16–22 Nov 2026"
    assert week_label(dt.date(2026, 11, 30)) == "30 Nov – 6 Dec 2026"
