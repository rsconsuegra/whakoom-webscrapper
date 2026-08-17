-- 002_validation_snapshots.sql
-- Validation history: per-run table row counts so `wk validate` can flag
-- unexpected row-count drops against the previous successful run (V2 §12
-- check 6). Forward-only migration (V2 §8.4).

CREATE TABLE IF NOT EXISTS validation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES scrape_runs (id),
    table_name TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (run_id, table_name)
);
