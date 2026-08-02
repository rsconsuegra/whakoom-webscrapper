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
