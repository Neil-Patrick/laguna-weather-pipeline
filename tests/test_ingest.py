"""Tests for the ingest and load helpers. No network or database needed."""

import datetime as dt
import math

import pandas as pd

from pipeline.ingest import unpublished_days, year_chunks
from pipeline.load import to_params

D = dt.date
NAN = float("nan")


# ---------- year_chunks ----------

def test_chunks_split_at_year_boundaries():
    assert list(year_chunks(D(2023, 11, 15), D(2025, 2, 3))) == [
        (D(2023, 11, 15), D(2023, 12, 31)),
        (D(2024, 1, 1), D(2024, 12, 31)),
        (D(2025, 1, 1), D(2025, 2, 3)),
    ]


def test_range_inside_one_year_is_one_chunk():
    assert list(year_chunks(D(2024, 3, 1), D(2024, 3, 7))) == [(D(2024, 3, 1), D(2024, 3, 7))]


def test_new_year_edge():
    assert list(year_chunks(D(2024, 12, 31), D(2025, 1, 1))) == [
        (D(2024, 12, 31), D(2024, 12, 31)),
        (D(2025, 1, 1), D(2025, 1, 1)),
    ]


def test_single_day():
    assert list(year_chunks(D(2024, 2, 29), D(2024, 2, 29))) == [(D(2024, 2, 29), D(2024, 2, 29))]


# ---------- unpublished_days ----------

def rows(**columns) -> pd.DataFrame:
    base = {"date": [D(2026, 11, 19), D(2026, 11, 20)],
            "temp_max_c": [31.6, NAN], "temp_min_c": [25.4, NAN],
            "precipitation_mm": [0.6, NAN], "rain_hours": [6.0, NAN],
            "wind_max_kmh": [19.8, NAN]}
    base.update(columns)
    return pd.DataFrame(base)


def test_day_with_no_measurements_is_unpublished():
    assert unpublished_days(rows()).tolist() == [False, True]


def test_era5_quirk_rain_hours_zero_still_counts_as_unpublished():
    # Regression test: for unpublished days the API returns precipitation_hours = 0.0
    # while everything else is null. Before the fix, these were stored as real rows.
    assert unpublished_days(rows(rain_hours=[6.0, 0.0])).tolist() == [False, True]


def test_partly_missing_day_is_kept():
    # one real measurement is enough to keep the day (its NULLs stay NULL)
    assert unpublished_days(rows(precipitation_mm=[0.6, 12.0])).tolist() == [False, False]


# ---------- to_params (load.py) ----------

def test_nan_becomes_none_so_postgres_stores_null():
    params = to_params(3, rows())
    assert params[0] == (3, D(2026, 11, 19), 31.6, 25.4, 0.6, 6.0, 19.8)
    assert params[1][0:2] == (3, D(2026, 11, 20))
    assert all(value is None for value in params[1][2:])   # None, not float NaN
    assert not any(isinstance(v, float) and math.isnan(v) for p in params for v in p)
