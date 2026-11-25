# PLAN: Laguna Weather Pipeline

## Context
- Owner: CS student (Intelligent Systems, grad 2027), moving from web dev into data/AI/automation.
- Purpose: first SOLO portfolio project; fills the gap where Python/SQL/Postgres are listed as skills
  but no project uses them. Will be added to the portfolio site as project #4.
- Guiding question: **"Is Laguna's rainy season shifting?"** (10+ years of data, 5 towns)

## What it does
Daily: fetch weather → clean/validate → upsert to Postgres.
Weekly (Mon 9 AM PHT): SQL computes this week vs last → LLM writes summary → Discord.
Dashboard: Streamlit, town picker, temp/rain charts, rainy-season view, latest report,
"Data last updated" date.

## Stack (decided)
Python 3.13 + venv + pinned requirements.txt (pip freeze) · python-dotenv · requests · pandas ·
psycopg v3 (raw SQL, no ORM) · Neon Postgres (free) · GitHub Actions cron ·
OpenRouter free model · Discord webhook · Streamlit + Community Cloud · pytest.
Data source v1: Open-Meteo (forecast + archive APIs, no key). v2 later: DOE weekly fuel
prices (PDFs, pdfplumber).

## Layout
pipeline/ (db.py, init_db.py, fetch.py, clean.py, report.py) · sql/001_schema.sql ·
sql/queries/ · dashboard/app.py · tests/ · .github/workflows/ (daily.yml, weekly.yml, keepalive.yml)
Run modules from repo root with `python -m pipeline.<name>`.

## Schema (sql/001_schema.sql, idempotent)
- locations(id, name UNIQUE, latitude, longitude): San Pablo, Calamba, Santa Cruz,
  Los Baños, Biñan (approx. coords, verify)
- daily_weather(location_id, date, temp_max_c, temp_min_c, precipitation_mm, rain_hours,
  wind_max_kmh, fetched_at). PK (location_id, date), so re-runs upsert, no duplicates
- reports(id, week_start UNIQUE, summary_text, model, created_at)

## Phases
- [x] 0 Setup: venv, deps, .gitignore, .env (DATABASE_URL), schema, `python -m pipeline.init_db`
      prints Postgres version + "Locations: 5" (twice, still 5)
- [x] 1 Collect + backfill: fetch.py/clean.py (types, ranges, missing values); backfill from 1991
      (30-yr climate baseline) from archive API. Done: ~65k rows, a real "rainiest month per town" query works
- [ ] 2 Automation: daily.yml, re-fetch last 7 days each run (archive lag), secrets in GH Actions,
      fail loudly. Done: 3 unattended runs in a row
- [x] 3 Analysis: 5–8 SQL queries (window functions, rolling 7-day rain, cross-town comparison,
      rainy-season start/end per year). Done: 2–3 plain-language findings answering the question
- [x] 4 Weekly AI report: LLM gets ONLY computed numbers (never does math), output validated,
      fallback to plain-number report, model name in config. Done: first report on Discord
- [x] 5 Dashboard: Streamlit, deployed, public link
- [ ] 6 Polish: README (architecture diagram, setup, findings, design decisions), pytest for
      clean.py + report logic, add to portfolio

## Future-proofing (build these in)
- keepalive.yml: monthly commit so GitHub doesn't disable cron after 60 days without repo activity
- Discord alert on any job failure; "last updated" shown on dashboard
- Idempotent jobs: any re-run is safe, recovery takes one click
- Pinned deps; tests catch breakage on deliberate upgrades
- Known/accepted: Streamlit app sleeps when idle (wakes in ~30s); Neon pauses when idle (auto-wakes)

## Working rules
- Owner does ALL git commits/pushes; Claude suggests commit messages only.
- Secrets only in .env (gitignored) or GitHub secrets; never in code or chat. No .env.example;
  document variables in README.
- Owner creates all accounts/keys (Neon, Discord webhook, OpenRouter).
- Explain design decisions (SQL, idempotency, LLM safeguards) so the owner can defend them in
  interviews. Teach, don't just generate.
- Ask before adding dependencies beyond the stack above.
