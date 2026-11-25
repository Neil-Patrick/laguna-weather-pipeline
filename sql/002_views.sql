-- 002_views.sql: shared analysis logic, defined once. Idempotent (CREATE OR REPLACE).
-- Never edit this file after it has been applied; change a view with a new numbered file.
-- Note: CREATE OR REPLACE VIEW can add columns at the end, but can't rename,
-- reorder or retype existing ones; that needs DROP VIEW + CREATE in a new file.

-- rainy_seasons: rainy-season onset and end, one row per town and season year.
--
-- Method: anomalous accumulation (Liebmann & Marengo, 2001, J. Climate).
--   For each day: anomaly = that day's rain - the town's average daily rain.
--   Keep a running total of the anomaly through the "season year".
--   In the dry season days are below average, so the total falls;
--   in the rainy season they're above average, so it rises.
--     onset_date = the day after the running total's lowest point
--     end_date   = the day of its highest point
--
-- Why this method: each town is compared with its own average, so the model's
-- bias toward too many light-rain days largely cancels out. PAGASA's threshold
-- rule fired ~31 days early on this data (sql/queries/rainy_season_onset.sql);
-- this method is a median 5 days before PAGASA's declarations, 2016-2024.
--
-- Search windows (OUR choice, not taken from a paper): the plain method breaks in
-- drier-than-average years, where the running total drifts down all year and its
-- "lowest point" lands at the end of the year. So:
--   1. Find the town's typical (1991-2020 average) onset and end.
--   2. Each year's onset = lowest point within +-60 days of the typical onset.
--   3. Each year's end   = highest point between that year's onset and 31 Jan.
--
-- Other choices:
--   - Average daily rain over 1991-2020 (the WMO standard normals period): a fixed
--     baseline that doesn't move as new data arrives.
--   - The season year runs 1 Feb (dry season) to 31 Jan, labelled by its Feb year,
--     so a season ending in January isn't cut off at 31 December.
--   - Only complete season years appear.
--   - onset_day / end_day count days since 1 Feb, for comparing years.

CREATE OR REPLACE VIEW rainy_seasons AS
WITH baseline AS (
    SELECT location_id, avg(precipitation_mm) AS mean_daily_mm
    FROM daily_weather
    WHERE date BETWEEN '1991-01-01' AND '2020-12-31'
    GROUP BY location_id
),
season_days AS (
    SELECT w.location_id,
           w.date,
           -- Feb..Jan -> the year of its February (31 Jan 2025 belongs to season 2024)
           extract(year FROM w.date - INTERVAL '1 month')::int AS season_year,
           w.precipitation_mm - b.mean_daily_mm                AS anomaly_mm
    FROM daily_weather w
    JOIN baseline b ON b.location_id = w.location_id
),
accumulated AS (
    SELECT location_id, season_year, date,
           date - make_date(season_year, 2, 1) AS day_of_season,   -- 0 = 1 Feb
           sum(anomaly_mm) OVER (PARTITION BY location_id, season_year ORDER BY date)
               AS cumulative_anomaly_mm
    FROM season_days
),
complete_seasons AS (
    SELECT location_id, season_year
    FROM accumulated
    GROUP BY location_id, season_year
    HAVING count(*) = make_date(season_year + 1, 2, 1) - make_date(season_year, 2, 1)
),
-- The typical season: average running total per day of season over 1991-2020.
typical_curve AS (
    SELECT a.location_id, a.day_of_season, avg(a.cumulative_anomaly_mm) AS avg_cumulative_mm
    FROM accumulated a
    JOIN complete_seasons c USING (location_id, season_year)
    WHERE a.season_year BETWEEN 1991 AND 2019   -- seasons that start and end within 1991-2020
      AND a.day_of_season < 365                 -- day 365 exists only in leap seasons
    GROUP BY a.location_id, a.day_of_season
),
typical AS (
    SELECT location_id,
           (array_agg(day_of_season ORDER BY avg_cumulative_mm ASC,  day_of_season))[1] + 1 AS typical_onset_day,
           (array_agg(day_of_season ORDER BY avg_cumulative_mm DESC, day_of_season))[1]     AS typical_end_day
    FROM typical_curve
    GROUP BY location_id
),
onsets AS (
    SELECT a.location_id, a.season_year,
           (array_agg(a.date ORDER BY a.cumulative_anomaly_mm ASC, a.date))[1] + 1 AS onset_date
    FROM accumulated a
    JOIN complete_seasons c USING (location_id, season_year)
    JOIN typical t USING (location_id)
    WHERE a.day_of_season + 1 BETWEEN t.typical_onset_day - 60 AND t.typical_onset_day + 60
    GROUP BY a.location_id, a.season_year
),
ends AS (
    SELECT a.location_id, a.season_year,
           (array_agg(a.date ORDER BY a.cumulative_anomaly_mm DESC, a.date))[1] AS end_date
    FROM accumulated a
    JOIN onsets o USING (location_id, season_year)
    WHERE a.date >= o.onset_date
    GROUP BY a.location_id, a.season_year
)
SELECT o.location_id,
       l.name                                          AS town,
       o.season_year,
       o.onset_date,
       e.end_date,
       e.end_date - o.onset_date                       AS length_days,
       o.onset_date - make_date(o.season_year, 2, 1)   AS onset_day,
       e.end_date   - make_date(o.season_year, 2, 1)   AS end_day,
       make_date(2001, 2, 1) + t.typical_onset_day     AS typical_onset,   -- shown as a date in 2001
       make_date(2001, 2, 1) + t.typical_end_day       AS typical_end
FROM onsets o
JOIN ends e      USING (location_id, season_year)
JOIN typical t   USING (location_id)
JOIN locations l ON l.id = o.location_id;
