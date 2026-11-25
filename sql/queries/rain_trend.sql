-- Question: the season's timing isn't clearly shifting (season_trend.sql), so is the
-- AMOUNT of rain changing? Per town, trends over 1991-2025 in:
--   annual_total      rain per calendar year
--   season_total      rain between that year's onset and end (rainy_seasons view)
--   dec_jan_total     rain in December + the following January (the "wetter Dec/Jan"
--                     lead from monthly_rain_per_year.sql), labelled by December's year
--   days_20mm_plus    days with >= 20 mm per year ("R20mm", a standard ETCCDI
--                     climate index for very heavy rain days)
--   wettest_day       the largest one-day total each year ("Rx1day", ETCCDI)
-- Only complete years/periods are used.
--
-- The statistics are the same as season_trend.sql (least-squares slope with a 95%
-- confidence interval using t = 2.03, plus Sen's slope). pct_per_decade expresses the
-- slope relative to the town's average, so towns with different rainfall compare fairly.

WITH calendar_years AS (
    SELECT location_id,
           extract(year FROM date)::int                    AS year,
           sum(precipitation_mm)                           AS annual_total,
           count(*) FILTER (WHERE precipitation_mm >= 20)  AS days_20mm_plus,
           max(precipitation_mm)                           AS wettest_day
    FROM daily_weather
    GROUP BY location_id, extract(year FROM date)
    HAVING count(*) = make_date(extract(year FROM date)::int + 1, 1, 1)
                    - make_date(extract(year FROM date)::int, 1, 1)
),
season_totals AS (
    SELECT s.location_id, s.season_year AS year, sum(w.precipitation_mm) AS season_total
    FROM rainy_seasons s
    JOIN daily_weather w
      ON w.location_id = s.location_id
     AND w.date BETWEEN s.onset_date AND s.end_date
    GROUP BY s.location_id, s.season_year
),
dec_jan AS (
    SELECT location_id,
           extract(year FROM date - INTERVAL '1 month')::int AS year,  -- Jan 2025 -> 2024
           sum(precipitation_mm)                             AS dec_jan_total
    FROM daily_weather
    WHERE extract(month FROM date) IN (12, 1)
    GROUP BY location_id, extract(year FROM date - INTERVAL '1 month')
    HAVING count(*) = 62                                    -- full December + full January
),
per_town AS (
    SELECT location_id, year, measure, sort_m, value
    FROM calendar_years
    CROSS JOIN LATERAL (VALUES
        ('annual_total',   1, annual_total),
        ('days_20mm_plus', 4, days_20mm_plus::double precision),
        ('wettest_day',    5, wettest_day)
    ) AS m(measure, sort_m, value)
    WHERE year <= 2025
    UNION ALL
    SELECT location_id, year, 'season_total', 2, season_total FROM season_totals
    UNION ALL
    SELECT location_id, year, 'dec_jan_total', 3, dec_jan_total FROM dec_jan WHERE year <= 2025
),
measures AS (
    SELECT l.name AS town, p.location_id AS sort_key, p.year AS x, p.measure, p.sort_m, p.value AS y
    FROM per_town p
    JOIN locations l ON l.id = p.location_id
    UNION ALL
    -- towns averaged per year first, each ERA5 grid cell counted once
    -- (Calamba and Los Baños share a cell, so Los Baños is left out of the average)
    SELECT 'All towns (4 grid cells)', 99, p.year, p.measure, p.sort_m, avg(p.value)
    FROM per_town p
    JOIN locations l ON l.id = p.location_id
    WHERE l.name <> 'Los Baños'
    GROUP BY p.year, p.measure, p.sort_m
),
least_squares AS (
    SELECT town, sort_key, measure, sort_m,
           regr_count(y, x)                                   AS n,
           avg(y)                                             AS mean_value,
           regr_slope(y, x)                                   AS slope,
           sqrt((regr_syy(y, x) - regr_sxy(y, x) ^ 2 / regr_sxx(y, x))
                / (regr_count(y, x) - 2) / regr_sxx(y, x))    AS slope_se
    FROM measures
    GROUP BY town, sort_key, measure, sort_m
),
sen AS (
    SELECT a.town, a.measure,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY (b.y - a.y) / (b.x - a.x)) AS sen_slope
    FROM measures a
    JOIN measures b ON b.town = a.town AND b.measure = a.measure AND b.x > a.x
    GROUP BY a.town, a.measure
)
SELECT ls.town,
       ls.measure,
       ls.n                                                       AS years,
       round(ls.mean_value::numeric, 1)                           AS average,
       round((ls.slope * 10)::numeric, 1)                         AS slope_per_decade,
       round((ls.slope * 10 / ls.mean_value * 100)::numeric, 1)   AS pct_per_decade,
       round(((ls.slope - 2.03 * ls.slope_se) * 10)::numeric, 1)  AS ci95_low,
       round(((ls.slope + 2.03 * ls.slope_se) * 10)::numeric, 1)  AS ci95_high,
       round((s.sen_slope * 10)::numeric, 1)                      AS sen_slope_per_decade,
       CASE WHEN ls.slope - 2.03 * ls.slope_se > 0 THEN 'increasing (clear)'
            WHEN ls.slope + 2.03 * ls.slope_se < 0 THEN 'decreasing (clear)'
            ELSE 'no clear trend'
       END                                                        AS verdict
FROM least_squares ls
JOIN sen s ON s.town = ls.town AND s.measure = ls.measure
ORDER BY ls.sort_key, ls.sort_m;
