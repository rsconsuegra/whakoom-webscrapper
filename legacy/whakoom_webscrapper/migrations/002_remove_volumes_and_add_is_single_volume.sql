-- Up
-- Add is_single_volume column to titles table
ALTER TABLE titles ADD COLUMN is_single_volume INTEGER NOT NULL DEFAULT 0;

DROP TABLE IF EXISTS volumes;

-- Down
-- Remove is_single_volume column from titles table
ALTER TABLE titles DROP COLUMN is_single_volume;

-- Recreate volumes table
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
    FOREIGN KEY (title_id) REFERENCES titles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_volumes_title ON volumes (title_id);
CREATE INDEX IF NOT EXISTS idx_volumes_volume_id ON volumes (volume_id);
