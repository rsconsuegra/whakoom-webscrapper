-- views.sql — DuckDB views over the attached SQLite database (V2 §14).
-- Applied wholesale by `wk analyze` against `ATTACH ... AS wh (TYPE sqlite)`.
-- Views persist in data/whakoom.duckdb for the explore.ipynb notebook.

-- year_lists is filtered first so the year extraction never runs against
-- non-year names; TRY_CAST guards against any residual empty match (DuckDB
-- may evaluate projections on rows the surrounding filters would drop).
CREATE OR REPLACE VIEW v_titles_by_year AS
WITH year_lists AS (
    SELECT
        l.id AS list_id,
        l.whakoom_list_id AS whakoom_list_id,
        l.canonical_name AS canonical_name,
        TRY_CAST(regexp_extract(l.name, '(?:19|20)[0-9]{2}') AS INTEGER) AS year
    FROM wh.lists AS l
    WHERE l.list_type = 'year'
)
SELECT
    yl.year AS year,
    s.id AS series_id,
    s.whakoom_series_id AS whakoom_series_id,
    s.name AS series_name,
    yl.whakoom_list_id AS whakoom_list_id,
    yl.canonical_name AS canonical_name
FROM year_lists AS yl
JOIN wh.list_items AS li ON li.list_id = yl.list_id
JOIN wh.series AS s ON s.id = li.series_id;

CREATE OR REPLACE VIEW v_titles_by_magazine AS
SELECT
    l.canonical_name AS magazine,
    s.id AS series_id,
    s.whakoom_series_id AS whakoom_series_id,
    s.name AS series_name,
    l.whakoom_list_id AS whakoom_list_id
FROM wh.lists AS l
JOIN wh.list_items AS li ON li.list_id = l.id
JOIN wh.series AS s ON s.id = li.series_id
WHERE l.list_type = 'magazine';

CREATE OR REPLACE VIEW v_publisher_share_by_year AS
WITH year_lists AS (
    SELECT
        l.id AS list_id,
        l.name AS name,
        TRY_CAST(regexp_extract(l.name, '(?:19|20)[0-9]{2}') AS INTEGER) AS year
    FROM wh.lists AS l
    WHERE l.list_type = 'year'
)
SELECT
    yl.year AS year,
    COALESCE(p.name, li.publisher, 'Unknown') AS publisher,
    COUNT(DISTINCT s.id) AS titles
FROM year_lists AS yl
JOIN wh.list_items AS li ON li.list_id = yl.list_id
JOIN wh.series AS s ON s.id = li.series_id
LEFT JOIN wh.publishers AS p ON p.id = s.publisher_id
GROUP BY
    yl.year,
    COALESCE(p.name, li.publisher, 'Unknown');

CREATE OR REPLACE VIEW v_rating_by_publisher AS
SELECT
    p.name AS publisher,
    COUNT(*) AS titles,
    AVG(s.rating) AS avg_rating,
    SUM(s.rating_count) AS total_votes,
    AVG(s.ownership_count) AS avg_ownership
FROM wh.series AS s
JOIN wh.publishers AS p ON p.id = s.publisher_id
GROUP BY p.name;

CREATE OR REPLACE VIEW v_score_history AS
SELECT
    s.whakoom_series_id AS whakoom_series_id,
    s.name AS series_name,
    r.id AS run_id,
    o.observed_at AS observed_at,
    o.rating AS rating,
    o.rating_count AS rating_count,
    o.ownership_count AS ownership_count,
    o.volumes_count AS volumes_count,
    o.status AS status
FROM wh.series_observations AS o
JOIN wh.series AS s ON s.id = o.series_id
JOIN wh.scrape_runs AS r ON r.id = o.run_id;

CREATE OR REPLACE VIEW v_list_overlap AS
SELECT
    s.whakoom_series_id AS whakoom_series_id,
    s.name AS series_name,
    COUNT(DISTINCT l.id) AS list_count,
    string_agg(l.name, ' | ' ORDER BY l.name) AS lists
FROM wh.lists AS l
JOIN wh.list_items AS li ON li.list_id = l.id
JOIN wh.series AS s ON s.id = li.series_id
GROUP BY
    s.whakoom_series_id,
    s.name
HAVING COUNT(DISTINCT l.id) > 1;
