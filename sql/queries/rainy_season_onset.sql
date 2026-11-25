-- REJECTED APPROACH, kept to document the validation. Use rainy_season.sql instead.
-- Checked against PAGASA's declared onset dates 2016-2024, this rule fired a median
-- 31 days early (only 22% of town-years within +-10 days). Cause: the model data has
-- too many light-rain days, so the 25 mm / 3-wet-day test passes in April and 10-day
-- dry spells (the false-start check) almost never happen.
--
-- Question: on what date did the rainy season start, per town and year?
--
-- Rule (per town; PAGASA's rainfall test plus a false-start check):
--   A day D is the onset if, searching 1 April to 31 July:
--   1. days D..D+4 have >= 25 mm in total                        (PAGASA, 2019 criteria)
--   2. and within D..D+4 there are 3 consecutive days of >= 1 mm  (PAGASA, 2019 criteria)
--   3. and in the 30 days after that spell (D+5..D+34) there is
--      no run of 10+ consecutive dry days (< 1 mm)                (our false-start check)
--   The onset is the first such day. No such day -> NULL (no clear onset that year).
--
-- PAGASA also requires 7 of 13 stations and westerly winds; we apply only the
-- rainfall part, per town. So we expect the same ballpark as PAGASA, not the same day.
--
-- onset_pagasa_only applies rules 1-2 without the false-start check, to show
-- how often the check changed the answer.

WITH days AS (
    SELECT location_id, date, precipitation_mm,
           (precipitation_mm >= 1)::int AS wet          -- 1 = wet day, 0 = dry day
    FROM daily_weather
),
-- For each day: what does the stretch starting here look like?
looking_ahead AS (
    SELECT location_id, date,
           sum(precipitation_mm) OVER next_5  AS rain_next_5d,
           count(*)              OVER next_5  AS days_next_5,
           -- 3 wet days in a row starting today (count guards the end of the data)
           (min(wet) OVER next_3  = 1 AND count(*) OVER next_3  = 3)  AS starts_3_wet,
           -- 10 dry days in a row starting today
           (max(wet) OVER next_10 = 0 AND count(*) OVER next_10 = 10) AS starts_10_dry
    FROM days
    WINDOW next_3  AS (PARTITION BY location_id ORDER BY date
                       RANGE BETWEEN CURRENT ROW AND INTERVAL '2 days' FOLLOWING),
           next_5  AS (PARTITION BY location_id ORDER BY date
                       RANGE BETWEEN CURRENT ROW AND INTERVAL '4 days' FOLLOWING),
           next_10 AS (PARTITION BY location_id ORDER BY date
                       RANGE BETWEEN CURRENT ROW AND INTERVAL '9 days' FOLLOWING)
),
candidates AS (
    SELECT location_id, date, rain_next_5d, days_next_5,
           -- rule 2: a 3-wet-day run starting on D, D+1 or D+2 fits inside D..D+4
           bool_or(starts_3_wet)  OVER spell_starts AS has_3_wet_run,
           -- rule 3: a 10-dry-day run starting D+5..D+25 fits inside D+5..D+34
           bool_or(starts_10_dry) OVER after_spell  AS dry_spell_follows
    FROM looking_ahead
    WINDOW spell_starts AS (PARTITION BY location_id ORDER BY date
                            RANGE BETWEEN CURRENT ROW AND INTERVAL '2 days' FOLLOWING),
           after_spell  AS (PARTITION BY location_id ORDER BY date
                            RANGE BETWEEN INTERVAL '5 days' FOLLOWING AND INTERVAL '25 days' FOLLOWING)
),
onsets AS (
    SELECT location_id,
           extract(year FROM date)::int AS year,
           min(date) FILTER (WHERE NOT dry_spell_follows) AS onset,
           min(date)                                       AS onset_pagasa_only
    FROM candidates
    WHERE date BETWEEN make_date(extract(year FROM date)::int, 4, 1)
                   AND make_date(extract(year FROM date)::int, 7, 31)
      AND days_next_5 = 5
      AND rain_next_5d >= 25
      AND has_3_wet_run
    GROUP BY location_id, extract(year FROM date)
),
-- every town-year with data through the end of the search window (incl. the 34 days after)
town_years AS (
    SELECT location_id, extract(year FROM date)::int AS year
    FROM daily_weather
    GROUP BY location_id, extract(year FROM date)
    HAVING max(date) >= make_date(extract(year FROM date)::int, 9, 3)
)
SELECT l.name                                 AS town,
       ty.year,
       o.onset,
       extract(doy FROM o.onset)::int         AS onset_day_of_year,
       o.onset_pagasa_only
FROM town_years ty
JOIN locations l  ON l.id = ty.location_id
LEFT JOIN onsets o ON o.location_id = ty.location_id AND o.year = ty.year
ORDER BY l.id, ty.year;
