# INSERT_OR_UPDATE_LIST
INSERT INTO lists (list_id, title, url, user_profile, scrape_status, scraped_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (list_id) DO UPDATE SET
    title = excluded.title,
    url = excluded.url,
    scrape_status = excluded.scrape_status,
    scraped_at = excluded.scraped_at,
    updated_at = CURRENT_TIMESTAMP;

# GET_LISTS_BY_STATUS
SELECT
    id,
    list_id,
    title,
    url,
    user_profile,
    scrape_status,
    scraped_at
FROM lists
WHERE scrape_status = ?
ORDER BY id;

# GET_LISTS_BY_USER_PROFILE
SELECT
    id,
    list_id,
    title,
    url,
    user_profile,
    scrape_status,
    scraped_at
FROM lists
WHERE user_profile = ?
ORDER BY id;

# UPDATE_LIST_STATUS
UPDATE lists
SET scrape_status = ?, scraped_at = CURRENT_TIMESTAMP
WHERE list_id = ?;

# GET_LIST_BY_ID
SELECT
    id,
    list_id,
    title,
    url,
    user_profile,
    scrape_status,
    scraped_at
FROM lists
WHERE list_id = ?;

# GET_ALL_LISTS
SELECT
    id,
    list_id,
    title,
    url,
    user_profile,
    scrape_status,
    scraped_at
FROM lists
ORDER BY id;

# GET_LISTS_FOR_PROCESSING
SELECT
    id,
    list_id,
    title,
    url,
    user_profile,
    scrape_status,
    scraped_at
FROM lists
WHERE scrape_status = ?
ORDER BY id;
