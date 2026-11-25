"""Project settings. Data lives here; logic lives in the other modules."""

# Coordinates from the Open-Meteo geocoding API (GeoNames data), checked 2026-11-25.
# For each town we took the most populated match in the Province of Laguna,
# skipping smaller barangays with the same name.
LOCATIONS = [
    {"name": "San Pablo",  "latitude": 14.06830, "longitude": 121.32560},
    {"name": "Calamba",    "latitude": 14.21167, "longitude": 121.16528},
    {"name": "Santa Cruz", "latitude": 14.28140, "longitude": 121.41610},
    {"name": "Los Baños",  "latitude": 14.17025, "longitude": 121.24181},
    {"name": "Biñan",      "latitude": 14.34267, "longitude": 121.08071},
]

# Daily run: re-fetch this many days, so values the archive revises get updated.
DAILY_LOOKBACK_DAYS = 7

# The archive rejects end dates past "yesterday", and its idea of yesterday may
# follow UTC (8 hours behind PHT). Stopping 2 days before today (PHT) is always safe.
ARCHIVE_LAG_DAYS = 2

# Default first day for a backfill (python -m pipeline.ingest --backfill).
# 1991 covers a full 30-year climate baseline (the WMO's 1991-2020 normals period),
# so a "rainy season is shifting" claim isn't just one unusual decade.
BACKFILL_START = "1991-01-01"
