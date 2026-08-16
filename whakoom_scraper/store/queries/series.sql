-- series.sql
-- Named queries for `series`, `publishers`, `authors` and `series_authors`.

-- name: upsert_publisher
INSERT INTO publishers (whakoom_id, name, url)
VALUES (?, ?, ?)
ON CONFLICT (name) DO UPDATE SET
    whakoom_id = COALESCE(excluded.whakoom_id, publishers.whakoom_id),
    url = COALESCE(excluded.url, publishers.url),
    updated_at = STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now');

-- name: get_publisher_id_by_name
SELECT id FROM publishers
WHERE name = ?;

-- name: get_publisher_by_name
SELECT
    id,
    whakoom_id,
    name,
    url,
    created_at,
    updated_at
FROM publishers
WHERE name = ?;

-- name: upsert_author
INSERT INTO authors (whakoom_id, name, url)
VALUES (?, ?, ?)
ON CONFLICT (whakoom_id) DO UPDATE SET
    name = excluded.name,
    url = excluded.url,
    updated_at = STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now');

-- name: get_author_id_by_whakoom_id
SELECT id FROM authors
WHERE whakoom_id = ?;

-- name: get_author_id_by_name
SELECT id FROM authors
WHERE name = ?
ORDER BY id LIMIT 1;

-- name: get_author_by_name
SELECT
    id,
    whakoom_id,
    name,
    url,
    created_at,
    updated_at
FROM authors
WHERE name = ?
ORDER BY id LIMIT 1;

-- name: link_series_author
INSERT OR IGNORE INTO series_authors (series_id, author_id, role)
VALUES (?, ?, ?);

-- name: stub_series
INSERT INTO series (whakoom_series_id, slug, url, name, scrape_status)
VALUES (?, ?, ?, ?, 'pending')
ON CONFLICT (whakoom_series_id) DO NOTHING;

-- name: get_series_id
SELECT id FROM series
WHERE whakoom_series_id = ?;

-- name: get_series
SELECT
    id,
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM series
WHERE whakoom_series_id = ?;

-- name: get_pending_series
SELECT
    id,
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM series
WHERE scrape_status = 'pending'
ORDER BY id;

-- name: get_pending_series_with_failed
SELECT
    id,
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM series
WHERE scrape_status IN ('pending', 'failed')
ORDER BY id;

-- name: get_failed_series
SELECT
    id,
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM series
WHERE scrape_status = 'failed'
ORDER BY id;

-- name: get_all_series
SELECT
    id,
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at,
    created_at,
    updated_at
FROM series
ORDER BY id;

-- name: upsert_series
INSERT INTO series (
    whakoom_series_id,
    slug,
    url,
    name,
    original_title,
    publisher_id,
    status,
    format,
    language,
    volumes_count,
    rating,
    rating_count,
    rating_distribution,
    ownership_count,
    synopsis,
    scrape_status,
    scraped_at
)
VALUES (
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    ?,
    'completed',
    STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now')
)
ON CONFLICT (whakoom_series_id) DO UPDATE SET
    slug = excluded.slug,
    url = excluded.url,
    name = excluded.name,
    original_title = excluded.original_title,
    publisher_id = excluded.publisher_id,
    status = excluded.status,
    format = excluded.format,
    language = excluded.language,
    volumes_count = excluded.volumes_count,
    rating = excluded.rating,
    rating_count = excluded.rating_count,
    rating_distribution = excluded.rating_distribution,
    ownership_count = excluded.ownership_count,
    synopsis = excluded.synopsis,
    scrape_status = 'completed',
    scraped_at = STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now'),
    updated_at = STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now');

-- name: set_series_status
UPDATE series
SET
    scrape_status = ?,
    updated_at = STRFTIME('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE id = ?;
