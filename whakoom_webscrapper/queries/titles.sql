# INSERT_OR_IGNORE_TITLE
INSERT INTO titles (title_id, title, url, scrape_status, scraped_at, is_single_volume)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (title_id) DO NOTHING;

# GET_TITLE_BY_ID
SELECT
    id,
    title_id,
    title,
    url,
    scrape_status,
    scraped_at,
    is_single_volume,
    created_at,
    updated_at
FROM titles
WHERE title_id = ?;

# GET_TITLES_BY_STATUS
SELECT
    id,
    title_id,
    title,
    url,
    scrape_status,
    scraped_at,
    is_single_volume,
    created_at,
    updated_at
FROM titles
WHERE scrape_status = ?
ORDER BY id;

# UPDATE_TITLE_STATUS
UPDATE titles
SET scrape_status = ?, scraped_at = CURRENT_TIMESTAMP
WHERE title_id = ?;

# GET_ALL_TITLES
SELECT
    id,
    title_id,
    title,
    url,
    scrape_status,
    scraped_at,
    is_single_volume,
    created_at,
    updated_at
FROM titles
ORDER BY id;
