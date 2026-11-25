"""Download daily weather from the Open-Meteo archive API. Fetch only: cleaning is clean.py's job.

Try it from the repo root:  python -m pipeline.fetch
"""

import time

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# The daily variables we ask for. Open-Meteo's default units already match our
# columns: °C, mm, hours, km/h.
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
]

TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}  # rate limit or server trouble: worth retrying


def fetch_daily(latitude: float, longitude: float, start_date: str, end_date: str) -> dict:
    """Return Open-Meteo's raw JSON for one location and an inclusive date range (YYYY-MM-DD)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "Asia/Manila",  # days run midnight to midnight PHT, not UTC
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(ARCHIVE_URL, params=params, timeout=TIMEOUT_SECONDS)
            if response.status_code in RETRY_STATUS_CODES and attempt < MAX_ATTEMPTS:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status()  # any other 4xx is our bug: fail immediately
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as error:
            is_retryable = not isinstance(error, requests.HTTPError) or (
                error.response is not None and error.response.status_code in RETRY_STATUS_CODES
            )
            if not is_retryable or attempt == MAX_ATTEMPTS:
                raise
            wait = 2**attempt  # 2s, then 4s
            print(f"Attempt {attempt} failed ({error}); retrying in {wait}s")
            time.sleep(wait)

    raise AssertionError("unreachable")  # the loop always returns or raises


if __name__ == "__main__":
    from pipeline.config import LOCATIONS

    town = LOCATIONS[0]  # San Pablo
    data = fetch_daily(town["latitude"], town["longitude"], "2024-07-01", "2024-07-31")

    print(f"{town['name']}: grid point {data['latitude']}, {data['longitude']} "
          f"(elevation {data.get('elevation')} m)")
    print("Units:", data["daily_units"])
    daily = data["daily"]
    for i, day in enumerate(daily["time"]):
        values = [daily[name][i] for name in DAILY_VARIABLES]
        print(day, values)
