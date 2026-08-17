# Publications Spider DB Integration Plan

## Context

This plan outlines the refactoring of `publications.py` spider to integrate it with the database layer, enabling proper data persistence and workflow orchestration.

### Current State

**What Works:**
- `lists.py` spider successfully scrapes and stores lists in `lists` table
- Database schema is well-designed with proper relationships
- Pipeline infrastructure exists and works for ListsItem
- SQLManager provides all necessary DB operations

**What Doesn't Work:**
- `publications.py` spider doesn't read from DB (expects URL as argument)
- Publications spider doesn't yield proper items that the pipeline can process
- No connection between lists → volumes → titles
- Title extraction logic is flawed (uses incremental index instead of real ID)
- No volume data being captured despite scraping volume URLs
- No status updates on lists during/after processing

### Real-World Flow Example

```
1. lists.py scrapes: https://www.whakoom.com/deirdre/lists/
   → Finds lists like: https://www.whakoom.com/deirdre/lists/licencias_manga_en_espana_2025_131178

2. publications.py processes each list:
   → Finds volume links like: https://www.whakoom.com/comics/fxTr6/rosen_blood/1
      where: fxTr6 = unique volume_id, 1 = volume_number

3. Follows volume link to get parent Title URL:
   → Extracts: https://www.whakoom.com/ediciones/673392/rosen_blood
      where: 673392 = unique numeric title_id

4. Stores in DB:
   - volumes table: volume_id='fxTr6', title_id=673392, url='...'
   - titles table: title_id=673392, url='...', title='Rosen Blood'
   - lists_titles: junction table linking list → title
```

### Target Architecture

```
┌─────────────────┐
│  lists.py       │  Scrapes lists from user profile
│  Spider         │  → Stores in 'lists' table with status='pending'
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  publications.py│  Reads lists from DB (mode='pending' or 'all')
│  Spider         │  → For each list:
└────────┬────────┘     1. Updates list status to 'in_progress'
         │               2. Scrapes all volumes from list (volume URLs)
         │               3. Follows each volume link to get parent Title URL
         │               4. Extracts volume_id and title_id from URLs
         │               5. Yields VolumesItem (volume_id, title_id, url)
         │               6. Yields TitlesItem (title_id, url, title)
         │               7. Yields TitlesListItem (list_id, title_id)
         │               8. Updates list status to 'completed'
         ▼
┌─────────────────┐
│  Pipeline       │  Processes all items with deduplication
│                 │  - Titles: INSERT OR IGNORE (keep first occurrence)
│                 │  - Volumes: Store volume_id and title_id reference
│                 │  - TitlesList: Junction table for many-to-many
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  titles.py      │  (Future) Reads titles with status='pending'
│  Spider         │  → Scrapes title metadata, descriptions, etc.
└─────────────────┘
```

---

## Phase 1: Database Layer Improvements (Priority: HIGH)

### Goal
Add necessary SQL queries to support publications spider workflow.

### Tasks

#### 1.1 Create titles.sql query file
**File:** `whakoom_webscrapper/queries/titles.sql`

Required queries:
- `INSERT_OR_IGNORE_TITLE` - Insert title with ON CONFLICT DO NOTHING
- `GET_TITLE_BY_ID` - Select title by title_id
- `GET_TITLES_BY_STATUS` - Select titles by scrape_status
- `UPDATE_TITLE_STATUS` - Update title status by title_id

**Query Example:**
```sql
# INSERT_OR_IGNORE_TITLE
INSERT INTO titles (title_id, title, url, scrape_status, scraped_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (title_id) DO NOTHING;
```

#### 1.2 Create volumes.sql query file
**File:** `whakoom_webscrapper/queries/volumes.sql`

Required queries:
- `INSERT_OR_UPDATE_VOLUME` - Insert volume with ON CONFLICT DO UPDATE
- `GET_VOLUME_BY_ID` - Select volume by volume_id
- `GET_VOLUMES_BY_TITLE_ID` - Select all volumes for a title

**Query Example:**
```sql
# INSERT_OR_UPDATE_VOLUME
INSERT INTO volumes (volume_id, title_id, url)
VALUES (?, ?, ?)
ON CONFLICT (volume_id) DO UPDATE SET
    title_id = excluded.title_id,
    url = excluded.url,
    updated_at = CURRENT_TIMESTAMP;
```

**Note:** Ignoring volume_number, isbn, publisher, year for now (will be reworked later).

#### 1.3 Update lists.sql queries
**File:** `whakoom_webscrapper/queries/lists.sql`

Add query:
- `GET_LISTS_FOR_PROCESSING` - Select lists based on mode parameter
- Returns lists with pending status or all lists based on mode

---

## Phase 2: Model Updates (Priority: HIGH)

### Goal
Ensure dataclass models support proper ID extraction and field ordering.

### Tasks

#### 2.1 Fix TitlesItem field ordering
**File:** `whakoom_webscrapper/models/__init__.py`

Current `to_tuple()` order:
```python
(title_id, title, scrape_status, scraped_at, title_url)
```

Database schema order:
```sql
(title_id, title, url, scrape_status, scraped_at)
```

**Action:** Update `to_tuple()` to match DB schema order.

#### 2.2 Document VolumesItem usage
Currently VolumesItem exists with many fields (isbn, publisher, year, etc.).

**Action:** Document that for this phase, we only populate:
- `volume_id` (string ID from URL like 'fxTr6')
- `title_id` (numeric ID from Title URL like 673392)
- `url` (full volume URL)

Other fields (volume_number, isbn, publisher, year) will be populated in future volume rework.

#### 2.3 Verify TitlesListItem works correctly
Currently exists and should work - verify pipeline `_process_titles_list_item()` handles it properly.

---

## Phase 3: Publications Spider Refactoring (Priority: CRITICAL)

### Goal
Rewrite `publications.py` to:
1. Read lists from database
2. Process each list through Selenium
3. Extract volume URLs and parent Title URLs
4. Parse volume_id and title_id from URLs
5. Yield proper items (VolumesItem, TitlesItem, TitlesListItem)
6. Update list status appropriately

### Tasks

#### 3.1 Add database query method to spider
Add `__init__` method that initializes SQLManager for querying lists.

**Key changes:**
- Import SQLManager
- Initialize in `__init__` with mode parameter ('pending' or 'all')
- Add method `_get_lists_to_process()` that queries DB based on mode

#### 3.2 Replace `start_urls` with `start_requests()`
Instead of fixed URLs, query database and generate requests dynamically.

```python
def start_requests(self) -> Iterator[Request]:
    """Generate requests for lists from database."""
    lists_to_process = self._get_lists_to_process()

    for list_data in lists_to_process:
        list_id = list_data["list_id"]
        url = list_data["url"]

        yield Request(
            url=url,
            meta={
                "list_id": list_id,
                "list_url": url,
            },
            callback=self.parse_list,
            errback=self.errback_list,
        )
```

#### 3.3 Update `parse()` method
Rename to `parse_list()` and restructure:
- Parse list metadata (user_profile, list_name, list_amount)
- Update list status to 'in_progress'
- Initialize Selenium driver
- Scroll to load all items (existing logic)
- Extract volume items from `//span[@class="title"]/a` elements
- Extract volume URLs (these are volume URLs, not title URLs)
- Follow each volume link to get parent Title URL
- Yield items

**Example volume URL parsing:**
```
Volume URL: https://www.whakoom.com/comics/fxTr6/rosen_blood/1
- volume_id = 'fxTr6' (middle segment)
- volume_number = 1 (last segment) - IGNORE for now
```

#### 3.4 Update `parse_title()` method
Rename to `parse_volume_page()` and restructure:
- Extract parent Title URL from volume page using existing xpath
  - Current: `response.xpath('//*[@id="content"]/div/div/p[1]/a').attrib.get("href", "")`
- Parse title_id from Title URL (numeric ID)
- Parse volume_id from current volume URL
- Yield VolumesItem with volume_id, title_id, and url
- Yield TitlesItem with title_id, url, and title (will be deduplicated in DB)
- Yield TitlesListItem to link list → title

**Example Title URL parsing:**
```
Title URL: https://www.whakoom.com/ediciones/673392/rosen_blood
- title_id = 673392 (numeric ID from URL)
```

#### 3.5 Add URL parsing helper methods
Add methods to extract IDs from URLs:

```python
def _extract_volume_id_from_url(self, url: str) -> str:
    """Extract volume_id from volume URL.

    Example:
    https://www.whakoom.com/comics/fxTr6/rosen_blood/1 → 'fxTr6'

    Args:
        url: The volume URL.

    Returns:
        The volume ID extracted from the URL.
    """
    # Parse: /comics/{volume_id}/{title}/{volume_number}
    parts = url.rstrip('/').split('/')
    if 'comics' in parts:
        idx = parts.index('comics')
        if idx + 1 < len(parts):
            return parts[idx + 1]
    raise ValueError(f"Cannot extract volume_id from URL: {url}")

def _extract_title_id_from_url(self, url: str) -> int:
    """Extract numeric title_id from Title URL.

    Example:
    https://www.whakoom.com/ediciones/673392/rosen_blood → 673392

    Args:
        url: The Title URL.

    Returns:
        The numeric title ID.
    """
    # Parse: /ediciones/{title_id}/{title}
    parts = url.rstrip('/').split('/')
    if 'ediciones' in parts:
        idx = parts.index('ediciones')
        if idx + 1 < len(parts):
            return int(parts[idx + 1])
    raise ValueError(f"Cannot extract title_id from URL: {url}")
```

#### 3.6 Update item creation
Change from current approach (incremental index) to proper ID extraction:

**Current (WRONG):**
```python
for idx, title in enumerate(titles, start=1):
    title_name = title.get()
    item_url = title.attrib.get("href", "")
    yield TitlesItem(title_id=idx, ...)  # Wrong: uses incremental index
```

**New (CORRECT):**
```python
for title_element in titles:
    volume_url = title_element.attrib.get("href", "")
    volume_name = title_element.get()

    # Follow volume link to get Title URL
    yield Request(
        url=f"www.whakoom.com{volume_url}",
        meta={
            "volume_url": volume_url,
            "volume_name": volume_name,
            "list_id": response.meta["list_id"],
        },
        callback=self.parse_volume_page,
    )
```

Then in `parse_volume_page()`:
```python
def parse_volume_page(self, response: Response) -> Iterator:
    volume_url = response.meta["volume_url"]
    list_id = response.meta["list_id"]

    # Get parent Title URL
    title_url = response.xpath('//*[@id="content"]/div/div/p[1]/a').attrib.get("href", "")

    # Extract IDs
    volume_id = self._extract_volume_id_from_url(volume_url)
    title_id = self._extract_title_id_from_url(title_url)

    # Yield items
    yield VolumesItem(volume_id=volume_id, title_id=title_id, url=f"www.whakoom.com{volume_url}")
    yield TitlesItem(title_id=title_id, url=f"www.whakoom.com{title_url}", title=response.meta["volume_name"])
    yield TitlesListItem(list_id=list_id, title_id=title_id)
```

#### 3.7 Add error handling and status updates
- Add `errback_list()` method for request failures
- Update list status to 'failed' on error
- Log all errors with SQLManager

#### 3.8 Add `close_spider()` method
Update list statuses to 'completed' for successfully processed lists.

---

## Phase 4: Pipeline Updates (Priority: MEDIUM)

### Goal
Ensure pipeline properly handles all items and implements deduplication correctly.

### Tasks

#### 4.1 Use INSERT OR IGNORE for TitlesItem
Update `_process_titles_item()` in pipeline to use specific query with ON CONFLICT DO NOTHING.

**Action:** Use `INSERT_OR_IGNORE_TITLE` query from titles.sql.

#### 4.2 Update VolumesItem processing
Current `_process_volumes_item()` uses generic `insert()` which includes all fields.

**Action:** Since we're only populating volume_id, title_id, and url, ensure the query works with NULL values for other fields. Alternatively, create a simplified insert query for this phase.

#### 4.3 Ensure junction table works
Verify `_process_titles_list_item()` properly inserts into `lists_titles` table with `list_id` and `title_id`.

**Note:** `list_id` in `TitlesListItem` refers to the database `list_id` (primary key of lists table), not the Whakoom `list_id`. Need to ensure we're using the correct ID.

#### 4.4 Add list status tracking
Track which lists are being processed and update status appropriately:
- Set to 'in_progress' when starting a list
- Set to 'completed' when all items from list are processed
- Set to 'failed' if any errors occur

**Current behavior:** Pipeline updates to 'completed' on spider close for all processed lists. This is acceptable, but we could add more granular tracking.

---

## Phase 5: Testing & Validation (Priority: HIGH)

### Goal
Test the complete workflow end-to-end with real Whakoom URLs.

### Tasks

#### 5.1 Unit tests
- Test URL parsing methods with real URLs:
  - `https://www.whakoom.com/comics/fxTr6/rosen_blood/1` → volume_id='fxTr6'
  - `https://www.whakoom.com/ediciones/673392/rosen_blood` → title_id=673392
- Test item creation with correct IDs
- Test SQL queries with various inputs

#### 5.2 Integration tests
- Test complete flow: lists → publications → DB
- Verify deduplication works (same title in multiple lists)
- Verify status updates work correctly
- Verify junction table entries are correct
- Verify volume_id is properly stored as string
- Verify title_id is properly stored as integer

#### 5.3 Manual testing
- Run `uv run scrapy crawl lists` - verify lists are stored with status='pending'
- Run `uv run scrapy crawl publications` (mode='pending') - verify:
  - Lists are updated to 'in_progress' → 'completed'
  - Volumes are stored with correct volume_id and title_id
  - Titles are stored with correct title_id (deduplicated)
  - Junction table has correct list_id → title_id mappings
- Check database directly to verify data integrity:
  ```sql
  SELECT * FROM lists WHERE user_profile='deirdre';
  SELECT * FROM volumes WHERE title_id=673392;
  SELECT * FROM titles WHERE title_id=673392;
  SELECT * FROM lists_titles WHERE list_id=123;
  ```
- Run `uv run scrapy crawl publications` (mode='all') - verify rebuild works

#### 5.4 Data validation queries
Run SQL queries to verify:
- All lists have status in ('pending', 'in_progress', 'completed', 'failed')
- All titles have unique title_id (no duplicates in titles table)
- All volumes have unique volume_id
- Volumes table has correct title_id references (foreign key integrity)
- Junction table has correct counts per list
- Same title appearing in multiple lists results in:
  - 1 entry in titles table (deduplication)
  - Multiple entries in lists_titles (one per list)

---

## Phase 6: Documentation & Cleanup (Priority: LOW)

### Goal
Document the new workflow and clean up any technical debt.

### Tasks

#### 6.1 Update README
Add section on spider execution order:
1. Run `uv run scrapy crawl lists`
2. Run `uv run scrapy crawl publications`
3. (Future) Run `uv run scrapy crawl titles`

Add URL format documentation:
- Volume URL: `https://www.whakoom.com/comics/{volume_id}/{title_name}/{volume_number}`
- Title URL: `https://www.whakoom.com/ediciones/{title_id}/{title_name}`

#### 6.2 Add usage examples
Add examples in README:
- How to run publications spider in pending mode
- How to run publications spider in all mode
- How to check scraping progress via SQL queries
- Example SQL queries for data validation

#### 6.3 Clean up old code
Remove any unused imports or methods in publications.py (e.g., old incremental index logic).

#### 6.4 Update AGENTS.md
If any new patterns or conventions emerge during refactoring, update AGENTS.md.

#### 6.5 Document volume_id as string
Since volume_id can be alphanumeric (e.g., 'fxTr6'), document this clearly for future developers.

---

## Implementation Order

### Priority 1 (Critical Path)
1. Phase 1 - Database queries (titles.sql, volumes.sql)
2. Phase 2 - Model field ordering fix
3. Phase 3 - Publications spider rewrite (main task)
4. Phase 5 - Basic testing with real URLs

### Priority 2 (Quality & Reliability)
5. Phase 4 - Pipeline improvements
6. Phase 5 - Comprehensive testing

### Priority 3 (Polish)
7. Phase 6 - Documentation and cleanup

---

## Success Criteria

✅ Publications spider reads lists from database (not hardcoded URLs)
✅ Each list's status is updated to 'in_progress' → 'completed'
✅ Volume URLs are stored in volumes table with volume_id (string) and title_id (integer)
✅ Title URLs are stored in titles table with numeric title_id
✅ Title IDs are extracted from URLs (not incremental index)
✅ Title deduplication works (same title in multiple lists = one entry in titles table)
✅ Junction table correctly links lists → titles
✅ Pipeline handles all item types with proper error handling
✅ All SQL queries use parameterized queries (no string interpolation)
✅ URL parsing works with real Whakoom URL formats
✅ Tests cover critical paths
✅ Documentation is updated with URL format examples

---

## Potential Risks & Mitigations

### Risk 1: Title ID extraction fails
**Mitigation:** Add robust URL parsing with error handling, log failures, fallback to using URL as ID

### Risk 2: Volume ID is alphanumeric
**Mitigation:** Ensure volumes table volume_id column is TEXT type (it is), document this clearly

### Risk 3: Title ID is numeric but stored as string
**Mitigation:** Ensure proper type conversion when extracting title_id (int), database schema has INTEGER type

### Risk 4: Selenium memory issues with large lists
**Mitigation:** Add list size limits, batch processing, or driver reinitialization per list

### Risk 5: Duplicate detection not working
**Mitigation:** Test thoroughly with same title across multiple lists, verify INSERT OR IGNORE behavior

### Risk 6: Database lock issues with concurrent inserts
**Mitigation:** Use transactions properly, consider connection pooling if needed

### Risk 7: List status updates fail mid-processing
**Mitigation:** Add retry logic for status updates, log all failures, manual recovery procedures

### Risk 8: volume_number is ignored
**Mitigation:** Document clearly that volume_number will be handled in future volume rework, ensure it's nullable in schema

---

## Notes for Future Work

1. **Titles spider** will read from `titles` table where `scrape_status='pending'`
2. **Volume metadata** (ISBN, publisher, year, volume_number) will be reworked in future phases
3. **Volume rework** - Future phase to populate all VolumesItem fields from volume pages
4. **Enrichment** (MyAnimeList, MangaUpdates data) will populate `title_enriched` table
5. **Performance** - Consider async processing for large lists, caching volume_id/title_id extractions
6. **Monitoring** - Add metrics for scraped counts, success rates, errors per list
7. **Recovery** - Add procedures for retrying failed lists, handling partial scrapes

---

## Appendix: URL Format Reference

### Volume URLs
**Format:** `https://www.whakoom.com/comics/{volume_id}/{title_slug}/{volume_number}`

**Examples:**
- `https://www.whakoom.com/comics/fxTr6/rosen_blood/1` → volume_id='fxTr6', volume_number=1
- `https://www.whakoom.com/comics/abc123/one_piece/2` → volume_id='abc123', volume_number=2

**Extraction:**
```python
# volume_id = middle segment after '/comics/'
volume_id = url.split('/')[4]  # e.g., 'fxTr6'
```

### Title URLs
**Format:** `https://www.whakoom.com/ediciones/{title_id}/{title_slug}`

**Examples:**
- `https://www.whakoom.com/ediciones/673392/rosen_blood` → title_id=673392
- `https://www.whakoom.com/ediciones/123456/one_piece` → title_id=123456

**Extraction:**
```python
# title_id = middle segment after '/ediciones/'
title_id = int(url.split('/')[4])  # e.g., 673392
```

### List URLs
**Format:** `https://www.whakoom.com/{user_profile}/lists/{list_name}_{list_id}`

**Examples:**
- `https://www.whakoom.com/deirdre/lists/licencias_manga_en_espana_2025_131178` → list_id=131178

**Note:** list_id extraction already implemented in lists.py spider.
