# Title Spider Workflow

**Status:** Future Work - Not Yet Implemented

This document outlines the planned workflow for the `TitleSpider` that will scrape detailed metadata for manga titles.

---

## Overview

**Spider:** `TitleSpider` (Future)
**File:** `whakoom_webscrapper/spiders/titles.py` (To be created)
**Purpose:** Scrape detailed metadata for each title
**Input:** Titles from database where `scrape_status='pending'`
**Output:** `TitleMetadataItem` instances
**Database Target:** `title_metadata` table
**Selenium:** TBD (depending on page complexity)

---

## Planned Functionality

### Entry Point

The spider will query the database for titles with `scrape_status='pending'`:

```python
def start_requests(self) -> Iterator[Request]:
    """Generate requests for titles from database."""
    titles_to_process = self._get_titles_to_process()

    for title_data in titles_to_process:
        title_id = title_data["title_id"]
        url = title_data["url"]

        yield Request(
            url=url,
            meta={
                "title_id": title_id,
                "title_url": url,
            },
            callback=self.parse_title,
            errback=self.errback_title,
        )
```

### Database Query

```sql
SELECT id, title_id, title, url, scrape_status, scraped_at
FROM titles
WHERE scrape_status = 'pending'
ORDER BY id;
```

---

## Page Processing

### Title Page Example

**URL:** `https://www.whakoom.com/ediciones/673392/rosen_blood`

**Expected Data to Extract:**

```python
TitleMetadataItem(
    title_id=673392,
    author='Kureishi',
    publisher='Panini Manga',
    demographic='Shojo',
    genre='Fantasy',
    themes=['Vampires', 'Romance'],
    original_title='Rosen Blood',
    description='Chloe lives in a world...',
    start_year=2018,
    end_year=None,
    status='Completed'
)
```

### Metadata Fields

| Field | Type | Description |
|--------|------|-------------|
| title_id | INTEGER | Unique title identifier (FK to titles table) |
| author | TEXT | Author name |
| publisher | TEXT | Publisher name |
| demographic | TEXT | Demographic (Shonen, Shojo, etc.) |
| genre | TEXT | Primary genre |
| themes | TEXT | Comma-separated themes |
| original_title | TEXT | Original title (if different from title) |
| description | TEXT | Synopsis/description |
| start_year | INTEGER | First publication year |
| end_year | INTEGER | Last publication year (NULL if ongoing) |
| status | TEXT | Publication status (Ongoing, Completed, etc.) |

---

## XPath Selectors

**Note:** These XPath selectors are placeholders and will need to be updated based on actual HTML structure.

### Example Selectors (To Be Verified)

```python
def parse_title(self, response: Response) -> Iterator[TitleMetadataItem]:
    """Parse title page and extract metadata."""

    title_id = response.meta["title_id"]

    # Extract metadata (XPath selectors TBD)
    author = response.xpath('//div[@class="author"]/text()').get()
    publisher = response.xpath('//div[@class="publisher"]/text()').get()
    demographic = response.xpath('//div[@class="demographic"]/text()').get()
    genre = response.xpath('//div[@class="genre"]/text()').get()
    description = response.xpath('//div[@class="description"]/text()').get()
    start_year = response.xpath('//div[@class="start-year"]/text()').get()
    status = response.xpath('//div[@class="status"]/text()').get()

    yield TitleMetadataItem(
        title_id=title_id,
        author=author,
        publisher=publisher,
        demographic=demographic,
        genre=genre,
        description=description,
        start_year=int(start_year) if start_year else None,
        status=status,
    )
```

---

## Pipeline Processing

### TitleMetadataItem Processing

**Database Table:** `title_metadata`

**SQL Query:**
```sql
INSERT INTO title_metadata (title_id, author, publisher, demographic, genre, themes, original_title, description, start_year, end_year, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (title_id) DO UPDATE SET
    author = excluded.author,
    publisher = excluded.publisher,
    demographic = excluded.demographic,
    genre = excluded.genre,
    themes = excluded.themes,
    original_title = excluded.original_title,
    description = excluded.description,
    start_year = excluded.start_year,
    end_year = excluded.end_year,
    status = excluded.status,
    updated_at = CURRENT_TIMESTAMP;
```

### Status Update

After successful metadata extraction, update title status:

```sql
UPDATE titles
SET scrape_status = 'completed', scraped_at = CURRENT_TIMESTAMP
WHERE title_id = ?;
```

---

## Command Line Usage

**When Implemented:**

```bash
# Scrape pending titles
uv run scrapy crawl titles

# Enable debug logging
uv run scrapy crawl titles --loglevel=DEBUG

# Export to JSON for inspection
uv run scrapy crawl titles -o titles_metadata.json
```

---

## Implementation Checklist

### Phase 1: Initial Implementation
- [ ] Create `whakoom_webscrapper/spiders/titles.py`
- [ ] Define `TitleSpider` class
- [ ] Implement `start_requests()` to query database
- [ ] Implement `parse_title()` method
- [ ] Add XPath selectors for metadata extraction
- [ ] Test with a single title URL

### Phase 2: Integration
- [ ] Update pipeline to handle `TitleMetadataItem`
- [ ] Create `title_metadata.sql` query file
- [ ] Add INSERT OR UPDATE query
- [ ] Test end-to-end with database

### Phase 3: Testing
- [ ] Test with various title types (ongoing, completed, single volume)
- [ ] Verify all metadata fields are extracted correctly
- [ ] Test error handling (missing fields, invalid data)
- [ ] Add unit tests for URL parsing
- [ ] Add integration tests for database flow

### Phase 4: Documentation
- [ ] Update this document with actual XPath selectors
- [ ] Add examples of extracted metadata
- [ ] Document any edge cases or special handling

---

## Development Notes

### To Be Determined

1. **Selenium vs Scrapy Only:**
   - Will title pages require Selenium for dynamic content?
   - Can we use Scrapy selectors only?

2. **Metadata Availability:**
   - Are all planned metadata fields available on the page?
   - Are there any fields that require additional page requests?

3. **Data Formats:**
   - How are themes represented? (Comma-separated? Array?)
   - How is date format? (YYYY? MM/YYYY?)
   - How is status represented? (Text? Code?)

4. **Pagination:**
   - Are there multiple pages for metadata?
   - How to navigate if metadata is paginated?

### Testing Strategy

When implementing, start with a known title:

```python
# Test with Rosen Blood
test_url = "https://www.whakoom.com/ediciones/673392/rosen_blood"
```

Use Scrapy shell to inspect the HTML:

```bash
uv run scrapy shell "https://www.whakoom.com/ediciones/673392/rosen_blood"
```

Then experiment with XPath selectors until all metadata is extracted.

---

## Related Documentation

- [Complete Scraping Workflow](scraping-flow.md) - End-to-end flow
- [Publications Spider Workflow](publications-spider-workflow.md) - Previous stage
- [Database Schema](../database/schema.md) - title_metadata table documentation
- [Adding Spiders](../development/adding-spiders.md) - Guide for creating new spiders

---

## Next Steps

**For Implementation:**
1. Inspect actual Whakoom title page HTML structure
2. Determine required metadata fields and their locations
3. Create XPath selectors for each field
4. Implement spider with database integration
5. Test with various title types
6. Document findings and update this file

**For Review:**
1. Review this document once spider is implemented
2. Add actual XPath selectors used
3. Add real examples of extracted data
4. Update any assumptions that proved incorrect
