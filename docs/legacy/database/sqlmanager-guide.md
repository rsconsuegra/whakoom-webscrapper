# SQLManager Guide

Comprehensive guide for using SQLManager - a lightweight ORM-like database manager.

---

## Overview

**SQLManager** provides type-safe database operations with named queries and ORM-like helper methods.

**Location:** `whakoom_webscrapper/sqlmanager.py`

**Design Philosophy:**
- Simpler than full ORMs (SQLAlchemy, Django ORM)
- Explicit SQL visibility
- Type-safe with Python 3.12 dataclasses
- Zero dependencies beyond Python stdlib
- Perfect fit for hobby/exploratory projects

---

## Initialization

### Basic Setup

```python
from whakoom_webscrapper.sqlmanager import SQLManager

sql_manager = SQLManager(
    db_path="databases/publications.db",
    sql_dir="whakoom_webscrapper/queries",
    migrations_dir="whakoom_webscrapper/migrations"
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| db_path | str | Yes | Path to SQLite database file |
| sql_dir | str | No | Path to directory containing `.sql` query files |
| migrations_dir | str | No | Path to directory containing migration files |

### Attributes

```python
sql_manager.db_path        # Database file path
sql_manager.sql_dir         # SQL queries directory
sql_manager.migrations_dir   # Migrations directory
sql_manager.queries         # Dict of loaded named queries
```

---

## Named Queries

### Loading Queries

SQLManager automatically loads all named queries from `.sql` files in `sql_dir`.

### Query File Format

```sql
# QUERY_NAME
SELECT * FROM table WHERE field = ?;

# ANOTHER_QUERY
INSERT INTO table (col1, col2) VALUES (?, ?);
```

**Rules:**
- Query name starts with `#` on its own line
- Query name is case-insensitive (converted to uppercase)
- Query continues until next `#` or end of file
- Use `?` placeholders for parameters (SQL injection safe)

### Example: lists.sql

```sql
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
SELECT id, list_id, title, url, user_profile, scrape_status, scraped_at
FROM lists
WHERE scrape_status = ?
ORDER BY id;

# UPDATE_LIST_STATUS
UPDATE lists
SET scrape_status = ?, scraped_at = CURRENT_TIMESTAMP
WHERE list_id = ?;
```

### Accessing Queries

```python
# Queries are loaded into dict with uppercase keys
query = sql_manager.queries['INSERT_OR_UPDATE_LIST']
```

---

## Execution Methods

### execute_query()

Execute a named query with optional parameter substitution.

**Signature:**
```python
def execute_query(self, query_name: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]
```

**Parameters:**
- `query_name` - Name of query (case-insensitive)
- `params` - Optional dict of parameters for string formatting

**Use Case:** Queries with named placeholders for string formatting.

**Example:**
```python
# Query with placeholder
query = """
SELECT * FROM lists
WHERE scrape_status = '{status}'
ORDER BY {sort_order}
"""

results = sql_manager.execute_query(
    "CUSTOM_QUERY",
    params={"status": "pending", "sort_order": "id"}
)
```

**Note:** This is less common. Use `execute_parametrized_query()` for most cases.

---

### execute_parametrized_query()

Execute a named query with positional parameters.

**Signature:**
```python
def execute_parametrized_query(self, query_name: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]
```

**Parameters:**
- `query_name` - Name of query (case-insensitive)
- `params` - Tuple of parameters matching `?` placeholders

**Returns:** List of tuples with query results.

**Use Case:** Most common query execution with safe parameter binding.

**Example:**
```python
# Get all pending lists
results = sql_manager.execute_parametrized_query(
    "GET_LISTS_BY_STATUS",
    ("pending",)
)

for row in results:
    list_id, title, url = row[1], row[2], row[3]
    print(f"{list_id}: {title}")
```

**With Multiple Parameters:**
```python
# Insert a list
sql_manager.execute_parametrized_query(
    "INSERT_OR_UPDATE_LIST",
    (131178, "Licencias Manga en Español 2025",
     "https://www.whakoom.com/deirdre/lists/...", "deirdre",
     "pending", None)
)
```

---

## ORM-Like Methods

### insert()

Insert a dataclass model instance into database.

**Signature:**
```python
def insert(self, model_class: type[Any], instance: Any) -> None
```

**Parameters:**
- `model_class` - Dataclass type (e.g., `ListsItem`)
- `instance` - Instance of model_class to insert

**Raises:**
- `ValueError` - If instance type doesn't match model_class
- `ValueError` - If model_class has no `table_name` attribute
- `ValueError` - If instance has no `to_tuple()` method
- `sqlite3.Error` - If query fails

**Requirements:**
1. Model class must have `table_name` attribute
2. Model class must be a dataclass with `@dataclass(kw_only=True)`
3. Instance must have `to_tuple()` method

**Example:**
```python
from whakoom_webscrapper.models import ListsItem

# Create instance
list_item = ListsItem(
    list_id=131178,
    title="Licencias Manga en Español 2025",
    url="https://www.whakoom.com/deirdre/lists/...",
    user_profile="deirdre",
    scrape_status="pending",
    scraped_at=None
)

# Insert into database
sql_manager.insert(ListsItem, list_item)
```

**Generated SQL:**
```sql
INSERT INTO lists (list_id, title, url, user_profile, scrape_status, scraped_at)
VALUES (?, ?, ?, ?, ?, ?)
```

**Parameters:**
```python
(131178, "Licencias Manga en Español 2025",
 "https://www.whakoom.com/deirdre/lists/...", "deirdre",
 "pending", None)
```

---

### update()

Update all fields of a model instance by ID field.

**Signature:**
```python
def update(self, model_class: type[Any], instance: Any, id_field: str, id_value: int | str) -> None
```

**Parameters:**
- `model_class` - Dataclass type
- `instance` - Instance with updated values
- `id_field` - Field name to use in WHERE condition
- `id_value` - Value of ID field to match

**Raises:** Same as `insert()`

**Example:**
```python
from whakoom_webscrapper.models import ListsItem

# Create updated instance
updated_list = ListsItem(
    list_id=131178,
    title="Updated Title",
    url="https://www.whakoom.com/deirdre/lists/...",
    user_profile="deirdre",
    scrape_status="completed",
    scraped_at="2026-02-01 18:00:00"
)

# Update in database
sql_manager.update(ListsItem, updated_list, "list_id", 131178)
```

**Generated SQL:**
```sql
UPDATE lists
SET title = ?, url = ?, user_profile = ?, scrape_status = ?, scraped_at = ?, updated_at = ?
WHERE list_id = ?
```

**Note:** Updates all fields except `table_name` and `id_field`.

---

### update_single_field()

Update a single field without affecting other data.

**Signature:**
```python
def update_single_field(self, table: str, id_field: str, id_value: int | str, field_name: str, field_value: Any) -> None
```

**Parameters:**
- `table` - Table name (string)
- `id_field` - Field name for WHERE condition
- `id_value` - Value of ID field to match
- `field_name` - Field to update
- `field_value` - New value for field

**Use Case:** Status updates (e.g., marking lists as completed).

**Example:**
```python
# Mark list as completed
sql_manager.update_single_field(
    "lists", "list_id", 131178, "scrape_status", "completed"
)

# Update timestamp
from datetime import datetime
sql_manager.update_single_field(
    "lists", "list_id", 131178, "scraped_at", datetime.now().isoformat()
)
```

**Generated SQL:**
```sql
UPDATE lists SET scrape_status = ? WHERE list_id = ?
```

---

### insert_relationship()

Insert into junction tables (many-to-many relationships).

**Signature:**
```python
def insert_relationship(self, table: str, **kwargs: Any) -> None
```

**Parameters:**
- `table` - Junction table name (string)
- `**kwargs` - Column name/value pairs

**Use Case:** Inserting into `lists_titles` table.

**Example:**
```python
# Link list to title
sql_manager.insert_relationship(
    "lists_titles",
    list_id=123,
    title_id=673392,
    position=1
)
```

**Generated SQL:**
```sql
INSERT INTO lists_titles (list_id, title_id, position)
VALUES (?, ?, ?)
```

---

### select_by_id()

Select a record from table by ID field.

**Signature:**
```python
def select_by_id(self, table: str, id_field: str, id_value: int | str) -> list[dict[str, Any]]
```

**Parameters:**
- `table` - Table name (string)
- `id_field` - Field name for WHERE condition
- `id_value` - Value of ID field to match

**Returns:** List of dictionaries with column names as keys.

**Example:**
```python
# Get list by list_id
results = sql_manager.select_by_id("lists", "list_id", 131178)
if results:
    list_data = results[0]
    print(f"List: {list_data['title']}, Status: {list_data['scrape_status']}")

# Get title by title_id
results = sql_manager.select_by_id("titles", "title_id", 673392)
if results:
    title_data = results[0]
    print(f"Title: {title_data['title']}")
```

---

## Migration Methods

### apply_migrations()

Apply all pending migrations in order.

**Signature:**
```python
def apply_migrations(self) -> None
```

**Behavior:**
1. Creates `migrations` table if not exists
2. Scans migrations directory for `.sql` files
3. Parses filenames to extract version and name
4. Checks which migrations are already applied
5. Applies pending migrations in version order
6. Tracks applied migrations in `migrations` table

**Example:**
```python
# Automatically called by pipeline on spider start
sql_manager.apply_migrations()
```

**Manual Application:**
```python
# Apply migrations manually
sql_manager.apply_migrations()
```

### get_pending_migrations()

Get all migrations not yet applied.

**Signature:**
```python
def get_pending_migrations(self) -> list[dict[str, str]]
```

**Returns:** List of dictionaries with `version`, `name`, `file_path`.

**Example:**
```python
pending = sql_manager.get_pending_migrations()
for migration in pending:
    print(f"Pending: {migration['version']} - {migration['name']}")
```

**Output:**
```
Pending: 002 - add_language_to_titles
Pending: 003 - create_indexes
```

---

## Logging Methods

### log_scraping_operation()

Log a scraping operation to `scraping_log` table.

**Signature:**
```python
def log_scraping_operation(self, scrapper_name: str, operation_type: str, entity_id: int, status: str, error_message: str | None = None, duration_ms: int | None = None) -> None
```

**Parameters:**
- `scrapper_name` - Name of spider (e.g., 'lists', 'publications')
- `operation_type` - Type of operation (e.g., 'list_processing', 'title_processing')
- `entity_id` - ID of entity being processed
- `status` - Status: `'started'`, `'success'`, `'failed'`
- `error_message` - Error message if failed
- `duration_ms` - Duration in milliseconds

**Example:**
```python
# Log operation start
sql_manager.log_scraping_operation(
    scrapper_name="lists",
    operation_type="list_processing",
    entity_id=131178,
    status="started"
)

# Log success
sql_manager.log_scraping_operation(
    scrapper_name="lists",
    operation_type="list_processing",
    entity_id=131178,
    status="success"
)

# Log failure
sql_manager.log_scraping_operation(
    scrapper_name="lists",
    operation_type="list_processing",
    entity_id=131178,
    status="failed",
    error_message="TimeoutException: Element not found"
)
```

---

## Pipeline Integration

### Using SQLManager in Pipeline

```python
from whakoom_webscrapper.sqlmanager import SQLManager
from whakoom_webscrapper.models import ListsItem

class WhakoomWebscrapperPipeline:
    def __init__(self) -> None:
        self.sql_manager = SQLManager(
            db_path="databases/publications.db",
            sql_dir="whakoom_webscrapper/queries",
            migrations_dir="whakoom_webscrapper/migrations"
        )

    def open_spider(self, spider: Spider) -> None:
        self.sql_manager.apply_migrations()

    def process_item(self, item: ListsItem, spider: Spider) -> None:
        if isinstance(item, ListsItem):
            self.sql_manager.log_scraping_operation(
                scrapper_name=spider.name,
                operation_type="list_processing",
                entity_id=item.list_id,
                status="started"
            )

            self.sql_manager.insert(ListsItem, item)

            self.sql_manager.log_scraping_operation(
                scrapper_name=spider.name,
                operation_type="list_processing",
                entity_id=item.list_id,
                status="success"
            )
```

---

## Common Patterns

### Pattern 1: Insert with Model

```python
# Create model instance
item = ListsItem(list_id=123, title="My List", url="...", user_profile="user")

# Insert
sql_manager.insert(ListsItem, item)
```

### Pattern 2: Query and Process Results

```python
# Query
results = sql_manager.execute_parametrized_query("GET_LISTS_BY_STATUS", ("pending",))

# Process results
for row in results:
    id, list_id, title, url, user_profile, scrape_status, scraped_at = row
    print(f"{list_id}: {title}")
```

### Pattern 3: Update Status

```python
# Update to in_progress
sql_manager.update_single_field("lists", "list_id", 123, "scrape_status", "in_progress")

# Do work...

# Update to completed
sql_manager.update_single_field("lists", "list_id", 123, "scrape_status", "completed")
```

### Pattern 4: Check for Existence

```python
# Try to select by ID
results = sql_manager.select_by_id("lists", "list_id", 123)

if results:
    # Exists
    list_data = results[0]
    print(f"Found: {list_data['title']}")
else:
    # Not exists
    print("Not found")
```

### Pattern 5: Count Records

```python
# Use execute_query with COUNT
results = sql_manager.execute_query(
    "COUNT_QUERY",
    params={"table": "lists", "status": "pending"}
)

count = results[0][0] if results else 0
print(f"Pending lists: {count}")
```

---

## Benefits of SQLManager

### vs Full ORMs (SQLAlchemy, Django ORM)

**SQLManager Advantages:**
- Simpler - No session management, declarative bases
- Explicit - Full SQL visibility, no query hiding
- Lightweight - No extra dependencies
- Type-safe - Python 3.12 dataclasses
- Perfect scale - Fits hobby/exploratory projects

**Full ORM Advantages:**
- Relationship loading (lazy, eager)
- Query builder API
- Migration tools (Alembic)
- Larger ecosystem

**Decision:** SQLManager is better for this project because:
- Simple CRUD operations
- Explicit SQL preferred
- No complex relationships
- Learning curve is gentler

### vs Raw SQLite

**SQLManager Advantages:**
- Named queries - Reusable, version-controlled
- ORM-like helpers - Type-safe, less boilerplate
- Migration support - Automatic schema evolution
- Logging - Built-in operation logging

**Raw SQLite Advantages:**
- Maximum control
- No abstraction overhead

**Decision:** SQLManager provides right balance:
- Named queries for reusability
- ORM helpers for common operations
- Raw access still available if needed

---

## Troubleshooting

### Issue: Query Not Found

**Error:** `ValueError: Query 'GET_LISTS' not found.`

**Cause:** Query name doesn't match any in query files.

**Solution:**
1. Check query file exists: `whakoom_webscrapper/queries/lists.sql`
2. Verify query name format: `# GET_LISTS`
3. Check for typos (case-insensitive but must exist)

### Issue: Type Mismatch

**Error:** `ValueError: Instance must be of type ListsItem`

**Cause:** Passing wrong instance type to `insert()`.

**Solution:**
```python
# Correct
sql_manager.insert(ListsItem, list_item)

# Wrong
sql_manager.insert(VolumesItem, list_item)  # Wrong type
```

### Issue: Missing table_name

**Error:** `ValueError: Model ListsItem has no 'table_name' attribute`

**Cause:** Model class doesn't have `table_name` attribute.

**Solution:**
```python
@dataclass(kw_only=True)
class ListsItem:
    list_id: int
    title: str
    # ... fields

    table_name: str = "lists"  # Required!
```

### Issue: Missing to_tuple()

**Error:** `ValueError: Instance of ListsItem has no 'to_tuple()' method`

**Cause:** Model instance doesn't have `to_tuple()` method.

**Solution:**
```python
@dataclass(kw_only=True)
class ListsItem:
    list_id: int
    title: str
    # ... fields

    def to_tuple(self) -> tuple:
        return (self.list_id, self.title, ...)  # Required!
```

### Issue: Database Locked

**Error:** `OperationalError: database is locked`

**Cause:** Concurrent access or unclosed connection.

**Solution:**
1. Ensure no other process accesses database
2. Close any SQLite clients
3. Wait a few seconds and retry
4. Use transactions properly

---

## Related Documentation

- [Database Schema](schema.md) - Complete database reference
- [Migrations Guide](migrations-guide.md) - Migration system
- [Queries Reference](queries-reference.md) - Named queries reference
- [Architecture](../architecture.md) - System architecture overview
