# Queries Reference

Complete reference for all named SQL queries organized by table.

---

## Overview

Named queries are stored in `.sql` files in `whakoom_webscrapper/queries/`.

### Query Format

```sql
# QUERY_NAME
SELECT * FROM table WHERE field = ?;
```

**Rules:**
- Query name starts with `#` on its own line
- Query name is case-insensitive (converted to uppercase)
- Use `?` placeholders for parameters (SQL injection safe)

### Loading Queries

Queries are automatically loaded by SQLManager on initialization:

```python
sql_manager = SQLManager(
    db_path="databases/publications.db",
    sql_dir="whakoom_webscrapper/queries"
)

# Access query
query = sql_manager.queries['GET_LISTS_BY_STATUS']
```

---

## Lists Queries

**File:** `whakoom_webscrapper/queries/lists.sql`

### INSERT_OR_UPDATE_LIST

Insert or update a list record.

**Purpose:** Add new lists or update existing ones.

**SQL:**
```sql
INSERT INTO lists (list_id, title, url, user_profile, scrape_status, scraped_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (list_id) DO UPDATE SET
    title = excluded.title,
    url = excluded.url,
    scrape_status = excluded.scrape_status,
    scraped_at = excluded.scraped_at,
    updated_at = CURRENT_TIMESTAMP;
```

**Parameters:**
1. `list_id` (INTEGER) - Whakoom's internal list ID
2. `title` (TEXT) - List title
3. `url` (TEXT) - Full list URL
4. `user_profile` (TEXT) - Whakoom username
5. `scrape_status` (TEXT) - Status value
6. `scraped_at` (TIMESTAMP|NULL) - Scraping timestamp

**Behavior:**
- INSERTS new record
- On CONFLICT (list_id): UPDATES all fields except id
- Sets `updated_at = CURRENT_TIMESTAMP`

**Example Usage:**
```python
sql_manager.execute_parametrized_query(
    "INSERT_OR_UPDATE_LIST",
    (131178, "Licencias Manga en Español 2025",
     "https://www.whakoom.com/deirdre/lists/...", "deirdre",
     "pending", None)
)
```

---

### GET_LISTS_BY_STATUS

Select lists by scrape_status.

**Purpose:** Get lists with a specific status (e.g., pending, completed).

**SQL:**
```sql
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
```

**Parameters:**
1. `scrape_status` (TEXT) - Status to filter by

**Returns:** List of tuples with columns: `(id, list_id, title, url, user_profile, scrape_status, scraped_at)`

**Example Usage:**
```python
results = sql_manager.execute_parametrized_query(
    "GET_LISTS_BY_STATUS",
    ("pending",)
)

for row in results:
    list_id, title, scrape_status = row[1], row[2], row[5]
    print(f"{list_id}: {title} ({scrape_status})")
```

---

### GET_LISTS_BY_USER_PROFILE

Select all lists for a specific user.

**Purpose:** Get lists belonging to a user profile.

**SQL:**
```sql
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
```

**Parameters:**
1. `user_profile` (TEXT) - Whakoom username

**Returns:** List of tuples with columns: `(id, list_id, title, url, user_profile, scrape_status, scraped_at)`

**Example Usage:**
```python
results = sql_manager.execute_parametrized_query(
    "GET_LISTS_BY_USER_PROFILE",
    ("deirdre",)
)

for row in results:
    list_id, title = row[1], row[2]
    print(f"{list_id}: {title}")
```

---

### UPDATE_LIST_STATUS

Update a list's scrape status.

**Purpose:** Mark list as in_progress, completed, or failed.

**SQL:**
```sql
UPDATE lists
SET scrape_status = ?, scraped_at = CURRENT_TIMESTAMP
WHERE list_id = ?;
```

**Parameters:**
1. `scrape_status` (TEXT) - New status value
2. `list_id` (INTEGER) - Whakoom's list ID

**Returns:** Empty list (UPDATE doesn't return rows)

**Example Usage:**
```python
# Mark as in_progress
sql_manager.execute_parametrized_query(
    "UPDATE_LIST_STATUS",
    ("in_progress", 131178)
)

# Mark as completed
sql_manager.execute_parametrized_query(
    "UPDATE_LIST_STATUS",
    ("completed", 131178)
)
```

---

### GET_LIST_BY_ID

Select a single list by its ID.

**Purpose:** Get specific list details.

**SQL:**
```sql
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
```

**Parameters:**
1. `list_id` (INTEGER) - Whakoom's list ID

**Returns:** List with one tuple (or empty if not found)

**Example Usage:**
```python
results = sql_manager.execute_parametrized_query(
    "GET_LIST_BY_ID",
    (131178,)
)

if results:
    id, list_id, title, url, user_profile, scrape_status, scraped_at = results[0]
    print(f"Found: {title}")
else:
    print("Not found")
```

---

### GET_ALL_LISTS

Select all lists.

**Purpose:** Get complete list of all lists in database.

**SQL:**
```sql
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
```

**Parameters:** None

**Returns:** List of tuples with all list records

**Example Usage:**
```python
results = sql_manager.execute_parametrized_query("GET_ALL_LISTS", ())

for row in results:
    id, list_id, title = row[0], row[1], row[2]
    print(f"{id}: {list_id} - {title}")
```

---

## Future Queries

### Titles Queries (To Be Created)

**File:** `whakoom_webscrapper/queries/titles.sql` (To be created)

**Planned Queries:**
- `INSERT_OR_IGNORE_TITLE` - Insert title with ON CONFLICT DO NOTHING
- `GET_TITLE_BY_ID` - Select title by title_id
- `GET_TITLES_BY_STATUS` - Select titles by scrape_status
- `UPDATE_TITLE_STATUS` - Update title scrape status

### Volumes Queries (To Be Created)

**File:** `whakoom_webscrapper/queries/volumes.sql` (To be created)

**Planned Queries:**
- `INSERT_OR_UPDATE_VOLUME` - Insert volume with ON CONFLICT DO UPDATE
- `GET_VOLUME_BY_ID` - Select volume by volume_id
- `GET_VOLUMES_BY_TITLE_ID` - Select all volumes for a title
- `GET_VOLUMES_BY_STATUS` - Select volumes by scrape_status

### Title Metadata Queries (To Be Created)

**File:** `whakoom_webscrapper/queries/title_metadata.sql` (To be created)

**Planned Queries:**
- `INSERT_OR_UPDATE_TITLE_METADATA` - Insert title metadata
- `GET_TITLE_METADATA_BY_ID` - Select metadata by title_id

---

## Common Query Patterns

### Pattern 1: Insert or Update

```sql
INSERT INTO table (col1, col2, col3)
VALUES (?, ?, ?)
ON CONFLICT (unique_col) DO UPDATE SET
    col1 = excluded.col1,
    col2 = excluded.col2,
    updated_at = CURRENT_TIMESTAMP;
```

**Use Case:** Add or update records without duplicates.

### Pattern 2: Select with Filter

```sql
SELECT
    col1,
    col2,
    col3
FROM table
WHERE filter_col = ?
ORDER BY sort_col;
```

**Use Case:** Get records matching specific criteria.

### Pattern 3: Update Single Field

```sql
UPDATE table
SET field = ?, updated_at = CURRENT_TIMESTAMP
WHERE id_col = ?;
```

**Use Case:** Status updates, timestamp updates.

### Pattern 4: Get by ID

```sql
SELECT
    col1,
    col2,
    col3
FROM table
WHERE id_col = ?;
```

**Use Case:** Fetch specific record by identifier.

---

## Parameter Binding

### Positional Parameters

Use `?` placeholders and pass tuple:

```python
# Query
SELECT * FROM lists WHERE list_id = ?;

# Execution
sql_manager.execute_parametrized_query(
    "GET_LIST_BY_ID",
    (131178,)  # Tuple with one element
)

# Multiple parameters
SELECT * FROM lists WHERE user_profile = ? AND scrape_status = ?;

# Execution
sql_manager.execute_parametrized_query(
    "QUERY_NAME",
    ("deirdre", "pending")
)
```

### SQL Injection Safety

**Safe:**
```python
sql_manager.execute_parametrized_query(
    "GET_LISTS_BY_STATUS",
    ("pending",)  # Safe parameter binding
)
```

**Unsafe:**
```python
# DON'T DO THIS - SQL injection risk
query = f"SELECT * FROM lists WHERE scrape_status = '{user_status}'"
sql_manager._execute_raw(query, ())
```

---

## Creating New Queries

### Step 1: Open Query File

Choose appropriate file (or create new):
- `lists.sql` - For list queries
- `titles.sql` - For title queries (to be created)
- `volumes.sql` - For volume queries (to be created)

### Step 2: Add Query

```sql
# YOUR_QUERY_NAME
SELECT * FROM table WHERE condition = ?;
```

### Step 3: Document

Add documentation:
- Purpose
- Parameters
- Returns
- Example usage

### Step 4: Test

Test query with SQLite CLI:

```bash
sqlite3 databases/publications.db <<EOF
-- Paste query here
SELECT * FROM lists WHERE list_id = ?;
EOF
```

Or use Python:

```python
sql_manager.execute_parametrized_query("YOUR_QUERY_NAME", (param,))
```

---

## Query Performance

### Indexes

Queries should leverage existing indexes for performance:

**lists table indexes:**
- `idx_lists_scrape_status` on `(scrape_status)`
- `idx_lists_user_profile` on `(user_profile)`

**titles table indexes:**
- `idx_titles_scrape_status` on `(scrape_status)`
- `idx_titles_title_id` on `(title_id)`

**volumes table indexes:**
- `idx_volumes_title` on `(title_id)`
- `idx_volumes_volume_id` on `(volume_id)`

### Query Optimization

**Use indexes in WHERE clauses:**
```sql
-- Good - uses index
SELECT * FROM lists WHERE scrape_status = 'pending';

-- Bad - full table scan
SELECT * FROM lists WHERE title LIKE '%Manga%';
```

**Order by indexed columns:**
```sql
-- Good - uses index
SELECT * FROM lists ORDER BY id;

-- Could be slow on large tables
SELECT * FROM lists ORDER BY title;
```

---

## Related Documentation

- [Database Schema](schema.md) - Table definitions
- [SQLManager Guide](sqlmanager-guide.md) - SQLManager usage
- [Migrations Guide](migrations-guide.md) - Working with migrations
