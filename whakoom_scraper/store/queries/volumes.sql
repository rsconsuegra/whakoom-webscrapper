-- volumes.sql
-- Named queries for the `volumes` table.

-- name: upsert_volume
INSERT INTO volumes (
    volume_slug, series_id, number, title, publisher, cover_url
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (volume_slug) DO UPDATE SET
    series_id = excluded.series_id,
    number = excluded.number,
    title = excluded.title,
    publisher = excluded.publisher,
    cover_url = excluded.cover_url,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now');
