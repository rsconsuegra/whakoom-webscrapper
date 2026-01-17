# AI Agent Guidelines — Whakoom Scraper

## 1. Project Context

This is a **Python 3.12 web scraping project** built with **Scrapy** to extract manga collection data from Whakoom user profiles. This is inteded as a hobby yet mantainable project with best practices.

**Core stack:**

* Python **3.12**
* Scrapy **2.11+**
* SQLite (local persistence)
* Dataclasses for items
* SQL migrations for schema evolution
* `uv` for **all** dependency and command execution

This file defines **non-negotiable rules** for AI agents and contributors.

---

## 2. Critical Agent Rules (READ FIRST)

These rules override all others.

### 🚫 Git & File Safety

1. **NEVER commit or push unless explicitly ordered**
2. **NEVER delete files** without explicit permission

   * Exception: temporary files created during the agent session
3. **ALWAYS run pre-commit before any commit**

   ```bash
   uv run pre-commit run --all-files
   ```
4. **NEVER ignore linting errors**

   * All linting errors must be addressed
   * Disabling rules requires **explicit user permission** and an inline comment

---

## 3. Command Execution (uv is mandatory)

**ALL commands must be executed via `uv run`.**

```bash
# Dependency sync
uv sync

# Scrapy
uv run scrapy crawl lists
uv run scrapy crawl lists --loglevel=DEBUG

# Quality tools
uv run ruff check whakoom_webscrapper/
uv run black whakoom_webscrapper/
uv run bandit -r whakoom_webscrapper/
uv run pre-commit run --all-files
```

🚫 Never use `pip`, `scrapy`, `ruff`, `black`, or `bandit` directly.

---

## 4. Python 3.12 Coding Standards

### Typing (MANDATORY)

* All functions **must** be fully typed
* Use modern syntax only

```python
# Good
def process_item(item: dict[str, Any]) -> dict[str, Any]: ...

# Bad
def process_item(item): ...
```

#### Allowed typing features

* `|` union syntax
* PEP 695 type aliases
* Generics (`TypeVar`, `Generic`)
* `kw_only=True` dataclasses

---

### Dataclasses & Items

* All items **must** be dataclasses
* `kw_only=True` is required
* Items must support `__getitem__`

```python
@dataclass(kw_only=True)
class ListsItem:
    list_id: int
    title: str

    def __getitem__(self, attr: str):
        return getattr(self, attr)
```

🚫 Plain dictionaries are not allowed for items.

---

### Docstrings (MANDATORY)

* **Google docstring format**
* Required for **all public functions**

**Structure:**

1. Short summary (no period)
2. Blank line
3. Args
4. Returns / Yields
5. Raises (if applicable)
6. Optional extended explanation

Example:
```python
  def connect_to_next_port(self, minimum: int) -> int:
    """Connects to the next available port.

    Args:
      minimum: A port value greater or equal to 1024.

    Returns:
      The new minimum port.

    Raises:
      ConnectionError: If no available port is found.
    """
```

---

### Pattern Matching & Modern Syntax

* Use `match/case` for complex branching
* Prefer f-strings (including debug syntax)
* Prefer list comprehensions
* Use context managers for all resources

---

## 5. Database Rules (Strict)

### SQL Access

* **ALWAYS** use `SQLManager`
* **NEVER** use raw SQLite connections
* **NEVER** write inline SQL

```python
sql_manager.execute_parametrized_query("INSERT_OR_UPDATE_LISTS", params)
```

---

### Queries

* All SQL must live in `queries/`
* Queries are referenced **by name**
* Parameters **must** use `?` placeholders

🚫 String interpolation in SQL is forbidden.

---

### Migrations

* Location: `migrations/`
* Naming: `XXX_description.sql`
* Must be idempotent
* Must include **UP and DOWN** sections

---

## 6. Scraping Rules

### Deduplication (CRITICAL)

A manga title may appear in multiple lists.

**Requirements:**

* Titles must be scraped **once**
* Use stable identifiers (e.g. Whakoom title ID)
* Enforce uniqueness at the database level

Failure to deduplicate is a **hard bug**.

---

### Spider Design

* **One spider = one responsibility**
* No mixed concerns

```python
ListSpider   → lists only
TitleSpider  → titles only
VolumeSpider → volumes only
```

---

### Pipelines & Error Handling

* No silent failures
* Always log errors
* Retry transient failures (max 3 attempts, exponential backoff)

---

### Logging

* Log to console **and** `scraping_log` table
* Use descriptive `scrapper_name`

---

## 7. Testing Expectations

* Unit tests for:

  * Items
  * Pipelines
  * Deduplication logic
* Integration tests for:

  * Spider → DB flow

Database-impacting changes must be tested.

---

## 8. Security Rules

* No secrets in code
* No credentials in repo
* Environment variables only
* SQL injection prevention is mandatory

---

## 9. Git & Commits

### Commit Format

Use **Conventional Commits**:

```text
feat: add title spider
fix: prevent duplicate title inserts
docs: update AGENTS.md
```

### Push Checklist (only if ordered)

1. Run pre-commit
2. Review `git diff`
3. Update README if behavior or scope changed
4. Push

---

## 10. Summary Checklist (Agent Self-Audit)

Before stopping work, ensure:

* [ ] Python 3.12 syntax only
* [ ] Full typing coverage
* [ ] Google-style docstrings
* [ ] `uv run` used everywhere
* [ ] SQLManager + named queries only
* [ ] Deduplication enforced
* [ ] Errors logged
* [ ] Tests updated if DB logic changed
* [ ] No commits or deletions without permission

---

## Final Notes for AI Agents

This project prioritizes:

* **Correctness over speed**
* **Determinism over cleverness**
* **Explicit behavior over implicit assumptions**

If uncertain, **stop and ask**.
