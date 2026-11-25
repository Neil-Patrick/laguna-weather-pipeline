-- Question: when did the rainy season start and end, per town and year?
-- The logic lives in the rainy_seasons view (sql/002_views.sql), so the trend query,
-- dashboard and weekly report all use one definition. See that file for the method.

SELECT town, season_year AS year, onset_date, end_date, length_days,
       typical_onset, typical_end
FROM rainy_seasons
ORDER BY location_id, season_year;
