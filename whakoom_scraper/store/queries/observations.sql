-- observations.sql
-- Named queries for the `series_observations` table.

-- name: insert_observation
INSERT INTO series_observations (
    series_id,
    run_id,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    volumes_count,
    status
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (series_id, run_id) DO NOTHING;
