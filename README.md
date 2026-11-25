# laguna-weather-pipeline

A daily weather pipeline for five towns in Laguna, Philippines, built to answer one question:
**is Laguna's rainy season shifting?** (Work in progress; see [PLAN.md](PLAN.md).)

## Findings so far (1991–2025)

1. **The rainy season's timing has not clearly shifted.** Onset averages 22 May with a trend of
   −0.7 days/decade (95% range −6.3 to +4.9). The end averages 31 Oct and leans later
   (+6.0 days/decade), but the 95% range (−3.2 to +15.2) includes zero.
   *Source: `sql/queries/season_trend.sql`.*
2. **December–January rain is clearly increasing**, by about 25% per decade averaged across the
   towns (+59 mm/decade on a 235 mm average; 95% range +14 to +104). This holds in every grid cell,
   and Sen's slope (robust to outliers) agrees. *Source: `sql/queries/rain_trend.sql`.*
3. **Annual rain is rising modestly**, about +6% per decade on average (95% range +12 to +273 mm/decade).
   That's clear in 3 of the 4 grid cells; San Pablo is borderline. *Source: `sql/queries/rain_trend.sql`.*

Together: the season isn't moving, but late-year rain after the main season is increasing.

**Method and limits.** Season dates use the anomalous-accumulation method (Liebmann & Marengo, 2001);
see `sql/002_views.sql`. They land a median 6 days before PAGASA's declared onset (2016–2024). PAGASA's
declaration is national, so the comparison is a sanity check, not a target. The data is ERA5
reanalysis (a weather model's reconstruction, ~25 km grid), not rain-gauge readings. Calamba and
Los Baños share one grid cell and get identical rain, so analyses that combine towns count it once.

## Data source

Open-Meteo's archive API, **ERA5 model only** (`WEATHER_MODEL` in `pipeline/config.py`). Open-Meteo's
default switches from ERA5 to ECMWF IFS in 2017, and IFS gives up to ~270 mm/year more rain here.
That switch would show up as a fake "wetter after 2017" trend, so every year uses ERA5. ERA5
publishes about 5–7 days behind.

## Setup (Windows / PowerShell)

Requires Python 3.13 and a Postgres database (the project uses a free Neon instance).

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pipeline.init_db   # creates tables and seeds the 5 towns; safe to re-run
```

## Running the pipeline

```powershell
python -m pipeline.ingest              # daily run: re-fetches the last 14 days (unpublished days are skipped)
python -m pipeline.ingest --backfill   # full history since 1991 (~65k rows, a few minutes)
python -m pipeline.ingest --start 2020-01-01 --end 2020-12-31   # any range
```

Every run is an upsert, so re-running any command is safe. ERA5 data runs about 5–7 days behind.

## Environment variables

Put these in a `.env` file at the repo root for local runs (it's gitignored). In GitHub Actions,
set them as repository secrets.

| Variable       | Used by          | What it is                                   |
|----------------|------------------|----------------------------------------------|
| `DATABASE_URL` | all pipeline jobs | Postgres connection string from Neon (`postgresql://...?sslmode=require`) |
| `DISCORD_WEBHOOK_URL` | failure alerts (GitHub Actions) | Discord channel webhook (`https://discord.com/api/webhooks/...`) |

## Automation (GitHub Actions)

| Workflow | When | What it does |
|---|---|---|
| `daily.yml` | every day 06:17 PHT | `python -m pipeline.ingest` (last 14 days); Discord alert on failure |
| `keepalive.yml` | 1st of each month | empty commit if the repo has been quiet 25+ days, so GitHub doesn't disable the schedules after 60 |

Both can be started by hand from the Actions tab (**Run workflow**). `daily.yml` has a **fire drill**
option that fails on purpose to test the Discord alert.
