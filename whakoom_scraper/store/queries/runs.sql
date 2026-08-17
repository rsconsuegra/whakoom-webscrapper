-- runs.sql
-- Named queries for the `scrape_runs` table.

-- name: create_run
INSERT INTO scrape_runs (stage) VALUES (?);

-- name: close_run
UPDATE scrape_runs
SET
    finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
    status = ?,
    items_processed = ?,
    items_failed = ?,
    notes = ?
WHERE id = ?;

-- name: get_last_run
SELECT
    id,
    stage,
    status,
    items_processed,
    items_failed,
    notes
FROM scrape_runs
WHERE stage = ?
ORDER BY id DESC
LIMIT 1;

-- name: get_last_completed_run_id
SELECT id
FROM scrape_runs
WHERE stage = ? AND status = 'completed' AND id != ?
ORDER BY id DESC
LIMIT 1;

-- name: abort_stale_runs
UPDATE scrape_runs
SET
    status = 'aborted',
    finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
    notes
    = coalesce(notes || '; ', '')
    || 'marked aborted by validate: stale running run'
WHERE status = 'running' AND id != ?;
