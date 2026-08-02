-- list_items.sql
-- Named queries for the `list_items` table.

-- name: get_list_item_series_map
SELECT
    volume_slug,
    series_id
FROM list_items
WHERE list_id = ?;

-- name: delete_list_items_for_list
DELETE FROM list_items
WHERE list_id = ?;

-- name: insert_list_item
INSERT INTO list_items (
    list_id,
    position,
    volume_slug,
    whakoom_publication_id,
    volume_url,
    volume_number,
    publisher,
    series_id
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);

-- name: count_items_for_list
SELECT count(*) AS n FROM list_items
WHERE list_id = ?;

-- name: get_unresolved_slugs
SELECT DISTINCT volume_slug
FROM list_items
WHERE series_id IS NULL
ORDER BY volume_slug;

-- name: set_item_series
UPDATE list_items
SET
    series_id = ?,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE volume_slug = ?;
