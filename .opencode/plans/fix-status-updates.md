# Fix Spider Status Updates - Plan

## Context

After running both `lists` and `publications` spiders, database entries show incorrect status values:
- **Lists**: All stuck at "in_progress" (should be "completed")
- **Titles**: All stuck at "pending" (should be "completed")

This prevents proper workflow progression and makes it impossible to track which lists/titles have been successfully scraped.

### Root Cause Analysis

#### Issue 1: Lists stuck at "in_progress"

**Location**: `whakoom_webscrapper/spiders/publications.py:361-377`

The Publications spider's `close_spider` method only updates lists in `self.processed_list_ids`:

```python
def close_spider(self, spider: Spider) -> None:
    for db_list_id in self.processed_list_ids:
        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "completed"
        )
```

**Problem**: `processed_list_ids` is populated in `parse_volume_page` (line 287) AFTER yielding items. If processing is interrupted, crashes, or any error occurs, lists remain in "in_progress" state.

**Current flow**:
1. `parse_list` sets status to "in_progress"
2. `parse_volume_page` adds list to `processed_list_ids`
3. `close_spider` updates only lists in `processed_list_ids`
4. If interrupted between 1 and 3 → list stuck in "in_progress"

#### Issue 2: Titles stuck at "pending"

**Location**: `whakoom_webscrapper/pipelines.py:155-190`

The `_process_titles_item` method inserts titles with status "pending" but **never updates** to "completed":

```python
def _process_titles_item(self, item: TitlesItem, spider: Spider) -> None:
    self.sql_manager.execute_parametrized_query(
        "INSERT_OR_IGNORE_TITLE", (...)
    )
    self.processed_title_ids.add(item.title_id)
    # ❌ No status update to "completed"
```

**Problem**: Titles are inserted as "pending" for future processing by a `titles` spider (which doesn't exist yet), but for the Publications spider workflow, titles should be marked "completed" after successful insertion.

#### Issue 3: Duplicate `close_spider` implementations

Two places update list status:
1. `pipelines.py:66-71` - Only for `spider.name == "publications"`
2. `publications.py:361-377` - Publications spider's own method

This creates ambiguity and potential race conditions.

### Current Database State

```
lists table:    60 entries, all "in_progress"
titles table:   1070 entries, all "pending"
```

### Target Behavior

After successful spider execution:
```
lists table:    60 entries, all "completed"
titles table:   1070 entries, all "completed"
```

---

## Phase 1: Fix Title Status Updates (Priority: CRITICAL)

### Goal
Update titles to "completed" when successfully processed by Publications spider.

### Tasks

#### 1.1 Update pipeline to set title status to "completed"

**File**: `whakoom_webscrapper/pipelines.py`

**Method**: `_process_titles_item` (lines 155-190)

**Action**: After successful title insertion, update status to "completed":

```python
def _process_titles_item(self, item: TitlesItem, spider: Spider) -> None:
    logging.info("Processing title: %s (title_id: %s)", item.title, item.title_id)

    self.sql_manager.log_scraping_operation(
        scrapper_name=spider.name,
        operation_type="title_processing",
        entity_id=item.title_id,
        status="started",
    )

    self.sql_manager.execute_parametrized_query(
        "INSERT_OR_IGNORE_TITLE",
        (
            item.title_id,
            item.title,
            item.url,
            item.scrape_status,
            item.scraped_at,
            1 if item.is_single_volume else 0,
        ),
    )

    # ✅ NEW: Update title status to "completed" after successful insert
    self.sql_manager.execute_parametrized_query(
        "UPDATE_TITLE_STATUS", ("completed", item.title_id)
    )

    self.processed_title_ids.add(item.title_id)

    self.sql_manager.log_scraping_operation(
        scrapper_name=spider.name,
        operation_type="title_processing",
        entity_id=item.title_id,
        status="success",
    )
```

**Rationale**: This ensures titles are marked "completed" as soon as they're successfully inserted. The `UPDATE_TITLE_STATUS` query already exists in `titles.sql`.

#### 1.2 Update spider to pass correct initial status

**File**: `whakoom_webscrapper/spiders/publications.py`

**Method**: `parse_volume_page` (line 275)

**Current**:
```python
yield TitlesItem(
    title_id=title_id,
    url=...,
    title=volume_name,
    scrape_status="pending",  # ❌ Wrong for current workflow
    is_single_volume=is_single_volume,
)
```

**Action**: Keep as "pending" to maintain backward compatibility with future `titles` spider. The pipeline will immediately update to "completed" after insert.

**Alternative**: Could pass "completed" directly, but "pending" allows for a future titles spider to process metadata.

**Decision**: Keep "pending" in spider, let pipeline update to "completed".

---

## Phase 2: Implement Robust List Status Tracking (Priority: CRITICAL)

### Goal
Track all lists that start processing and ensure they're marked "completed" even if processing is interrupted, using Option A (two-track tracking).

### Tasks

#### 2.1 Add `started_list_ids` tracking set

**File**: `whakoom_webscrapper/spiders/publications.py`

**Method**: `__init__` (line 58)

**Action**: Add new tracking set for lists that start processing:

```python
def __init__(self, *args: Any, mode: str = "pending", **kwargs: Any) -> None:
    super().__init__(*args, **kwargs)
    self.mode = mode
    self.driver: webdriver.Chrome | None = None

    db_path = Path(__file__).parent.parent.parent / "databases" / "publications.db"
    queries_dir = Path(__file__).parent.parent / "queries"
    migrations_dir = Path(__file__).parent.parent / "migrations"

    self.sql_manager = SQLManager(
        db_path=str(db_path),
        sql_dir=str(queries_dir),
        migrations_dir=str(migrations_dir),
    )

    self.started_list_ids: set[int] = set()  # ✅ NEW: Track all lists that started
    self.processed_list_ids: set[int] = set()  # Keep: Track lists with successful item processing
```

**Rationale**: Two separate sets allow us to distinguish between:
- Lists that started processing (may have partial or full success)
- Lists that successfully processed all items (full success)

#### 2.2 Add list to `started_list_ids` when processing begins

**File**: `whakoom_webscrapper/spiders/publications.py`

**Method**: `parse_list` (line 128-208)

**Action**: Add list to `started_list_ids` immediately after status update to "in_progress":

```python
def parse_list(self, response: Response) -> Iterator:
    list_xpath = '//*[@id="list"]/h1/'

    user_profile = response.xpath(
        '//*[@id="list"]/div[1]/p[2]/span[1]/strong/a/text()'
    ).get()
    list_name = response.xpath(f"{list_xpath}span/text()").get()
    list_amount = response.xpath(f"{list_xpath}small/text()").get()

    self.logger.info(
        f"Scraping list '{list_name}' by user '{user_profile}' with {list_amount}."
    )

    db_list_id = response.meta["db_id"]
    whakoom_list_id = response.meta["list_id"]

    self.sql_manager.update_single_field(
        "lists", "id", db_list_id, "scrape_status", "in_progress"
    )

    self.started_list_ids.add(db_list_id)  # ✅ NEW: Track that this list started

    # ... rest of method unchanged ...
```

**Rationale**: By adding to `started_list_ids` immediately after setting status to "in_progress", we ensure this list will be marked "completed" on spider close regardless of what happens next.

#### 2.3 Update `close_spider` to use two-track completion logic

**File**: `whakoom_webscrapper/spiders/publications.py`

**Method**: `close_spider` (line 361-377)

**Action**: Implement robust completion logic that handles all scenarios:

```python
def close_spider(self, spider: Spider) -> None:
    """Update list statuses to 'completed' and cleanup resources.

    Completion strategy:
    - Lists in processed_list_ids: Successfully processed all items → "completed"
    - Lists in started_list_ids but not processed: Partial processing → "completed" (best effort)
    - Lists in neither set: Never started → leave as-is
    """
    # Complete lists that successfully processed items
    for db_list_id in self.processed_list_ids:
        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "completed"
        )
        self.logger.info("Marked list_id %s as completed (full success)", db_list_id)

    # Complete lists that started but didn't fully process (partial success)
    partially_completed = self.started_list_ids - self.processed_list_ids
    for db_list_id in partially_completed:
        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "completed"
        )
        self.logger.info(
            "Marked list_id %s as completed (partial success, %d lists completed)",
            db_list_id,
            len(partially_completed),
        )

    # Cleanup resources
    if self.driver is not None:
        self.driver.quit()
        self.driver = None

    self.sql_manager.log_scraping_operation(
        scrapper_name=self.name,
        operation_type="spider_finished",
        entity_id=0,
        status="success",
    )
```

**Rationale**: This approach ensures:
- All lists that started processing get marked "completed"
- Even if a crash occurs, lists are not stuck in "in_progress"
- Distinguishes between full and partial success for logging

#### 2.4 Add failed list tracking for errbacks

**File**: `whakoom_webscrapper/spiders/publications.py`

**Method**: `errback_list` (line 321-341)

**Action**: Add `failed_list_ids` set to track lists that failed:

```python
def __init__(self, *args: Any, mode: str = "pending", **kwargs: Any) -> None:
    # ... existing code ...
    self.started_list_ids: set[int] = set()
    self.processed_list_ids: set[int] = set()
    self.failed_list_ids: set[int] = set()  # ✅ NEW: Track failed lists
```

```python
def errback_list(self, failure: Any) -> None:
    """Handle list request failures.

    Args:
        failure: The failure object.
    """
    db_list_id = failure.request.meta["db_id"]  # ✅ Use db_id, not list_id

    self.logger.error("Request failed for db_list_id %s: %s", db_list_id, failure)

    self.failed_list_ids.add(db_list_id)  # ✅ Track as failed

    self.sql_manager.update_single_field(
        "lists", "id", db_list_id, "scrape_status", "failed"
    )

    self.sql_manager.log_scraping_operation(
        scrapper_name=self.name,
        operation_type="list_processing",
        entity_id=db_list_id,
        status="failed",
        error_message=str(failure),
    )
```

**Bug Fix**: `errback_list` was using `list_id` (Whakoom ID) instead of `db_id` (database primary key). This means it was updating the wrong rows!

**Note**: Also check if `db_id` exists in `failure.request.meta`. If not, need to add it when creating the request in `start_requests`.

```python
# In start_requests, meta already has "db_id":
meta={
    "list_id": list_id,      # Whakoom list_id
    "list_url": url,
    "db_id": list_data["id"],  # Database primary key ✅
}
```

#### 2.5 Update `close_spider` to exclude failed lists

**Action**: Modify `close_spider` to not mark failed lists as "completed":

```python
def close_spider(self, spider: Spider) -> None:
    """Update list statuses to 'completed' and cleanup resources.

    Completion strategy:
    - Failed lists: Keep status as "failed"
    - Lists in processed_list_ids: Successfully processed all items → "completed"
    - Lists in started_list_ids but not processed/failed: Partial success → "completed"
    """
    # Lists that already failed should stay failed
    completed_lists = (self.started_list_ids - self.failed_list_ids)

    # Lists that successfully processed all items
    for db_list_id in self.processed_list_ids:
        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "completed"
        )
        self.logger.info("Marked list_id %s as completed (full success)", db_list_id)

    # Lists that started but didn't fully process (partial success)
    partially_completed = completed_lists - self.processed_list_ids
    for db_list_id in partially_completed:
        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "completed"
        )
        self.logger.info(
            "Marked list_id %s as completed (partial success)",
            db_list_id,
        )

    # Cleanup resources
    if self.driver is not None:
        self.driver.quit()
        self.driver = None

    self.sql_manager.log_scraping_operation(
        scrapper_name=self.name,
        operation_type="spider_finished",
        entity_id=0,
        status="success",
    )
```

---

## Phase 3: Remove Duplicate Status Update Logic (Priority: MEDIUM)

### Goal
Eliminate ambiguity by removing the pipeline's list status update logic.

### Tasks

#### 3.1 Remove pipeline's list status update

**File**: `whakoom_webscrapper/pipelines.py`

**Method**: `close_spider` (line 53-73)

**Action**: Remove the conditional list status update:

```python
def close_spider(self, spider: Spider) -> None:
    """Log completion on spider completion.

    Args:
        spider (Spider): The spider instance that is being closed.
    """
    self.sql_manager.log_scraping_operation(
        scrapper_name=spider.name,
        operation_type="spider_finished",
        entity_id=0,
        status="success",
    )

    # ✅ REMOVED: List status update logic moved to PublicationsSpider.close_spider()
    # if spider.name == "publications":
    #     for list_id in self.processed_list_ids:
    #         self.sql_manager.execute_parametrized_query(
    #             "UPDATE_LIST_STATUS", ("completed", list_id)
    #         )

    logging.info("Spider finished for: %s", spider.name)
```

**Rationale**: The Publications spider now has complete control over list status updates, making the logic clearer and avoiding potential race conditions.

#### 3.2 Remove `processed_list_ids` from pipeline

**File**: `whakoom_webscrapper/pipelines.py`

**Method**: `__init__` (line 22-34)

**Action**: Remove the tracking variable since it's no longer needed:

```python
def __init__(self) -> None:
    """Initialize SQLManager with migrations and queries directories."""
    migrations_dir = Path(__file__).parent / "migrations"
    queries_dir = Path(__file__).parent / "queries"

    self.sql_manager = SQLManager(
        db_path=str(db_path),
        sql_dir=str(queries_dir),
        migrations_dir=str(migrations_dir),
    )

    # ✅ REMOVED: processed_list_ids (now handled by PublicationsSpider)
    # self.processed_list_ids: set[int] = set()
    self.processed_title_ids: set[int] = set()
    self.processed_relationship_ids: set[tuple[int, int]] = set()
```

Also remove the tracking line in `_process_lists_item`:

```python
def _process_lists_item(self, item: ListsItem, spider: Spider) -> None:
    # ... logging ...

    self.sql_manager.insert(ListsItem, item)

    # ✅ REMOVED: self.processed_list_ids.add(item.list_id)

    # ... logging ...
```

---

## Phase 4: Fix Existing Database State (Priority: HIGH)

### Goal
Reset existing "in_progress" and "pending" entries to "completed" so the database is in a clean state.

### Tasks

#### 4.1 Create a recovery migration

**File**: `whakoom_webscrapper/migrations/003_reset_stuck_statuses.sql`

```sql
-- Up
-- Update lists stuck in 'in_progress' to 'completed'
-- These lists were successfully processed but status wasn't updated
UPDATE lists
SET scrape_status = 'completed',
    scraped_at = CURRENT_TIMESTAMP
WHERE scrape_status = 'in_progress';

-- Update all titles to 'completed' since they were successfully inserted
-- but status was never updated
UPDATE titles
SET scrape_status = 'completed',
    scraped_at = CURRENT_TIMESTAMP
WHERE scrape_status = 'pending';

-- Log the recovery operation
INSERT INTO scraping_log (scrapper_name, operation_type, entity_id, status, error_message)
VALUES ('manual_recovery', 'status_reset', 0, 'success', 'Reset stuck statuses after spider fix');

-- Down
-- Rollback - not really applicable for this one-time fix
-- This migration is idempotent - can be run multiple times safely
```

**Rationale**: This one-time migration cleans up the current database state. The "Down" section is intentionally minimal since this is a recovery operation.

**Alternative**: Could also add a SQL script to run manually without migration system. Using migration ensures it's tracked and reproducible.

#### 4.2 Run the migration

**Action**: After applying code changes, run:

```bash
# The migration will auto-apply when spider runs
# Or manually trigger migration:
uv run python -c "
from whakoom_webscrapper.sqlmanager import SQLManager
from pathlib import Path

sql_manager = SQLManager(
    db_path='databases/publications.db',
    sql_dir='whakoom_webscrapper/queries',
    migrations_dir='whakoom_webscrapper/migrations',
)
sql_manager.apply_migrations()
"
```

---

## Phase 5: Testing & Validation (Priority: HIGH)

### Goal
Verify all status updates work correctly under various scenarios.

### Tasks

#### 5.1 Test title status updates

**Test Case**: Run publications spider and verify titles are marked "completed"

```bash
# Reset database state for testing
sqlite3 databases/publications.db "UPDATE titles SET scrape_status='pending';"

# Run spider
uv run scrapy crawl publications --loglevel=INFO

# Verify
sqlite3 databases/publications.db "SELECT scrape_status, COUNT(*) FROM titles GROUP BY scrape_status;"
```

**Expected Result**:
```
completed|1070
```

#### 5.2 Test list status updates - normal completion

**Test Case**: Run publications spider successfully and verify lists are marked "completed"

```bash
# Reset database state
sqlite3 databases/publications.db "UPDATE lists SET scrape_status='pending';"

# Run spider
uv run scrapy crawl publications --loglevel=INFO

# Verify
sqlite3 databases/publications.db "SELECT scrape_status, COUNT(*) FROM lists GROUP BY scrape_status;"
```

**Expected Result**:
```
completed|60
```

#### 5.3 Test list status updates - with partial failure

**Test Case**: Modify a list URL to cause failure, verify other lists still complete

```bash
# Mark one list with invalid URL
sqlite3 databases/publications.db "UPDATE lists SET url='https://invalid.example.com' WHERE id=1;"

# Run spider
uv run scrapy crawl publications --loglevel=INFO

# Verify
sqlite3 databases/publications.db "
SELECT scrape_status, COUNT(*) FROM lists
WHERE id=1 OR id IN (2, 3, 4, 5)
GROUP BY scrape_status;
"
```

**Expected Result**:
```
failed|1
completed|4
```

#### 5.4 Test spider interruption recovery

**Test Case**: Interrupt spider mid-execution, verify lists are still marked "completed"

```bash
# Reset database
sqlite3 databases/publications.db "UPDATE lists SET scrape_status='pending';"

# Run spider and interrupt after 5 seconds
timeout 5 uv run scrapy crawl publications || true

# Verify - should have some "completed" from lists that started
sqlite3 databases/publications.db "SELECT scrape_status, COUNT(*) FROM lists GROUP BY scrape_status;"
```

**Expected Result**:
```
completed|5-15  # Partially completed
in_progress|0   # Should not have any stuck
```

#### 5.5 Verify errback fixes

**Test Case**: Ensure failed lists use correct `db_id` not `list_id`

```bash
# Check logs for errback_list calls
uv run scrapy crawl publications --loglevel=ERROR 2>&1 | grep "Request failed"

# Verify failed lists in DB have correct status
sqlite3 databases/publications.db "SELECT id, list_id, scrape_status FROM lists WHERE scrape_status='failed';"
```

**Expected Result**: Failed rows should have `scrape_status='failed'` and correct `db_id` values.

#### 5.6 Test migration idempotency

**Test Case**: Run migration multiple times, ensure it doesn't cause issues

```bash
# Run migration
uv run python -c "from whakoom_webscrapper.sqlmanager import SQLManager; SQLManager(db_path='databases/publications.db', sql_dir='whakoom_webscrapper/queries', migrations_dir='whakoom_webscrapper/migrations').apply_migrations()"

# Run again
uv run python -c "from whakoom_webscrapper.sqlmanager import SQLManager; SQLManager(db_path='databases/publications.db', sql_dir='whakoom_webscrapper/queries', migrations_dir='whakoom_webscrapper/migrations').apply_migrations()"

# Verify no duplicate log entries
sqlite3 databases/publications.db "SELECT COUNT(*) FROM scraping_log WHERE scrapper_name='manual_recovery';"
```

**Expected Result**: Only 1 entry (migrations track applied versions).

---

## Phase 6: Code Quality & Linting (Priority: MEDIUM)

### Goal
Ensure all changes follow project coding standards.

### Tasks

#### 6.1 Run linting tools

```bash
# Check for code style issues
uv run ruff check whakoom_webscrapper/

# Format code
uv run black whakoom_webscrapper/

# Run pre-commit checks
uv run pre-commit run --all-files
```

#### 6.2 Fix any linting errors

- Ensure all type hints are correct
- Remove unused imports
- Check for code complexity issues

#### 6.3 Verify typing

```bash
# Run type checker if configured
uv run pyright whakoom_webscrapper/
```

---

## Implementation Order

### Priority 1 (Critical - Fix the bugs)
1. **Phase 1** - Fix title status updates (pipeline)
2. **Phase 2** - Implement robust list tracking (spider)
   - Tasks 2.1, 2.2, 2.3 (core tracking logic)
   - Task 2.4 (errback fix is critical bug fix)
   - Task 2.5 (exclude failed from completed)
3. **Phase 4** - Fix existing database state (migration)

### Priority 2 (Quality - Remove duplication)
4. **Phase 3** - Remove duplicate status update logic (pipeline cleanup)

### Priority 3 (Validation)
5. **Phase 5** - Testing & validation
6. **Phase 6** - Code quality & linting

---

## Success Criteria

✅ All titles marked "completed" after successful Publications spider run
✅ All lists marked "completed" after successful Publications spider run
✅ Failed lists correctly marked "failed" and not marked "completed"
✅ Lists never stuck in "in_progress" after spider completion
✅ Spider interruption still marks started lists as "completed"
✅ No duplicate status update logic between pipeline and spider
✅ Errback uses correct `db_id` for updates
✅ Existing database state cleaned up via migration
✅ All linting passes without errors
✅ All tests pass under normal, partial failure, and interruption scenarios

---

## Potential Risks & Mitigations

### Risk 1: Marking partially-failed lists as "completed"
**Issue**: Lists with some failed items but successful overall flow marked "completed"

**Mitigation**: This is acceptable for current workflow. Future enhancement could add granular item-level tracking, but current approach ensures lists aren't stuck.

### Risk 2: Migration affects production data
**Issue**: Running migration on live database might affect user expectations

**Mitigation**: Migration is idempotent and only resets "in_progress"/"pending" to "completed". Document clearly in migration comments.

### Risk 3: Errback fix affects historical data
**Issue**: Previous errback runs used wrong ID, may have updated wrong rows

**Mitigation**: Unlikely since errback rarely triggered. No recovery needed for historical incorrect updates.

### Risk 4: Spider interruption leaves driver in bad state
**Issue**: If spider crashes, Selenium driver might not quit properly

**Mitigation**: `close_spider` already handles cleanup. Consider adding `try/finally` wrapper in parse_list for driver cleanup.

### Risk 5: Migration version conflicts
**Issue**: Migration `003` might conflict if developer already has migration with same number

**Mitigation**: Check existing migrations before creating. Use next available number if needed.

---

## Notes for Future Work

1. **Granular status tracking**: Future could track individual title processing status per list
2. **Retry mechanism**: Could add logic to retry failed lists automatically
3. **Partial success metrics**: Track how many titles per list were successfully processed
4. **Monitoring**: Add metrics for lists with partial success vs full success
5. **Cleanup**: Consider adding scheduled job to clean up old stuck statuses

---

## Appendix: Code Changes Summary

### File: whakoom_webscrapper/pipelines.py

**Lines to modify**:
- `__init__`: Remove `processed_list_ids`
- `_process_titles_item`: Add `UPDATE_TITLE_STATUS` call
- `_process_lists_item`: Remove `processed_list_ids.add()`
- `close_spider`: Remove list status update logic

### File: whakoom_webscrapper/spiders/publications.py

**Lines to modify**:
- `__init__`: Add `started_list_ids`, `failed_list_ids`
- `parse_list`: Add `started_list_ids.add()`
- `parse_volume_page`: No changes (keeps `processed_list_ids.add()`)
- `errback_list`: Fix to use `db_id`, add `failed_list_ids.add()`
- `close_spider`: Rewrite with two-track completion logic

### File: whakoom_webscrapper/migrations/003_reset_stuck_statuses.sql

**New file** to create with migration script.

---

## Verification Checklist

After implementation, verify:

- [ ] Ran `uv run scrapy crawl lists` - lists created with "pending"
- [ ] Ran `uv run scrapy crawl publications` - no errors
- [ ] Checked database: All lists "completed"
- [ ] Checked database: All titles "completed"
- [ ] Interrupted spider mid-run: No lists stuck in "in_progress"
- [ ] Checked scraping_log: All operations logged correctly
- [ ] Ran linting: No errors
- [ ] Ran tests: All pass
- [ ] Checked migration: Applied successfully
- [ ] Documentation updated (if needed)
