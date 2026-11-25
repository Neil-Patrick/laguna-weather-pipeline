-- Question: how did one week compare, per town, with the week before and with normal?
-- Feeds the weekly report (pipeline/report.py). Every number the LLM may use is
-- computed here, including the differences, so the LLM never does arithmetic.
--
-- Parameter: %(week_start)s, a Monday (psycopg named parameter; report.py fills it in).
-- normal_* = average over 1991-2020 of the same 7 calendar days (same day-of-year),
-- the WMO standard normals period, as in the rainy_seasons view.
-- A "rain day" is >= 1 mm, as in monthly_rain_per_year.sql.

WITH params AS (
    SELECT %(week_start)s::date AS week_start
),
this_week AS (
    SELECT w.location_id,
           sum(w.precipitation_mm)                           AS rain_mm,
           count(*) FILTER (WHERE w.precipitation_mm >= 1)   AS rain_days,
           max(w.temp_max_c)                                 AS hottest_c,
           min(w.temp_min_c)                                 AS coolest_c,
           max(w.wind_max_kmh)                               AS strongest_wind_kmh
    FROM daily_weather w, params p
    WHERE w.date BETWEEN p.week_start AND p.week_start + 6
    GROUP BY w.location_id
),
last_week AS (
    SELECT w.location_id, sum(w.precipitation_mm) AS rain_mm
    FROM daily_weather w, params p
    WHERE w.date BETWEEN p.week_start - 7 AND p.week_start - 1
    GROUP BY w.location_id
),
normal AS (
    -- the same 7 days of the year (by day-of-year offset, so 29 Feb can't break it)
    SELECT w.location_id,
           sum(w.precipitation_mm) / 30.0                                 AS rain_mm,
           count(*) FILTER (WHERE w.precipitation_mm >= 1) / 30.0         AS rain_days
    FROM daily_weather w, params p,
         generate_series(1991, 2020) AS y(year)
    WHERE w.date BETWEEN make_date(y.year, 1, 1) + (extract(doy FROM p.week_start)::int - 1)
                     AND make_date(y.year, 1, 1) + (extract(doy FROM p.week_start)::int - 1) + 6
    GROUP BY w.location_id
)
SELECT l.name                                               AS town,
       round(t.rain_mm::numeric, 1)                         AS rain_mm,
       t.rain_days,
       round(lw.rain_mm::numeric, 1)                        AS last_week_rain_mm,
       round((t.rain_mm - lw.rain_mm)::numeric, 1)          AS change_from_last_week_mm,
       round(n.rain_mm::numeric, 1)                         AS normal_rain_mm,
       round(n.rain_days::numeric, 1)                       AS normal_rain_days,
       CASE WHEN n.rain_mm > 0
            THEN round((t.rain_mm / n.rain_mm * 100)::numeric) END AS percent_of_normal_rain,
       round(t.hottest_c::numeric, 1)                       AS hottest_c,
       round(t.coolest_c::numeric, 1)                       AS coolest_c,
       round(t.strongest_wind_kmh::numeric, 1)              AS strongest_wind_kmh
FROM this_week t
JOIN last_week lw ON lw.location_id = t.location_id
JOIN normal n     ON n.location_id  = t.location_id
JOIN locations l  ON l.id           = t.location_id
ORDER BY l.id;
