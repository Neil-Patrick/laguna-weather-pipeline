-- Question: how much rain fell in the 7 days ending on each date, in each town?
-- Single days are noisy (one storm, then dry); a 7-day total shows whether it's
-- *persistently* wet, which is what a rainy season is. The onset/end rule builds on this.
--
-- RANGE with an interval (not ROWS 6 PRECEDING) means "the 7 calendar days ending
-- this date", so it stays correct even if a day were ever missing from the table.
-- days_in_window guards the start of the series: on 1991-01-03 only 3 days exist,
-- so that partial total is returned as NULL instead of looking like a dry week.

WITH rolling AS (
    SELECT location_id,
           date,
           precipitation_mm,
           sum(precipitation_mm) OVER seven_days AS rain_7d_mm,
           count(*)              OVER seven_days AS days_in_window
    FROM daily_weather
    WINDOW seven_days AS (
        PARTITION BY location_id
        ORDER BY date
        RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
    )
)
SELECT l.name AS town,
       r.date,
       r.precipitation_mm,
       CASE WHEN r.days_in_window = 7 THEN round(r.rain_7d_mm::numeric, 1) END AS rain_7d_mm
FROM rolling r
JOIN locations l ON l.id = r.location_id
ORDER BY l.id, r.date;
