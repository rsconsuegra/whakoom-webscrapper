# Getting Started

Quick start guide for running the Whakoom Manga Lists Scraper.

---

## Prerequisites

### Required Software

- **Python 3.12** or higher
- **uv** - Python package manager
- **ChromeDriver** - For Selenium browser automation

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd whakoom-webscrapper
   ```

2. **Install dependencies using uv:**
   ```bash
   uv sync
   ```

3. **Verify ChromeDriver is installed:**
   ```bash
   chromedriver --version
   ```
   If not installed, install it:
   - **macOS:** `brew install chromedriver`
   - **Linux:** `sudo apt-get install chromium-chromedriver`
   - **Windows:** Download from [ChromeDriver website](https://chromedriver.chromium.org/)

---

## Your First Scrape

### Step 1: Scrape Lists

Run the lists spider to collect all lists from the target user profile:

```bash
uv run scrapy crawl lists
```

**Expected Output:**
- Console logs showing scraping progress
- Lists stored in `databases/publications.db`
- Each list with `scrape_status='pending'`

### Step 2: Verify Lists in Database

Check the scraped lists:

```bash
sqlite3 databases/publications.db "SELECT list_id, title, scrape_status FROM lists;"
```

**Example Output:**
```
131178|Licencias Manga en Español 2025|pending
131179|Shonen Jump 2024|pending
...
```

### Step 3: Scrape Publications

Run the publications spider to process all pending lists:

```bash
uv run scrapy crawl publications
```

This will:
- Read all lists with `scrape_status='pending'`
- Process each list using Selenium
- Extract volume URLs and parent Title URLs
- Store volumes, titles, and list-title relationships

**Expected Output:**
- Console logs showing list processing
- Selenium browser activity (headless)
- Database updates for volumes, titles, and junction table

### Step 4: Verify Results

Check the scraped data:

```bash
# View titles
sqlite3 databases/publications.db "SELECT title_id, title, scrape_status FROM titles LIMIT 10;"

# View volumes for a specific title
sqlite3 databases/publications.db "SELECT volume_id, title_id FROM volumes WHERE title_id=673392;"

# View list-title relationships
sqlite3 databases/publications.db "SELECT lt.list_id, l.title, lt.title_id, t.title FROM lists_titles lt JOIN lists l ON lt.list_id = l.id JOIN titles t ON lt.title_id = t.title_id LIMIT 10;"

# Check list statuses
sqlite3 databases/publications.db "SELECT list_id, title, scrape_status FROM lists;"
```

---

## Checking Scraping Progress

### Monitor Status Updates

Track which lists have been processed:

```bash
sqlite3 databases/publications.db "SELECT scrape_status, COUNT(*) as count FROM lists GROUP BY scrape_status;"
```

**Expected Output:**
```
completed|15
pending|0
```

### View Scraping Log

Check recent scraping operations:

```bash
sqlite3 databases/publications.db "SELECT scrapper_name, operation_type, entity_id, status, timestamp FROM scraping_log ORDER BY timestamp DESC LIMIT 20;"
```

---

## Running with Different Modes

### Process All Lists (Re-scrape)

To re-process all lists regardless of status:

```bash
uv run scrapy crawl publications -a mode=all
```

This is useful for:
- Re-scraping after schema changes
- Updating stale data
- Testing spider behavior

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
uv run scrapy crawl publications --loglevel=DEBUG
```

### Custom Output Format

Export scraped items to JSON for inspection:

```bash
uv run scrapy crawl lists -o lists.json
uv run scrapy crawl publications -o publications.json
```

---

## Common Pitfalls

### Issue: ChromeDriver not found

**Error:** `WebDriverException: Message: 'chromedriver' executable needs to be in PATH`

**Solution:**
1. Install ChromeDriver using your package manager
2. Add ChromeDriver to your PATH
3. Verify with `chromedriver --version`

### Issue: Database locked

**Error:** `sqlite3.OperationalError: database is locked`

**Solution:**
- Ensure no other process is accessing the database
- Close any SQLite clients
- Wait a few seconds and retry

### Issue: No items yielded

**Error:** Spider runs but no data is saved to database

**Solution:**
1. Check logs for errors
2. Verify spider is yielding items: `uv run scrapy crawl publications --loglevel=DEBUG`
3. Check if list statuses are being updated in database
4. Inspect the scraping log table for failures

### Issue: Selenium timeout

**Error:** `TimeoutException: Element not found`

**Solution:**
1. Increase timeout in spider configuration
2. Check network connectivity
3. Verify Whakoom website is accessible
4. Try running with non-headless mode for debugging

---

## Next Steps

After your first successful scrape:

1. **Explore the data:**
   ```bash
   sqlite3 databases/publications.db
   ```

2. **Read detailed documentation:**
   - [Architecture Overview](architecture.md) - System design and components
   - [Scraping Workflows](workflows/) - Detailed spider workflows
   - [Database Schema](database/schema.md) - Database structure and relationships

3. **Run specific spiders:**
   ```bash
   uv run scrapy crawl lists
   uv run scrapy crawl publications
   ```

4. **Check documentation for troubleshooting:**
   - [Troubleshooting Guide](development/troubleshooting.md) - Common issues and solutions

---

## Useful Commands

```bash
# View all tables
sqlite3 databases/publications.db ".tables"

# View table schema
sqlite3 databases/publications.db ".schema titles"

# Count records per table
sqlite3 databases/publications.db "
SELECT 'lists' as table_name, COUNT(*) as count FROM lists
UNION ALL
SELECT 'titles', COUNT(*) FROM titles
UNION ALL
SELECT 'volumes', COUNT(*) FROM volumes;
"

# View applied migrations
sqlite3 databases/publications.db "SELECT * FROM migrations;"

# Check for failed operations
sqlite3 databases/publications.db "SELECT * FROM scraping_log WHERE status='failed' ORDER BY timestamp DESC LIMIT 10;"
```

---

## Need Help?

- Check the [Troubleshooting Guide](development/troubleshooting.md) for common issues
- Review [Scraping Workflows](workflows/) for detailed process information
- See [Contributing Guide](development/contributing.md) for development guidelines
