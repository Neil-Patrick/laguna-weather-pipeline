"""Fetch -> clean -> load for every town over a date range. Safe to re-run.

From the repo root:
    python -m pipeline.ingest                    # daily run: the last 7 available days
    python -m pipeline.ingest --backfill         # everything since BACKFILL_START
    python -m pipeline.ingest --start 2020-01-01 --end 2020-12-31   # any range
"""

import argparse
import datetime as dt
import logging
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.clean import clean_daily
from pipeline.config import ARCHIVE_LAG_DAYS, BACKFILL_START, DAILY_LOOKBACK_DAYS, LOCATIONS
from pipeline.db import get_connection
from pipeline.fetch import fetch_daily
from pipeline.load import get_location_ids, upsert_daily_weather

log = logging.getLogger("pipeline.ingest")

MANILA = ZoneInfo("Asia/Manila")


def latest_available_date() -> dt.date:
    """The newest day it's safe to ask the archive for."""
    return dt.datetime.now(MANILA).date() - dt.timedelta(days=ARCHIVE_LAG_DAYS)


def year_chunks(start: dt.date, end: dt.date):
    """Split [start, end] into pieces that never cross a year boundary."""
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(dt.date(chunk_start.year, 12, 31), end)
        yield chunk_start, chunk_end
        chunk_start = chunk_end + dt.timedelta(days=1)


def unpublished_days(rows: pd.DataFrame) -> pd.Series:
    """True for days with no measurements at all (not published yet by ERA5).

    rain_hours is left out on purpose: for unpublished days the API returns
    precipitation_hours = 0.0 instead of null, so counting it would make an empty
    day look like real data (this happened once; see tests/test_ingest.py).
    """
    measured = ["temp_max_c", "temp_min_c", "precipitation_mm", "wind_max_kmh"]
    return rows[measured].isna().all(axis=1)


def ingest(start: dt.date, end: dt.date) -> dict[str, int]:
    """Load every town for [start, end]. Any error stops the run and the process exits non-zero."""
    totals = {"rows": 0, "rejected_values": 0, "empty_days": 0}

    with get_connection() as conn:
        location_ids = get_location_ids(conn)
        missing = [town["name"] for town in LOCATIONS if town["name"] not in location_ids]
        if missing:
            raise RuntimeError(f"Towns missing from the database, run init_db first: {missing}")

        for town in LOCATIONS:
            for chunk_start, chunk_end in year_chunks(start, end):
                raw = fetch_daily(
                    town["latitude"], town["longitude"],
                    chunk_start.isoformat(), chunk_end.isoformat(),
                )
                rows, issues = clean_daily(raw, town["name"])

                # Skip (and say so) days with no measurements, rather than store
                # a row of NULLs. Normal for the newest days: ERA5 lags ~5-7 days.
                empty = unpublished_days(rows)
                if empty.any():
                    log.info("%s: %d days not published yet (no data), skipped: %s..%s",
                             town["name"], int(empty.sum()),
                             rows["date"][empty].min(), rows["date"][empty].max())

                sent = upsert_daily_weather(conn, location_ids[town["name"]], rows[~empty])
                conn.commit()  # save each chunk as soon as it's loaded
                log.info("%s %s..%s: %d rows, %d rejected values",
                         town["name"], chunk_start, chunk_end, sent, len(issues))

                totals["rows"] += sent
                totals["rejected_values"] += len(issues)
                totals["empty_days"] += int(empty.sum())

    return totals


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch, clean and load daily weather.")
    parser.add_argument("--backfill", action="store_true",
                        help=f"start from BACKFILL_START ({BACKFILL_START})")
    parser.add_argument("--start", type=dt.date.fromisoformat, help="first day, YYYY-MM-DD")
    parser.add_argument("--end", type=dt.date.fromisoformat, help="last day, YYYY-MM-DD")
    args = parser.parse_args(argv)

    newest = latest_available_date()
    end = args.end or newest
    if args.backfill:
        start = dt.date.fromisoformat(BACKFILL_START)
    else:
        start = args.start or end - dt.timedelta(days=DAILY_LOOKBACK_DAYS - 1)
    if end > newest:
        parser.error(f"--end can be at most {newest} (the archive lags behind)")
    if start > end:
        parser.error(f"start {start} is after end {end}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Ingesting %s..%s for %d towns", start, end, len(LOCATIONS))
    totals = ingest(start, end)
    log.info("Done: %(rows)d rows upserted, %(rejected_values)d rejected values, "
             "%(empty_days)d empty days skipped", totals)


if __name__ == "__main__":
    main()
