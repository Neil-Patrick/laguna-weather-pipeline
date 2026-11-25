-- Question: is Laguna's rainy season shifting? Per town, is the onset, the end, or
-- the length of the season trending over 1991-2025?
--
-- For each town and measure (onset day, end day, length), we fit a straight line
-- through the 35 yearly values and report its slope in days per decade:
--   slope_per_decade: least-squares slope (regr_slope), x10.
--   ci95_low/high:    95% confidence interval of that slope. If it includes 0, the
--                     data can't distinguish the trend from year-to-year noise.
--                     Uses t = 2.03 (the t-distribution value for ~35 years, 33 degrees
--                     of freedom; Postgres has no t-distribution function).
--   sen_slope_per_decade: Sen's slope = median of the slopes between every pair of
--                     years. Robust: one freak year can't swing it. Standard in
--                     climate trend studies. If it disagrees with the least-squares
--                     slope, outliers are driving the result.
-- "All towns" averages per year first, counting each ERA5 grid cell once: Calamba and
-- Los Baños share a cell (identical data), so Los Baños is left out of the average.
-- The towns are neighbours with strongly correlated weather, so they are NOT
-- independent pieces of evidence.
-- Positive = later (onset/end) or longer (length).

WITH yearly AS (
    SELECT town, location_id AS sort_key, season_year, onset_day, end_day, length_days
    FROM rainy_seasons
    UNION ALL
    SELECT 'All towns (4 grid cells)', 99, season_year,
           avg(onset_day), avg(end_day), avg(length_days)
    FROM rainy_seasons
    WHERE town <> 'Los Baños'   -- same ERA5 grid cell as Calamba
    GROUP BY season_year
),
measures AS (
    SELECT y.town, y.sort_key, y.season_year AS x, m.measure, m.sort_m, m.value AS y
    FROM yearly y
    CROSS JOIN LATERAL (VALUES
        ('onset',  1, y.onset_day::double precision),
        ('end',    2, y.end_day::double precision),
        ('length', 3, y.length_days::double precision)
    ) AS m(measure, sort_m, value)
),
least_squares AS (
    SELECT town, sort_key, measure, sort_m,
           regr_count(y, x)                                   AS n,
           avg(y)                                             AS mean_day,
           regr_slope(y, x)                                   AS slope,
           -- standard error of the slope, from Postgres's built-in sums of squares
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
       ls.n                                                    AS years,
       CASE WHEN ls.measure = 'length'
            THEN round(ls.mean_day)::text || ' days'
            ELSE to_char(make_date(2001, 2, 1) + round(ls.mean_day)::int, 'DD Mon')
       END                                                     AS average,
       round((ls.slope * 10)::numeric, 1)                      AS slope_per_decade,
       round(((ls.slope - 2.03 * ls.slope_se) * 10)::numeric, 1) AS ci95_low,
       round(((ls.slope + 2.03 * ls.slope_se) * 10)::numeric, 1) AS ci95_high,
       round((s.sen_slope * 10)::numeric, 1)                   AS sen_slope_per_decade,
       CASE WHEN ls.slope - 2.03 * ls.slope_se > 0 THEN 'later/longer (clear)'
            WHEN ls.slope + 2.03 * ls.slope_se < 0 THEN 'earlier/shorter (clear)'
            ELSE 'no clear trend'
       END                                                     AS verdict
FROM least_squares ls
JOIN sen s ON s.town = ls.town AND s.measure = ls.measure
ORDER BY ls.sort_key, ls.sort_m;
