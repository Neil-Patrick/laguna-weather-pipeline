-- Question: how close are our rainy-season onset dates to PAGASA's official declarations?
-- A sanity check, not a target: PAGASA declares one national date (7 of 13 stations across
-- western Luzon and the Visayas, plus westerly winds); ours are per town from ERA5 model data.
--
-- PAGASA declaration dates, from news reports of each announcement:
--   2016-05-24 Philstar (declared without waiting for its usual criteria)
--   2017-05-30 Inquirer   2018-06-08 Philstar (2019 article)   2019-06-14 Philstar
--   2020-06-12 Manila Bulletin (2021 article)   2021-06-04 Manila Bulletin
--   2022-05-18 Manila Bulletin   2023-06-02 ABS-CBN   2024-05-29 Manila Bulletin
-- Los Baños is left out: it shares an ERA5 grid cell with Calamba (identical rain).

WITH pagasa(year, declared) AS (
    VALUES (2016, DATE '2016-05-24'), (2017, DATE '2017-05-30'), (2018, DATE '2018-06-08'),
           (2019, DATE '2019-06-14'), (2020, DATE '2020-06-12'), (2021, DATE '2021-06-04'),
           (2022, DATE '2022-05-18'), (2023, DATE '2023-06-02'), (2024, DATE '2024-05-29')
),
differences AS (
    SELECT s.town, p.year, p.declared, s.onset_date,
           s.onset_date - p.declared AS days_vs_pagasa      -- negative = before PAGASA
    FROM rainy_seasons s
    JOIN pagasa p ON p.year = s.season_year
    WHERE s.town <> 'Los Baños'
)
SELECT count(*)                                                        AS town_years,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY days_vs_pagasa)     AS median_days_vs_pagasa,
       round(avg((abs(days_vs_pagasa) <= 10)::int) * 100)              AS pct_within_10_days,
       round(avg((abs(days_vs_pagasa) <= 20)::int) * 100)              AS pct_within_20_days,
       min(days_vs_pagasa)                                             AS earliest_vs_pagasa,
       max(days_vs_pagasa)                                             AS latest_vs_pagasa
FROM differences;
