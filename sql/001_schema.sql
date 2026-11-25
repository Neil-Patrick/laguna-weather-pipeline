-- 001_schema.sql: base tables. Idempotent: safe to run any number of times.
-- Never edit this file after it has been applied; add 002_*.sql instead.

-- One row per town we track. Rows come from pipeline/config.py (seeded by init_db).
CREATE TABLE IF NOT EXISTS locations (
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    latitude  DOUBLE PRECISION NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180)
);

-- One row per town per day. The primary key is the natural key, so re-fetching
-- a day updates that row (upsert) instead of creating a duplicate.
-- Measurements are nullable: NULL means "missing", which is not the same as 0.
CREATE TABLE IF NOT EXISTS daily_weather (
    location_id      INTEGER NOT NULL REFERENCES locations (id),
    date             DATE    NOT NULL,
    temp_max_c       DOUBLE PRECISION,
    temp_min_c       DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION CHECK (precipitation_mm >= 0),
    rain_hours       DOUBLE PRECISION CHECK (rain_hours BETWEEN 0 AND 24),
    wind_max_kmh     DOUBLE PRECISION CHECK (wind_max_kmh >= 0),
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, date),
    CHECK (temp_min_c <= temp_max_c)
);

-- One weekly report per week. week_start is always a Monday.
-- model records which LLM wrote it ('fallback' when the plain-number report was used).
CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    week_start   DATE NOT NULL UNIQUE CHECK (EXTRACT(ISODOW FROM week_start) = 1),
    summary_text TEXT NOT NULL,
    model        TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
