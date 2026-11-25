-- Question: how much rain fell each December-January, per town, and what's the trend line?
-- The year-by-year view behind finding #2 (rain_trend.sql's dec_jan_total). The fitted
-- trend uses the same least-squares fit (regr_slope / regr_intercept), as a window over
-- each town's years, so the dashboard draws the line without computing it in Python.
-- December of year Y + January of Y+1, labelled Y. Complete periods (62 days) only.

WITH dec_jan AS (
    SELECT location_id,
           extract(year FROM date - INTERVAL '1 month')::int AS year,
           sum(precipitation_mm)                             AS dec_jan_mm
    FROM daily_weather
    WHERE extract(month FROM date) IN (12, 1)
    GROUP BY location_id, extract(year FROM date - INTERVAL '1 month')
    HAVING count(*) = 62
)
SELECT l.name AS town,
       d.year,
       round(d.dec_jan_mm::numeric, 1) AS dec_jan_mm,
       round((regr_intercept(d.dec_jan_mm, d.year) OVER town_years
              + regr_slope(d.dec_jan_mm, d.year) OVER town_years * d.year)::numeric, 1) AS trend_mm
FROM dec_jan d
JOIN locations l ON l.id = d.location_id
WHERE d.year <= 2025   -- same years as rain_trend.sql
WINDOW town_years AS (PARTITION BY d.location_id)
ORDER BY l.id, d.year;
