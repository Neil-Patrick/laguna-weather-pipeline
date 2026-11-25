-- Question: how much did it rain in each month of each year, in each town?
-- The base table for spotting patterns: one row per (town, year, month).
--
-- total_mm:  total rain that month.
-- rain_days: days with at least 1 mm. That's the standard "wet day" threshold
--            (ETCCDI climate indices). The model data has a trace of drizzle on
--            most days, so counting anything above 0 would call almost every day rainy.
-- Only complete months are returned (days_recorded = days in that month), so the
-- current, half-finished month can't look unusually dry.

SELECT l.name                                            AS town,
       extract(year  FROM w.date)::int                   AS year,
       extract(month FROM w.date)::int                   AS month,
       round(sum(w.precipitation_mm)::numeric, 1)        AS total_mm,
       count(*) FILTER (WHERE w.precipitation_mm >= 1)   AS rain_days,
       count(*)                                          AS days_recorded
FROM daily_weather w
JOIN locations l ON l.id = w.location_id
GROUP BY l.id, l.name, year, month
HAVING count(*) = extract(day FROM date_trunc('month', min(w.date)) + interval '1 month - 1 day')
ORDER BY l.id, year, month;
