-- Question: what has the weather been like over the last 90 days of data, per town?
-- Feeds the dashboard's "recent weather" charts. The 7-day rolling total uses the same
-- RANGE window as rolling_7day_rain.sql; it's computed over 6 extra days so the first
-- shown day has a full 7-day window. Days ERA5 hasn't published yet are excluded.

WITH latest AS (
    SELECT max(date) AS last_day
    FROM daily_weather
    WHERE precipitation_mm IS NOT NULL
),
window_days AS (
    SELECT w.location_id, w.date, w.precipitation_mm, w.temp_max_c, w.temp_min_c,
           sum(w.precipitation_mm) OVER (
               PARTITION BY w.location_id ORDER BY w.date
               RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
           ) AS rain_7d_mm
    FROM daily_weather w, latest
    WHERE w.date BETWEEN latest.last_day - 95 AND latest.last_day
)
SELECT l.name AS town, d.date, d.precipitation_mm, d.rain_7d_mm, d.temp_max_c, d.temp_min_c
FROM window_days d
JOIN locations l ON l.id = d.location_id
CROSS JOIN latest
WHERE d.date > latest.last_day - 90
ORDER BY l.id, d.date;
