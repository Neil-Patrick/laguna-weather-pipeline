"""Turn Open-Meteo's raw JSON into checked rows shaped like the daily_weather table.

Two kinds of problems, handled differently:
- Structural (a variable missing, wrong units, lists of different lengths, bad dates):
  raise ValueError. The API changed and a human has to look, so the job must fail.
- A bad individual value (not a number, impossible range, min above max):
  store that one value as NULL and report it. One broken reading shouldn't throw
  away the rest of the day's data, and the report makes sure it isn't silent.

Try it from the repo root:  python -m pipeline.clean
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)

# Open-Meteo variable -> (our column, the unit we expect it in)
COLUMNS = {
    "temperature_2m_max": ("temp_max_c", "°C"),
    "temperature_2m_min": ("temp_min_c", "°C"),
    "precipitation_sum": ("precipitation_mm", "mm"),
    "precipitation_hours": ("rain_hours", "h"),
    "wind_speed_10m_max": ("wind_max_kmh", "km/h"),
}

# Plausibility bounds: wide enough to keep any real reading in lowland Laguna,
# narrow enough to catch garbage like 999 or -50.
VALID_RANGES = {
    "temp_max_c": (10, 45),
    "temp_min_c": (5, 40),
    "precipitation_mm": (0, 1500),
    "rain_hours": (0, 24),
    "wind_max_kmh": (0, 350),
}


def clean_daily(raw: dict, town: str) -> tuple[pd.DataFrame, list[str]]:
    """Return (rows, issues).

    rows: one row per day with columns date, temp_max_c, temp_min_c,
          precipitation_mm, rain_hours, wind_max_kmh. Missing values are NaN
          (they become NULL in the database, never 0).
    issues: one human-readable message per value that was rejected.
    """
    daily = raw.get("daily")
    units = raw.get("daily_units", {})
    _check_structure(daily, units, town)

    # format= makes a malformed date raise instead of being guessed at.
    dates = pd.to_datetime(daily["time"], format="%Y-%m-%d").date
    rows = pd.DataFrame({"date": dates})
    if rows["date"].duplicated().any():
        raise ValueError(f"{town}: response contains duplicate dates")

    issues: list[str] = []

    # 1. Types: anything that isn't a number (and isn't already missing) is rejected.
    for api_name, (column, _unit) in COLUMNS.items():
        original = pd.Series(daily[api_name], dtype=object)
        numbers = pd.to_numeric(original, errors="coerce")  # junk -> NaN
        not_numeric = original.notna() & numbers.isna()
        issues += _report(rows["date"], original, not_numeric, column, town, "is not a number")
        rows[column] = numbers.astype(float)

    # 2. Ranges. NaN is skipped: missing isn't the same as wrong.
    for column, (low, high) in VALID_RANGES.items():
        out_of_range = rows[column].notna() & ~rows[column].between(low, high)
        issues += _report(rows["date"], rows[column], out_of_range, column, town,
                          f"is outside {low}..{high}")
        rows.loc[out_of_range, column] = float("nan")

    # 3. Consistency: min above max means we can't trust either value.
    swapped = rows["temp_min_c"] > rows["temp_max_c"]  # comparisons with NaN are False
    for column in ("temp_min_c", "temp_max_c"):
        issues += _report(rows["date"], rows[column], swapped, column, town,
                          "conflicts with the other temperature (min > max)")
        rows.loc[swapped, column] = float("nan")

    return rows, issues


def _check_structure(daily: dict | None, units: dict, town: str) -> None:
    """Raise ValueError if the response doesn't have the shape we expect."""
    if not daily or "time" not in daily:
        raise ValueError(f"{town}: response has no daily data")
    expected_length = len(daily["time"])
    for api_name, (_column, unit) in COLUMNS.items():
        if api_name not in daily:
            raise ValueError(f"{town}: response is missing {api_name}")
        if units.get(api_name) != unit:
            raise ValueError(
                f"{town}: {api_name} is in {units.get(api_name)!r}, expected {unit!r}"
            )
        if len(daily[api_name]) != expected_length:
            raise ValueError(f"{town}: {api_name} has a different length from time")


def _report(dates, values, mask, column, town, reason) -> list[str]:
    """Log and return one message per flagged value."""
    messages = [
        f"{town} {day}: {column}={value!r} {reason}; stored as NULL"
        for day, value in zip(dates[mask], values[mask])
    ]
    for message in messages:
        log.warning(message)
    return messages


if __name__ == "__main__":
    from pipeline.config import LOCATIONS
    from pipeline.fetch import fetch_daily

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    town = LOCATIONS[0]  # San Pablo
    raw = fetch_daily(town["latitude"], town["longitude"], "2024-07-01", "2024-07-31")
    rows, issues = clean_daily(raw, town["name"])

    print(rows.to_string(index=False))
    print(f"\n{len(rows)} rows, {len(issues)} rejected values, "
          f"{int(rows.isna().sum().sum())} missing values")
