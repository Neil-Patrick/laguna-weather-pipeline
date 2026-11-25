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

## Environment variables

Put these in a `.env` file at the repo root for local runs (it's gitignored). In GitHub Actions,
set them as repository secrets.

| Variable       | Used by          | What it is                                   |
|----------------|------------------|----------------------------------------------|
| `DATABASE_URL` | all pipeline jobs | Postgres connection string from Neon (`postgresql://...?sslmode=require`) |
