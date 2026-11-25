# laguna-weather-pipeline

A daily weather pipeline for five towns in Laguna, Philippines, built to answer one question:
**is Laguna's rainy season shifting?** (Work in progress; see [PLAN.md](PLAN.md).)

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
python -m pipeline.ingest              # daily run: re-fetches the last 7 available days
python -m pipeline.ingest --backfill   # full history since 1991 (~65k rows, a few minutes)
python -m pipeline.ingest --start 2020-01-01 --end 2020-12-31   # any range
```

Every run is an upsert, so re-running any command is safe. The archive data runs about 2 days behind.

## Environment variables

Put these in a `.env` file at the repo root for local runs (it's gitignored). In GitHub Actions,
set them as repository secrets.

| Variable       | Used by          | What it is                                   |
|----------------|------------------|----------------------------------------------|
| `DATABASE_URL` | all pipeline jobs | Postgres connection string from Neon (`postgresql://...?sslmode=require`) |
