-- 001_initial_schema.sql
-- Initial Whakoom V2 schema. Idempotent: safe to re-apply.
--
-- Identifier discipline:
--   * surrogate `id` PRIMARY KEYs never leave the database
--   * external identifiers always use the `whakoom_*` prefix

-- Up

CREATE TABLE IF NOT EXISTS _migrations (
    filename TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'completed', 'failed', 'aborted')),
    items_processed INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    whakoom_list_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    user_profile TEXT NOT NULL,
    description TEXT,
    comic_count INTEGER,
    likes INTEGER,
    -- list_type is intentionally unconstrained until Stage 1
    -- defines the value domain.
    list_type TEXT,
    canonical_name TEXT,
    scrape_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (scrape_status IN ('pending', 'completed', 'failed')),
    scraped_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS publishers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    whakoom_id INTEGER UNIQUE,
    name TEXT NOT NULL UNIQUE,
    url TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    whakoom_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    url TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    whakoom_series_id INTEGER NOT NULL UNIQUE,
    -- slug is NOT unique: Whakoom slugifies CJK titles to underscore
    -- strings, so distinct series can share a slug (id is the real key).
    slug TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    name TEXT,
    original_title TEXT,
    publisher_id INTEGER REFERENCES publishers (id),
    status TEXT,
    format TEXT,
    language TEXT,
    volumes_count INTEGER CHECK (volumes_count >= 0),
    rating REAL CHECK (rating BETWEEN 0 AND 5),
    rating_count INTEGER CHECK (rating_count >= 0),
    rating_distribution TEXT,
    ownership_count INTEGER CHECK (ownership_count >= 0),
    synopsis TEXT,
    scrape_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (scrape_status IN ('pending', 'completed', 'failed')),
    scraped_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_series_scrape_status ON series (scrape_status);
CREATE INDEX IF NOT EXISTS idx_series_publisher_id ON series (publisher_id);

CREATE TABLE IF NOT EXISTS series_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES scrape_runs (id),
    observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    rating REAL CHECK (rating BETWEEN 0 AND 5),
    rating_count INTEGER CHECK (rating_count >= 0),
    rating_distribution TEXT,
    ownership_count INTEGER CHECK (ownership_count >= 0),
    volumes_count INTEGER CHECK (volumes_count >= 0),
    status TEXT,
    UNIQUE (series_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_observations_series ON series_observations (
    series_id
);

CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_slug TEXT NOT NULL UNIQUE,
    series_id INTEGER NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    number INTEGER,
    title TEXT,
    publisher TEXT,
    cover_url TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_volumes_series ON volumes (series_id);

CREATE TABLE IF NOT EXISTS series_authors (
    series_id INTEGER NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES authors (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (series_id, author_id, role)
);

CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL REFERENCES lists (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    volume_slug TEXT NOT NULL,
    whakoom_publication_id INTEGER,
    volume_url TEXT NOT NULL,
    volume_number INTEGER,
    publisher TEXT,
    series_id INTEGER REFERENCES series (id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (list_id, position),
    UNIQUE (list_id, volume_slug)
);

CREATE INDEX IF NOT EXISTS idx_list_items_series_id ON list_items (series_id);
CREATE INDEX IF NOT EXISTS idx_list_items_list_id ON list_items (list_id);

-- Down
-- This migration is forward-only by design (see V2 §8.4). No DOWN body.
