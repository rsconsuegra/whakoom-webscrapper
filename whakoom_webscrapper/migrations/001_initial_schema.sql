# MIGRATION_VERSION
001

# MIGRATION_NAME
initial_schema

# UP
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    user_profile TEXT NOT NULL,
    scrape_status TEXT NOT NULL DEFAULT 'pending',
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lists_scrape_status ON lists(scrape_status);
CREATE INDEX IF NOT EXISTS idx_lists_user_profile ON lists(user_profile);

CREATE TABLE IF NOT EXISTS titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    scrape_status TEXT NOT NULL DEFAULT 'pending',
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_titles_scrape_status ON titles(scrape_status);
CREATE INDEX IF NOT EXISTS idx_titles_title_id ON titles(title_id);

CREATE TABLE IF NOT EXISTS lists_titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL,
    title_id INTEGER NOT NULL,
    position INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (list_id) REFERENCES lists(id) ON DELETE CASCADE,
    FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE,
    UNIQUE(list_id, title_id)
);

CREATE INDEX IF NOT EXISTS idx_lists_titles_list ON lists_titles(list_id);
CREATE INDEX IF NOT EXISTS idx_lists_titles_title ON lists_titles(title_id);

CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id INTEGER NOT NULL UNIQUE,
    title_id INTEGER NOT NULL,
    volume_number INTEGER,
    title TEXT,
    url TEXT,
    isbn TEXT,
    publisher TEXT,
    year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_volumes_title ON volumes(title_id);
CREATE INDEX IF NOT EXISTS idx_volumes_volume_id ON volumes(volume_id);

CREATE TABLE IF NOT EXISTS title_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_id INTEGER NOT NULL UNIQUE,
    author TEXT,
    publisher TEXT,
    demographic TEXT,
    genre TEXT,
    themes TEXT,
    original_title TEXT,
    description TEXT,
    start_year INTEGER,
    end_year INTEGER,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS title_enriched (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_id INTEGER NOT NULL UNIQUE,
    cover_url TEXT,
    cover_image_path TEXT,
    rating REAL,
    rating_count INTEGER,
    popularity_rank INTEGER,
    myanimelist_url TEXT,
    mangaupdates_url TEXT,
    anilist_url TEXT,
    additional_data TEXT,
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scraping_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scrapper_name TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scraping_log_entity ON scraping_log(entity_id, operation_type);

CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO migrations (version, name) VALUES ('001', 'initial_schema');

# DOWN
DROP TABLE IF EXISTS scraping_log;
DROP TABLE IF EXISTS title_enriched;
DROP TABLE IF EXISTS title_metadata;
DROP TABLE IF EXISTS volumes;
DROP TABLE IF EXISTS lists_titles;
DROP TABLE IF EXISTS titles;
DROP TABLE IF EXISTS lists;
DROP TABLE IF EXISTS migrations;
