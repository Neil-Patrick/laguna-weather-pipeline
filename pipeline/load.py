"""Upsert cleaned rows into daily_weather. Safe to re-run: the same day is updated, never duplicated.

Try it from the repo root:  python -m pipeline.load
"""

import pandas as pd

WEATHER_COLUMNS = ["date", "temp_max_c", "temp_min_c", "precipitation_mm", "rain_hours", "wind_max_kmh"]

# ON CONFLICT targets the primary key (location_id, date): a new day is inserted,
# an existing day is overwritten with the latest fetch. EXCLUDED is the row we
# tried to insert, so fetched_at = EXCLUDED.fetched_at records when we last saw it.
UPSERT_DAILY_WEATHER = """
    INSERT INTO daily_weather
        (location_id, date, temp_max_c, temp_min_c, precipitation_mm, rain_hours, wind_max_kmh)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (location_id, date) DO UPDATE SET
        temp_max_c       = EXCLUDED.temp_max_c,
        temp_min_c       = EXCLUDED.temp_min_c,
        precipitation_mm = EXCLUDED.precipitation_mm,
        rain_hours       = EXCLUDED.rain_hours,
        wind_max_kmh     = EXCLUDED.wind_max_kmh,
        fetched_at       = EXCLUDED.fetched_at
"""


def get_location_ids(conn) -> dict[str, int]:
    """Map town name -> locations.id, as stored in the database."""
    return dict(conn.execute("SELECT name, id FROM locations").fetchall())


def upsert_daily_weather(conn, location_id: int, rows: pd.DataFrame) -> int:
    """Upsert one town's cleaned rows. Returns how many rows were sent."""
    weather = rows[WEATHER_COLUMNS]
    # pandas uses NaN for missing; psycopg sends None as SQL NULL.
    weather = weather.astype(object).where(weather.notna(), None)
    params = [(location_id, *values) for values in weather.itertuples(index=False, name=None)]
    with conn.cursor() as cur:
        cur.executemany(UPSERT_DAILY_WEATHER, params)
    return len(params)


if __name__ == "__main__":
    from pipeline.clean import clean_daily
    from pipeline.config import LOCATIONS
    from pipeline.db import get_connection
    from pipeline.fetch import fetch_daily

    town = LOCATIONS[0]  # San Pablo
    raw = fetch_daily(town["latitude"], town["longitude"], "2024-07-01", "2024-07-31")
    rows, issues = clean_daily(raw, town["name"])

    with get_connection() as conn:
        location_id = get_location_ids(conn)[town["name"]]
        sent = upsert_daily_weather(conn, location_id, rows)
        stored = conn.execute(
            "SELECT count(*) FROM daily_weather WHERE location_id = %s", (location_id,)
        ).fetchone()[0]
    print(f"{town['name']}: sent {sent} rows, {stored} stored for this town")
