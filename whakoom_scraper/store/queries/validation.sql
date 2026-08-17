-- validation.sql
-- Read-only checks for the `wk validate` stage (V2 §12) plus the
-- snapshot bookkeeping that powers row-count delta checks.

-- name: list_count_mismatches
SELECT
    l.whakoom_list_id,
    l.name,
    l.comic_count,
    COUNT(li.id) AS parsed_count
FROM lists AS l
LEFT JOIN list_items AS li ON l.id = li.list_id
WHERE l.comic_count IS NOT NULL
GROUP BY
    l.id,
    l.whakoom_list_id,
    l.name,
    l.comic_count
HAVING COUNT(li.id) != l.comic_count
ORDER BY l.whakoom_list_id;

-- name: count_lists_missing_comic_count
SELECT COUNT(*) AS n
FROM lists
WHERE comic_count IS NULL;

-- name: foreign_key_violations
PRAGMA foreign_key_check;

-- name: duplicate_list_item_positions
SELECT
    list_id,
    position,
    COUNT(*) AS n
FROM list_items
GROUP BY
    list_id,
    position
HAVING COUNT(*) > 1
ORDER BY list_id, position;

-- name: duplicate_list_item_slugs
SELECT
    list_id,
    volume_slug,
    COUNT(*) AS n
FROM list_items
GROUP BY
    list_id,
    volume_slug
HAVING COUNT(*) > 1
ORDER BY list_id, volume_slug;

-- name: count_unresolved_items
SELECT COUNT(*) AS n
FROM list_items
WHERE series_id IS NULL;

-- name: series_bound_violations
SELECT id
FROM series
WHERE
    (rating IS NOT NULL AND rating NOT BETWEEN 0 AND 5)
    OR rating_count < 0
    OR ownership_count < 0
    OR volumes_count < 0
ORDER BY id;

-- name: observation_bound_violations
SELECT id
FROM series_observations
WHERE
    (rating IS NOT NULL AND rating NOT BETWEEN 0 AND 5)
    OR rating_count < 0
    OR ownership_count < 0
    OR volumes_count < 0
ORDER BY id;

-- name: table_row_counts
SELECT
    'lists' AS table_name,
    COUNT(*) AS row_count
FROM lists
UNION ALL
SELECT
    'list_items' AS table_name,
    COUNT(*) AS row_count
FROM list_items
UNION ALL
SELECT
    'publishers' AS table_name,
    COUNT(*) AS row_count
FROM publishers
UNION ALL
SELECT
    'authors' AS table_name,
    COUNT(*) AS row_count
FROM authors
UNION ALL
SELECT
    'series' AS table_name,
    COUNT(*) AS row_count
FROM series
UNION ALL
SELECT
    'volumes' AS table_name,
    COUNT(*) AS row_count
FROM volumes
UNION ALL
SELECT
    'series_observations' AS table_name,
    COUNT(*) AS row_count
FROM series_observations
ORDER BY table_name;

-- name: latest_completed_stage_runs
SELECT
    stage,
    items_processed,
    items_failed
FROM (
    SELECT
        stage,
        items_processed,
        items_failed,
        ROW_NUMBER() OVER (PARTITION BY stage ORDER BY id DESC) AS rn
    FROM scrape_runs
    WHERE status = 'completed'
) AS ranked
WHERE rn = 1
ORDER BY stage;

-- name: insert_snapshot
INSERT INTO validation_snapshots (run_id, table_name, row_count)
VALUES (?, ?, ?);

-- name: get_snapshots_for_run
SELECT
    table_name,
    row_count
FROM validation_snapshots
WHERE run_id = ?
ORDER BY table_name;
