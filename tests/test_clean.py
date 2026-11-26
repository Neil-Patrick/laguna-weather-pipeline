"""Tests for clean.py: the validation boundary. No network or database needed."""

import math

import pytest

from pipeline.clean import clean_daily

UNITS = {"temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm",
         "precipitation_hours": "h", "wind_speed_10m_max": "km/h"}


def make_raw(**overrides) -> dict:
    """A small valid Open-Meteo response (2 days); override any daily list."""
    daily = {
        "time": ["2024-07-01", "2024-07-02"],
        "temperature_2m_max": [31.0, 30.5],
        "temperature_2m_min": [23.0, 22.8],
        "precipitation_sum": [5.0, 0.0],
        "precipitation_hours": [3.0, 0.0],
        "wind_speed_10m_max": [8.0, 9.5],
    }
    daily.update(overrides)
    return {"daily_units": dict(UNITS), "daily": daily}


def is_null(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


# ---------- good data ----------

def test_good_data_passes_unchanged():
    rows, issues = clean_daily(make_raw(), "Testville")
    assert issues == []
    assert list(rows.columns) == ["date", "temp_max_c", "temp_min_c", "precipitation_mm",
                                  "rain_hours", "wind_max_kmh"]
    assert rows.precipitation_mm.tolist() == [5.0, 0.0]   # 0.0 stays 0.0, not NULL


def test_missing_value_stays_missing_and_is_not_an_issue():
    rows, issues = clean_daily(make_raw(precipitation_sum=[None, 0.0]), "Testville")
    assert issues == []                      # missing isn't wrong
    assert is_null(rows.precipitation_mm[0])  # NULL, never 0


# ---------- bad individual values: NULL + reported ----------

@pytest.mark.parametrize("field, column, bad", [
    ("temperature_2m_max", "temp_max_c", 999.0),
    ("precipitation_sum", "precipitation_mm", -3.0),
    ("precipitation_hours", "rain_hours", 25.0),
    ("wind_speed_10m_max", "wind_max_kmh", -1.0),
])
def test_out_of_range_value_becomes_null_and_is_reported(field, column, bad):
    raw = make_raw()
    raw["daily"][field] = [bad, raw["daily"][field][1]]
    rows, issues = clean_daily(raw, "Testville")
    assert is_null(rows[column][0])
    assert not is_null(rows[column][1])      # the other day is untouched
    assert len(issues) == 1 and column in issues[0] and "outside" in issues[0]


def test_non_numeric_value_becomes_null_and_is_reported():
    rows, issues = clean_daily(make_raw(precipitation_hours=["abc", 0.0]), "Testville")
    assert is_null(rows.rain_hours[0])
    assert len(issues) == 1 and "not a number" in issues[0]


def test_min_above_max_nulls_both_and_reports_both():
    rows, issues = clean_daily(make_raw(temperature_2m_max=[22.0, 30.5],
                                        temperature_2m_min=[25.0, 22.8]), "Testville")
    assert is_null(rows.temp_max_c[0]) and is_null(rows.temp_min_c[0])
    assert len(issues) == 2
    assert rows.precipitation_mm[0] == 5.0   # the rest of that day is kept


def test_one_missing_temperature_is_not_a_conflict():
    rows, issues = clean_daily(make_raw(temperature_2m_max=[None, 30.5]), "Testville")
    assert issues == []
    assert rows.temp_min_c[0] == 23.0


# ---------- structural problems: raise ----------

def test_missing_variable_raises():
    raw = make_raw()
    del raw["daily"]["wind_speed_10m_max"]
    with pytest.raises(ValueError, match="missing wind_speed_10m_max"):
        clean_daily(raw, "Testville")


def test_unit_change_raises():
    # 86 °F would pass the °C range check, so only the unit check catches this
    raw = make_raw(temperature_2m_max=[86.0, 87.0])
    raw["daily_units"]["temperature_2m_max"] = "°F"
    with pytest.raises(ValueError, match="expected '°C'"):
        clean_daily(raw, "Testville")


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="different length"):
        clean_daily(make_raw(precipitation_sum=[5.0]), "Testville")


def test_malformed_date_raises():
    with pytest.raises(ValueError):
        clean_daily(make_raw(time=["2024-07-01", "02/07/2024"]), "Testville")


def test_duplicate_dates_raise():
    with pytest.raises(ValueError, match="duplicate dates"):
        clean_daily(make_raw(time=["2024-07-01", "2024-07-01"]), "Testville")


def test_no_daily_data_raises():
    with pytest.raises(ValueError, match="no daily data"):
        clean_daily({"daily_units": UNITS}, "Testville")
