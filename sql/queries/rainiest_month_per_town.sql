-- Question: which calendar month is the rainiest in each town, on average?
-- Method: total rain per (town, month), then average those totals per calendar month
-- across all complete years, and rank the 12 months within each town.
-- Only complete years are used, so a half-finished current year doesn't drag averages down.

WITH monthly AS (
    SELECT location_id,
           date_trunc('month', date) AS month,
           sum(precipitation_mm)     AS total_mm
    FROM daily_weather
    WHERE date < date_trunc('year', current_date)
    GROUP BY location_id, date_trunc('month', date)
),
by_calendar_month AS (
    SELECT location_id,
           extract(month FROM month)::int AS month_number,
           avg(total_mm)                  AS avg_mm,
           rank() OVER (PARTITION BY location_id ORDER BY avg(total_mm) DESC) AS rank
    FROM monthly
    GROUP BY location_id, extract(month FROM month)
)
SELECT l.name                                          AS town,
       to_char(make_date(2000, b.month_number, 1), 'Mon') AS rainiest_month,
       round(b.avg_mm::numeric, 0)                     AS avg_total_mm
FROM by_calendar_month b
JOIN locations l ON l.id = b.location_id
WHERE b.rank = 1
ORDER BY l.id;
