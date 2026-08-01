-- Up
-- Update lists stuck in 'in_progress' to 'completed'
-- These lists were successfully processed but status wasn't updated
UPDATE lists
SET
    scrape_status = 'completed',
    scraped_at = CURRENT_TIMESTAMP
WHERE scrape_status = 'in_progress';

-- Update all titles to 'completed' since they were successfully inserted
-- but status was never updated
UPDATE titles
SET
    scrape_status = 'completed',
    scraped_at = CURRENT_TIMESTAMP
WHERE scrape_status = 'pending';

-- Log the recovery operation
INSERT INTO scraping_log (
    scrapper_name, operation_type, entity_id, status, error_message
)
VALUES (
    'manual_recovery',
    'status_reset',
    0,
    'success',
    'Reset stuck statuses after spider fix'
);

-- Down
-- Rollback - not really applicable for this one-time fix
-- This migration is idempotent - can be run multiple times safely
