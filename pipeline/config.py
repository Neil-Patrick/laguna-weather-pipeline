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
# Note: on ERA5's ~25 km grid, Calamba and Los Baños fall in the same cell
# (14.25, 121.25) and get identical data. Both stay for the dashboard; analysis
# that combines towns counts that cell once.

# Weather model for ALL data. Open-Meteo's default switches from ERA5 to ECMWF IFS
# in 2017, a jump that would show up as a fake trend (IFS gives up to ~270 mm/year
# more rain here). Open-Meteo's docs recommend ERA5 or ERA5-Land only for
# multi-decade climate work; ERA5-Land has no rain data for this area.
WEATHER_MODEL = "era5"

# Daily run: re-fetch this many days. ERA5 runs ~5-7 days behind, so 14 days covers
# the newest published days plus revisions. Days not published yet come back empty
# and are skipped; a later run fills them in.
DAILY_LOOKBACK_DAYS = 14

# The archive rejects end dates past "yesterday", and its idea of yesterday may
# follow UTC (8 hours behind PHT). Stopping 2 days before today (PHT) is always safe.
ARCHIVE_LAG_DAYS = 2

# Weekly AI report: OpenRouter free models, tried in order until one returns a summary
# that passes validation. Free models get rate-limited and come and go, so keep backups;
# if all fail, the plain-number fallback report is posted instead.
# Checked 2026-11-26 against https://openrouter.ai/api/v1/models (":free" models).
REPORT_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "baidu/ernie-5.5-flash-preview:free",
]
LLM_TIMEOUT_SECONDS = 90
# Reasoning models "think" before answering and that uses tokens; with a small
# budget they run out and return an empty answer. 2000 leaves room for both.
LLM_MAX_TOKENS = 2000

# Default first day for a backfill (python -m pipeline.ingest --backfill).
# 1991 covers a full 30-year climate baseline (the WMO's 1991-2020 normals period),
# so a "rainy season is shifting" claim isn't just one unusual decade.
BACKFILL_START = "1991-01-01"
