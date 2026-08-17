-- lists.sql
-- Named queries for the `lists` table.

-- name: upsert_list
INSERT INTO lists (
    whakoom_list_id, name, url, user_profile, description, comic_count, likes
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (whakoom_list_id) DO UPDATE SET
    name = excluded.name,
    url = excluded.url,
    user_profile = excluded.user_profile,
    description = excluded.description,
    comic_count = excluded.comic_count,
    likes = excluded.likes,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now');

-- name: get_list
SELECT
    id,
    whakoom_list_id,
    name,
    url,
    user_profile,
    description,
    comic_count,
    likes,
    list_type,
    canonical_name,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM lists
WHERE whakoom_list_id = ?;

-- name: get_lists
SELECT
    id,
    whakoom_list_id,
    name,
    url,
    user_profile,
    description,
    comic_count,
    likes,
    list_type,
    canonical_name,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM lists
ORDER BY id;

-- name: get_pending_lists
SELECT
    id,
    whakoom_list_id,
    name,
    url,
    user_profile,
    description,
    comic_count,
    likes,
    list_type,
    canonical_name,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM lists
WHERE scrape_status = 'pending'
ORDER BY id;

-- name: get_pending_lists_with_failed
SELECT
    id,
    whakoom_list_id,
    name,
    url,
    user_profile,
    description,
    comic_count,
    likes,
    list_type,
    canonical_name,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM lists
WHERE scrape_status IN ('pending', 'failed')
ORDER BY id;

-- name: get_failed_lists
SELECT
    id,
    whakoom_list_id,
    name,
    url,
    user_profile,
    description,
    comic_count,
    likes,
    list_type,
    canonical_name,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM lists
WHERE scrape_status = 'failed'
ORDER BY id;

-- name: mark_list_status
UPDATE lists
SET
    scrape_status = ?,
    scraped_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE whakoom_list_id = ?;

-- name: reset_lists_pending
UPDATE lists SET scrape_status = 'pending'
WHERE scrape_status = 'completed';

-- name: invalidate_lists
UPDATE lists
SET
    scrape_status = 'pending',
    scraped_at = NULL,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now');

-- name: get_unclassified_lists
SELECT
    id,
    name
FROM lists
WHERE list_type IS NULL
ORDER BY id;

-- name: set_list_classification
UPDATE lists
SET
    list_type = ?,
    canonical_name = ?,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE id = ?;
