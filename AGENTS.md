# AI Agent Guidelines — Whakoom Scraper V2

## 1. Project Context

This is a **Python 3.13 web scraping project** that extracts manga collection data from
Whakoom user profiles through a plain-Python, sync-first httpx pipeline. It is a
hobby project with maintainability best practices: layering, determinism, and no slope.

The legacy `whakoom_webscrapper/` package (Scrapy + Selenium) is **frozen reference
material**: never wired in, never deleted — mine it for selectors/endpoint knowledge only.

**Core stack:**

* Python **3.13** (pinned in `.python-version`; `requires-python = ">=3.13"`, ADR-0011)
* httpx + tenacity (HTTP, retries), parsel (HTML parsing)
* SQLite (local persistence) behind a custom `store/` layer
* DuckDB (read-only analytics/export via the SQLite extension)
* Dataclasses for domain items
* SQL migrations for schema evolution (forward-only)
* `uv` for **all** dependency and command execution

Design authority is `V2.md`; implementation tracking is `phases.md`; architectural
decisions live in `docs/adr/` (accepted ADRs are never edited in place).

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
   * You are not allowed to modify .pre-commit-config.yaml to disable rules
   * Disabling rules requires **explicit user permission** and an inline comment

---

## 3. Command Execution (uv is mandatory)

**ALL commands must be executed via `uv run`.**

```bash
# Dependency sync
uv sync

# CLI stages
uv run wk lists [--reset]
uv run wk list-detail [--list-id N | --all]
uv run wk resolve [--limit N]
uv run wk series [--force] [--limit N]
uv run wk validate
uv run wk analyze [--force]
uv run wk run-all

# Quality gates (every phase)
uv run pytest
uv run ruff check .
uv run mypy .
uv run bandit -c pyproject.toml -r whakoom_scraper/
uv run pre-commit run --all-files
```

🚫 Never use `pip`, `scrapy`, `httpx`, `ruff`, `mypy`, `bandit`, `black`, or `pre-commit`
directly.

---

## 4. Python 3.13 Coding Standards

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

### Dataclasses & Domain Models

* All domain models **must** be dataclasses with `kw_only=True`
* All models live in `whakoom_scraper/domain.py`
* External identifiers carry a `whakoom_*` prefix; surrogate DB `id`s never cross namespaces

```python
@dataclass(kw_only=True)
class Series:
    whakoom_series_id: int
    slug: str
    url: str
    name: str | None = None
```

🚫 Plain dictionaries are not allowed as items or results.

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

* **ALWAYS** go through `whakoom_scraper.store.db.Database`
* **NEVER** open raw SQLite connections outside the store layer
* **NEVER** write inline SQL in application code
* Query parameters **must** use `?` placeholders

```python
db.execute("lists", "upsert_list", (list_.whakoom_list_id, list_.name))
db.fetchone("series", "get_series", (whakoom_series_id,))
```

🚫 String interpolation in SQL is forbidden.

---

### Named Queries

* All SQL lives in `whakoom_scraper/store/queries/*.sql`
* Queries are referenced by `-- name:` marker: `db.execute(<file_stem>, <query_name>, params)`
* Repository functions in `store/repositories.py` own all DB access for stages
* Repos **never commit** — the calling stage owns the transaction boundary

---

### Migrations

* Location: `whakoom_scraper/store/migrations/`
* Naming: `NNN_description.sql`
* Applied once, in filename order, tracked in the `_migrations` table
* **Forward-only** (no UP/DOWN sections; destructive changes dump → rebuild → reload)

---

## 6. Scraping Rules

### Deduplication (CRITICAL)

A manga title may appear in multiple lists.

**Requirements:**

* Titles must be scraped **once**
* Use stable identifiers (Whakoom series/list ids, volume slugs)
* Enforce uniqueness at the database level (`UNIQUE` + `ON CONFLICT`)

Failure to deduplicate is a **hard bug**.

---

### Stage Design

* **One stage = one responsibility**
* No mixed concerns

```text
lists        → list cards only
list-detail  → list items + per-list reconciliation
resolve      → volume slug → series (authenticated, name-aware)
series       → full series data + observation history
```

* `list-detail` **reconciles** per list (`replace_list_items`): latest fetched version
  wins, stale rows deleted, resolved `series_id` links preserved. On any delta: log a
  WARNING and record it in `scrape_runs.notes`, then proceed.

---

### Error Handling

* No silent failures
* Always log errors
* Retry transient failures (max 3 attempts, exponential backoff) — handled by `WhakoomSession`

---

### Logging

* Log to console **and** record stage outcomes in the `scrape_runs` table
* Session expiry aborts `resolve` with exit code `3` (loud, resumable)

---

## 7. Testing Expectations

* Unit tests for:

  * Domain models
  * Store layer (query loader, migrations, repositories)
  * Parsers (`scrapers/`) against snapshot fixtures
  * HTTP layer (retries, redirects, robots, archive) via `httpx.MockTransport`
* Integration tests for:

  * Stage → DB flow over `MockTransport` + a temp SQLite file

Database-impacting changes must be tested. All tests run **offline**.

---

## 8. Security Rules

* No secrets in code
* No credentials in repo (`cookies.txt`, `.env` are gitignored)
* Environment variables only (see `.env.example`)
* SQL injection prevention is mandatory (`?` placeholders only)

---

## 9. Git & Commits

### Git Rules

* Branches should be named `feature/description` or `fix/description`
* Always check in which branch you currently are before staging and/or committing changes. If you are not in the correct branch, create a new branch from the correct base.
* Never commit to `main` or `develop` directly
* Never use `Reset --Hard` unless explicitly ordered
* Never use force push unless explicitly ordered
* Never commit changes without asking the user first

### Commit Format

Use **Conventional Commits**:

```text
feat: add stage-1 lists pipeline
fix: reconcile list items instead of upserting
docs: update AGENTS.md to V2
```

### Push Checklist (only if ordered)

1. Run pre-commit
2. Review `git diff`
3. Update README if behavior or scope changed
4. Push

---

## 10. Code Search & Retrieval Routing

Route retrieval by cost; escalate only when the cheaper layer can't deliver.

* **Layer 1 — Text (default):** use the **Grep** and **Glob** tools. Drop to **Bash** `rg` only for per-file counts (`rg -c`), piping into `xargs`, or regex the Grep tool can't express.
* **Layer 2 — Structural / rewrite:** for AST-safe renames, matching code while ignoring strings/comments, or relational queries (`has`/`inside`/`not`) → load the **`code-search`** skill (`ast-grep`/`sg`). **Never** `rg` + `sed` for rewrites (corrupts strings/comments).
* **Layer 3 — Symbol:** for precise renames, go-to-definition, find-references, and type diagnostics on Python → rely on **pyright LSP** diagnostics (wired in `opencode.json`).

For the full layered funnel, decision tables, and ast-grep recipes, load the `code-search` skill.

---

## 11. Summary Checklist (Agent Self-Audit)

Before stopping work, ensure:

* [ ] Python 3.13 syntax only
* [ ] Full typing coverage
* [ ] Google-style docstrings
* [ ] `uv run` used everywhere
* [ ] `Database` + named queries only (no raw SQL, no inline SQL)
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

If hurry/panic mode is triggered, **stop immediately** and explain the situation to the user, requesting further instructions.

If uncertain, **stop and ask**.
