# Phase 0-2 Stabilization Plan

## 1. Purpose

This plan addresses the issues found during the architectural and implementation review of Whakoom Scraper V2 through Phase 2 of `phases.md`.

The objective is to make the existing design guarantees true before adding parsers and live pipeline stages. The project does not need another framework or architectural rewrite. It needs targeted corrections to migration safety, transaction ownership, request archiving, domain boundaries, resolver behavior, configuration, and documentation.

This plan deliberately avoids:

- An ORM.
- Generic repository base classes.
- Dependency injection containers.
- Async HTTP.
- Browser automation.
- A workflow engine.
- Event buses or middleware systems.
- External enrichment before the core pipeline is validated.
- Additional linting or formatting tools.

## 2. Authority and Scope

Use the project documents as follows:

- `V2.md` defines the target architecture and behavior.
- `phases.md` is the authoritative implementation sequence and phase-status document.
- Accepted ADRs record architectural decisions and are never edited in place.
- Contradictory accepted ADRs must be superseded by new ADRs.

Under `phases.md`, the completed work currently covers:

- Phase 0: scaffolding and environment.
- Phase 1: SQLite store, migrations, named queries, and repositories.
- Phase 2: HTTP session, robots policy, and raw archive.

The parser and pipeline implementations remain future work even where partial resolver code already exists.

## 3. Priority Summary

| Priority | Issue | Required before |
|---|---|---|
| P0 | Migration atomicity | Any new migration |
| P0 | Database transaction and rollback API | Phase 4 pipeline |
| P0 | Request-aware raw archive | Phase 3 fixtures and Phase 4 |
| P0 | Resolver request-contract contradiction | Resolver implementation |
| P1 | Surrogate IDs in parser-facing models | Phase 3 parsers |
| P1 | Missing schema enforcement | Real data ingestion |
| P1 | Configuration validation | Live requests |
| P1 | Session-expiry detection | Authenticated resolution |
| P1 | List invalidation and refresh policy | Public list stages |
| P1 | Resolver I/O inside parser package | Phase 5 |
| P2 | Repository invariant handling | Phase 4-6 |
| P2 | Publisher and author identity behavior | Phase 6 |
| P2 | Failed-item selection | Phase 4-6 |
| P2 | Series-child reconciliation | Phase 6 |
| P3 | ADR, tooling, and documentation alignment | Release checkpoint |

---

## 4. Track A: Store Safety

### A1. Make Migrations Atomic

#### Reason

The design promises that each migration and its `_migrations` record are applied as one transaction. The current implementation does not guarantee that.

`sqlite3.Connection.executescript()` may commit an existing transaction before executing a script. If a migration fails halfway through, earlier statements may remain applied while the migration filename is absent from `_migrations`. The next startup then retries against a partially changed schema.

This is not optional technical debt. It invalidates a Phase 1 acceptance guarantee and must be corrected before the first additional migration.

#### Sources

- `whakoom_scraper/store/db.py:163-183`
- `V2.md:145-147`
- `V2.md:379-383`
- `phases.md:140-142`
- `TECH_DEBT.md:27-39`

#### Implementation

1. Keep `_migrations` bootstrapping outside individual migration files.
2. Start each pending migration with an explicit `BEGIN IMMEDIATE` included in the script passed to `executescript()`.
3. Execute the migration body without committing it.
4. Insert the migration filename with a parameterized statement.
5. Commit only after the migration marker is inserted.
6. Roll back on every exception.
7. Reject transaction-control statements inside migration files so a migration cannot commit itself.
8. Validate migration filenames against `NNN_description.sql`.
9. Reject duplicate numeric prefixes.

Expected control flow:

```python
try:
    connection.executescript(f"BEGIN IMMEDIATE;\n{migration_sql}")
    connection.execute(
        "INSERT INTO _migrations (filename) VALUES (?)",
        (filename,),
    )
    connection.commit()
except Exception:
    connection.rollback()
    raise
```

The migration text is trusted repository content. Runtime values such as the filename must remain parameterized.

#### Tests

Add tests to `whakoom_scraper/tests/test_store_db.py` covering:

- A successful migration changes the schema and records its filename.
- Reopening the database skips an applied migration.
- A two-statement migration whose second statement fails rolls back the first statement.
- A failed migration is not recorded.
- A corrected migration can run after the failure.
- Duplicate migration prefixes fail at startup.
- Invalid migration filenames fail at startup.
- Migration files containing `BEGIN`, `COMMIT`, or `ROLLBACK` are rejected.

#### Acceptance

- No object created by a failed migration remains.
- No failed migration is recorded.
- Existing successful migration tests remain green.
- `TECH_DEBT.md` R2 is closed.

### A2. Add a Minimal Transaction Context

#### Reason

Repositories correctly leave transaction ownership to stages, but `Database` exposes only `commit()` and `close()`. There is no safe rollback or transaction boundary.

This is already relevant to `replace_list_items()`, which deletes existing rows before inserting replacements. It becomes critical for the future series transaction covering publisher, series, volumes, authors, observation, and final status.

#### Sources

- `whakoom_scraper/store/db.py:155-161`
- `whakoom_scraper/store/repositories.py:172-218`
- `V2.md:475-476`
- `phases.md:339-342`

#### Implementation

Add a transaction context manager to `Database`:

```python
@contextmanager
def transaction(self) -> Iterator[None]:
    try:
        self._conn.execute("BEGIN IMMEDIATE")
        yield
    except Exception:
        self._conn.rollback()
        raise
    else:
        self._conn.commit()
```

Also add:

```python
def rollback(self) -> None:
    self._conn.rollback()
```

Make `Database` itself a context manager so every stage can write:

```python
with Database(settings.db_path) as db:
    with db.transaction():
        ...
```

Initially reject nested transactions rather than introducing savepoints without a concrete need.

Do not add a unit-of-work class or an ORM-style session.

#### Tests

- A successful transaction commits every statement.
- An exception rolls back every statement.
- Failed list reconciliation preserves the original rows.
- A stage can begin a new transaction after rolling back a failed one.
- Leaving the database context closes the connection.
- A nested transaction attempt fails clearly.

#### Acceptance

Every future multi-statement workflow uses `db.transaction()` and contains no manual commit sequence.

### A3. Close Connections on Initialization Failure

#### Reason

`Database.__init__()` opens a connection before loading queries and applying migrations. If either operation raises, the instance is never returned and the connection may remain open.

#### Source

- `whakoom_scraper/store/db.py:70-76`

#### Implementation

Wrap initialization after `sqlite3.connect()` in `try/except`. Close the connection before re-raising any query-loader or migration error.

Assign fully initialized attributes only after the setup steps succeed where practical.

#### Tests

- A malformed query file does not leave the database locked.
- A failed migration does not leave the database locked.
- The same database can be reopened immediately after either failure.

### A4. Reject Invalid Named-Query Files Early

#### Reason

A nonempty SQL file without any `-- name:` markers currently loads silently. The failure appears later as a missing-query `KeyError` rather than at startup.

#### Source

- `whakoom_scraper/store/db.py:23-50`

#### Implementation

Reject a nonempty, non-comment-only `.sql` file containing no named-query markers. Keep the rest of the loader unchanged.

#### Tests

- SQL content without a marker fails with the filename in the error.
- Duplicate query names continue to fail.
- Empty named-query bodies continue to fail.
- Define and test whether a completely empty query file is allowed or rejected.

---

## 5. Track B: Raw Response Archive

### B1. Archive by Request Identity

#### Reason

Archive filenames currently depend only on URL. This loses data for every endpoint where POST bodies distinguish requests.

All pagination calls use `/lists/listdetail.aspx/SeriesPage`, and all QuickView calls use `/pwkws.asmx/QuickView`. Different pages, lists, and slugs therefore overwrite one another.

The current behavior defeats fixture harvesting, parser replay, request-count validation, and failure forensics.

#### Sources

- `whakoom_scraper/http/archive.py:20-51`
- `phases.md:180-181`
- `V2.md:511-519`

#### Implementation

Change the helper to accept request identity:

```python
def save_raw(
    raw_dir: Path,
    stage: str,
    *,
    method: str,
    url: str,
    request_body: bytes | None,
    response_content: bytes,
    run_key: str | None = None,
    content_suffix: str = "html",
) -> Path:
    ...
```

Derive the digest from:

```text
METHOD + NUL + normalized URL + NUL + exact request body
```

This provides the desired semantics:

- Different pagination bodies produce different files.
- Different QuickView slugs produce different files.
- Retrying the exact same request overwrites the same artifact.
- GET requests remain deterministic.

Use a layout such as:

```text
data/raw/YYYY-MM-DD/<run-key>/<stage>/<request-key>.html.gz
```

The run key should be supplied by the stage so the archive remains independent from SQLite.

Use a readable prefix and a 16-character digest, for example:

```text
seriespage_post_4b54d6d8fd9d7e31.json.gz
quickview_post_fa90e8e705f729de.json.gz
ediciones_673392_rosen_blood_get_c6fa9140207c529f.html.gz
```

#### Tests

- Same URL with different POST bodies creates different files.
- Same method, URL, and body produces the same key.
- GET and POST for the same URL produce different files.
- Different run keys do not overwrite each other.
- Three pagination pages remain separately readable.
- Two QuickView slugs remain separately readable.

#### Acceptance

A mocked three-page list creates three pagination artifacts, and two mocked QuickView requests create two distinct artifacts.

### B2. Make Archive Writes Atomic

#### Reason

Writing directly to the canonical gzip path can destroy a previous valid artifact if the process stops during the replacement write.

#### Source

- `whakoom_scraper/http/archive.py:32-35`

#### Implementation

1. Create a temporary sibling file.
2. Write and close the gzip stream.
3. Replace the canonical path atomically with `Path.replace()`.
4. Remove the temporary file on failure.

Do not add an archive database, content manifest, or provenance framework at this stage.

#### Tests

- Successful output is a readable gzip file.
- A simulated failure leaves an existing artifact unchanged.
- No temporary files remain after failure.

### B3. Keep Archiving at the Stage Boundary

#### Reason

Embedding archive behavior in `WhakoomSession` would couple HTTP transport to pipeline stages and filesystem policy.

#### Implementation

Each stage should:

1. Build its request data.
2. Execute through `WhakoomSession`.
3. Pass request method, URL, exact body, response body, stage, and run key to `save_raw()`.
4. Parse the archived response body.

Do not add callback systems, middleware, or event buses unless repeated stage code later proves materially problematic.

---

## 6. Track C: Domain and Repository Boundaries

### C1. Remove Surrogate IDs from Parser-Facing Models

#### Reason

Pure parsers cannot know SQLite surrogate IDs. Their presence places persistence state in source records and contradicts the domain module's identifier discipline.

#### Sources

- `whakoom_scraper/domain.py:3-5`
- `whakoom_scraper/domain.py:26-37`
- `whakoom_scraper/domain.py:59-68`
- `whakoom_scraper/domain.py:95-106`

#### Implementation

Make `ListItem` source-only:

```python
@dataclass(kw_only=True)
class ListItem:
    position: int
    volume_slug: str
    volume_url: str
    whakoom_publication_id: int | None = None
    volume_number: int | None = None
    publisher: str | None = None
```

Remove `list_id` and `series_id`.

Remove `series_id` from `Volume`.

Remove `scrape_status` from `Series`; that value is workflow state, not scraped series data.

Make `Observation` contain metrics only. Pass the run and series identities separately to repositories.

Change repository APIs to accept external IDs:

```python
replace_list_items(db, whakoom_list_id, items)
upsert_volumes(db, whakoom_series_id, volumes)
insert_observation(db, whakoom_series_id, run_id, observation)
set_item_series(db, volume_slug, whakoom_series_id)
```

Repositories resolve surrogate IDs internally.

This avoids creating separate parsed, stored, DTO, entity, and record class hierarchies.

#### Tests

- Parsers construct models without database data.
- The same parsed object can be persisted into different temporary databases.
- Repository callers never need a list or series surrogate ID.
- Repositories correctly resolve foreign keys from Whakoom IDs.

### C2. Replace Sentinel ID Zero with Explicit Failure

#### Reason

Several upsert functions return `0` if their follow-up lookup unexpectedly fails. This hides the original invariant violation and produces a later foreign-key error.

#### Sources

- `whakoom_scraper/store/repositories.py:105-106`
- `whakoom_scraper/store/repositories.py:273-274`
- `whakoom_scraper/store/repositories.py:307-314`
- `whakoom_scraper/store/repositories.py:362-363`
- `whakoom_scraper/store/repositories.py:424-425`

#### Implementation

Add one internal helper:

```python
def _required_row_id(row: sqlite3.Row | None, entity: str) -> int:
    if row is None:
        raise RuntimeError(f"{entity} missing after successful upsert")
    return int(row["id"])
```

Use it consistently after upserts.

Do not add a custom exception hierarchy unless a future stage has a concrete need to classify this error separately.

### C3. Make Read Contracts Honest

#### Reason

`get_series()` returns a `Series` object that appears complete but omits persisted publisher, authors, and volumes. Empty collections can be mistaken for absent source data rather than unloaded relationships.

#### Sources

- `whakoom_scraper/store/repositories.py:59-79`
- `whakoom_scraper/store/repositories.py:366-389`

#### Implementation

Use narrow repository operations such as:

```python
get_series_current(...)
get_pending_series_refs(...)
```

`get_pending_series_refs()` should return only the identity required to fetch a public series page:

- `whakoom_series_id`
- slug
- URL
- optional name

Do not implement a generic aggregate loader. Full analytical reads belong in explicit SQL views later.

---

## 7. Track D: Schema Enforcement

### D1. Add Missing Integrity Guards

#### Reason

The implemented schema omits several invariants that V2 describes as database-enforced.

#### Sources

- `whakoom_scraper/store/migrations/001_initial_schema.sql:27-43`
- `whakoom_scraper/store/migrations/001_initial_schema.sql:63-114`
- `V2.md:266-377`

Missing enforcement includes:

- `lists.list_type` limited to `year`, `magazine`, or `other`.
- Nonnegative `rating_count`.
- Nonnegative `ownership_count`.
- Nonnegative `volumes_count`.
- Equivalent observation constraints.
- `idx_observations_series`.
- `idx_volumes_series`.

#### Implementation

Do not edit an applied migration. After migration atomicity is fixed, create:

```text
002_add_integrity_guards.sql
```

SQLite cannot add column-level `CHECK` constraints directly. To avoid a disproportionate parent/child table rebuild, use validation triggers for existing columns and normal indexes for lookup performance.

Create insert and update triggers for:

- Valid list type.
- Nonnegative current series counts.
- Nonnegative observation counts.

Add:

```sql
CREATE INDEX idx_observations_series ON series_observations (series_id);
CREATE INDEX idx_volumes_series ON volumes (series_id);
```

If the owner explicitly confirms that no V2 database has ever been used outside temporary tests, resetting the baseline migration could be considered separately. The default implementation must follow the forward-only migration policy.

#### Tests

Attempt direct SQL inserts and updates with:

- Invalid `list_type`.
- Negative rating count.
- Negative ownership count.
- Negative volume count.
- Rating below zero.
- Rating above five.
- Null optional values.
- Valid zero and boundary values.

Run `PRAGMA foreign_key_check` afterward.

### D2. Document and Test Nullable Rating Checks

#### Reason

SQLite correctly permits null through `CHECK (rating BETWEEN 0 AND 5)`, but this is not immediately obvious.

#### Implementation

No schema change is required. Add tests proving:

- `NULL` accepted.
- `0` accepted.
- `5` accepted.
- Negative rejected.
- Greater than five rejected.

---

## 8. Track E: List Lifecycle and Reconciliation

### E1. Define Full-Run and Incremental Behavior

#### Reason

The list upsert never invalidates completed list contents. Card metadata also cannot detect same-count replacements or reorders.

#### Sources

- `whakoom_scraper/store/queries/lists.sql:4-16`
- `whakoom_scraper/store/queries/lists.sql:56-74`
- `V2.md:433-438`

#### Recommended Policy

Use two explicit modes:

```text
wk list-detail
```

Processes pending lists for interrupted-run recovery.

```text
wk list-detail --all
```

Reconciles every selected list.

`wk run-all` should perform full list reconciliation. Approximately 66 lists and roughly 150 public requests do not justify complex change detection.

The list-index upsert should still mark a completed list pending when these fields change:

- URL.
- Name.
- Advertised comic count.

Likes and description changes should update metadata without forcing membership retrieval.

Use SQLite's null-safe `IS NOT` comparison when deciding whether relevant fields changed.

#### Tests

- Unchanged list remains completed.
- Changed comic count becomes pending.
- Changed name becomes pending.
- Changed URL becomes pending.
- Likes-only change remains completed.
- Description-only change remains completed.
- `--all` includes completed lists.
- A same-count reorder is corrected by full reconciliation.

### E2. Correct Reconciliation Result Semantics

#### Reason

`ReconcileResult.inserted` currently means rows physically rewritten, not newly introduced source items. An unchanged list reports every row as inserted.

#### Sources

- `whakoom_scraper/store/repositories.py:190-218`
- `whakoom_scraper/domain.py:125-138`
- `docs/adr/0009-per-list-reconciliation.md`

#### Implementation

Rename:

```text
inserted -> written
```

Add only the delta information stages need:

```text
added_slugs
removed_slugs
changed
```

Define `changed` from:

- Added or removed slug.
- Count change.
- Position change.
- Relevant item metadata change.

Do not build a generic diff engine.

#### Tests

- Identical refresh reports `changed=False`.
- Reorder reports `changed=True`.
- Addition reports one added slug.
- Removal reports one removed slug.
- Metadata-only change reports `changed=True`.

### E3. Reuse Resolution Across Lists

#### Reason

A slug resolved in one list is inserted unresolved when it first appears in another list. This creates avoidable gated requests.

#### Sources

- `whakoom_scraper/store/repositories.py:190-209`
- `whakoom_scraper/store/queries/list_items.sql`

#### Implementation

Before inserting an unresolved list item, search globally for an existing non-null `series_id` associated with the same `volume_slug`.

Apply mapping precedence:

```text
explicit item mapping
same-list previous mapping
global existing mapping
NULL
```

Do not add a dedicated resolution table yet. If every occurrence disappears and the slug returns later, one repeated resolution request is acceptable at current scale.

### E4. Stop Retrying Failed Entities Forever

#### Reason

Queries using `scrape_status != 'completed'` include permanently failed rows. Those rows would be retried on every run without a budget.

#### Sources

- `whakoom_scraper/store/queries/lists.sql:56-74`
- `whakoom_scraper/store/queries/series.sql`
- `TECH_DEBT.md:13-23`

#### Implementation

Default work selection should use:

```sql
WHERE scrape_status = 'pending'
```

Expose failed-item recovery explicitly through `--force` or `--retry-failed`.

Do not add attempt counters until repeated permanent failures demonstrate a need.

---

## 9. Track F: Resolver Contract

### F1. Supersede the One-Request ADR

#### Reason

ADR-0002 says the resolver makes exactly one request per unique slug, but the implementation performs a QuickView request followed by an optional comics-page fallback.

#### Sources

- `docs/adr/0002-cookie-backed-series-resolution.md:21-32`
- `docs/adr/0008-name-aware-resolution-nullable-series-name.md:19-29`
- `whakoom_scraper/scrapers/resolve.py:98-143`
- `phases.md:322-328`

#### Recommended Decision

Create a new ADR superseding ADR-0002 with this contract:

```text
One resolver invocation per unresolved unique volume slug.
QuickView is the primary request.
A comics-page fallback is permitted only when QuickView does not provide a series reference.
Resolution therefore uses one request normally and at most two requests per slug.
```

Update acceptance measurements to report:

- Unique slugs attempted.
- QuickView successes.
- Fallback attempts.
- Fallback successes.
- Total gated requests.
- Maximum requests for any slug.

Do not claim exactly one physical request while retaining a fallback.

### F2. Separate Resolver I/O from Parsing

#### Reason

The `scrapers` package is defined as pure, but `resolve_series_id()` performs network I/O and session handling.

#### Sources

- `whakoom_scraper/scrapers/resolve.py:98-143`
- `V2.md:164-168`
- `phases.md:231-250`

#### Implementation

Keep pure functions in `scrapers/resolve.py`:

```python
parse_quickview(body: str) -> SeriesRef | None
parse_resolution_location(location: str) -> SeriesRef | None
parse_volume_parent(body: str) -> SeriesRef | None
```

Place orchestration in `pipeline/stage_resolve.py`:

```text
QuickView request
archive response
check session expiry
parse response
optional fallback request
archive response
check session expiry
parse response
persist result
```

The pure parser module should not import `httpx` or `WhakoomSession`.

### F3. Make Session Expiry Unambiguous

#### Reason

Current expiry detection only catches an unfollowed redirect with `/login` in `Location`. It misses direct HTTP 401 responses, followed redirects, and final login pages.

#### Sources

- `whakoom_scraper/scrapers/resolve.py:84-95`
- `whakoom_scraper/scrapers/resolve.py:117-142`
- `docs/adr/0002-cookie-backed-series-resolution.md`

#### Implementation

Use `follow_redirects=False` for every gated request.

Classify session expiry when:

- Status is `401`.
- Status is a redirect and `Location` targets `/login`.
- Final URL targets `/login` in defensive handling.
- Redirect history contains a login target.

Raise `SessionExpiredError` immediately. Do not attempt fallback after an expiry response.

Include request URL, status, and login target in the exception. Never include cookie values.

#### Tests

- QuickView direct 401 aborts.
- QuickView login redirect aborts without fallback.
- Fallback login redirect aborts.
- A final 200 login page is recognized defensively.
- A normal unresolved 404 remains unresolved rather than expired.
- Session expiry maps to CLI exit code `3`.

### F4. Correct Name Extraction

#### Reason

QuickView titles may be nested inside an anchor. The current direct-text selector misses nested text. The fallback 200-body path also extracts identity without the associated title.

#### Sources

- `whakoom_scraper/scrapers/resolve.py:67-81`
- `whakoom_scraper/tests/test_scrapers_resolve.py`

#### Implementation

Collect descendant text and normalize whitespace:

```python
parts = anchor.xpath(".//text()").getall()
name = " ".join(part.strip() for part in parts if part.strip())
```

For a 200 fallback body, parse both the edition URL and anchor text. Leave `name=None` only for a redirect-only result.

#### Tests

- Direct anchor text.
- Nested span text.
- Multiple descendant text nodes.
- Empty or whitespace-only text.
- Fallback body with title.
- Redirect-only fallback with null name.

---

## 10. Track G: Publisher, Author, and Series Refresh

### G1. Use External IDs as Primary Identity

#### Reason

Display names are not stable identifiers. Names can change, and multiple creators can share a name.

#### Sources

- `whakoom_scraper/store/repositories.py:258-314`
- `whakoom_scraper/store/queries/series.sql`

#### Implementation

For publishers:

- Upsert by `whakoom_id` when available.
- Update name and URL for that external ID.
- Fall back to exact normalized name only when no ID is available.
- Promote a name-only row only when exactly one unambiguous candidate exists.

For authors:

- Apply the same external-ID-first policy.
- Promote a name-only row only when unambiguous.
- Keep separate rows when the same name appears with different external IDs.
- Log ambiguous promotions instead of silently merging them.

Do not implement fuzzy author or publisher matching.

#### Tests

- Same external ID with a changed name updates one row.
- Same name with different IDs produces separate rows.
- A unique name-only row can be promoted.
- An ambiguous name-only row is not silently merged.

### G2. Reconcile Volumes and Credits Per Series

#### Reason

Current upserts can add and update children but cannot remove volumes or author roles that disappear from the source. Current-state tables would accumulate stale rows.

#### Sources

- `whakoom_scraper/store/repositories.py:331-340`
- `whakoom_scraper/store/repositories.py:444-468`
- `phases.md:332-359`

#### Implementation Before Phase 6

Inside one `db.transaction()`:

1. Upsert publisher.
2. Upsert series.
3. Replace the series' current volume rows.
4. Upsert global author identities.
5. Replace the series' author-role links.
6. Insert the observation.
7. Mark the series completed.

Preserve global publishers and authors. Reconcile only relationships and child records owned by the series.

Use delete-and-reinsert for `series_authors`. Use the same strategy for volumes if no inbound foreign key makes it unsafe.

---

## 11. Track H: Configuration and HTTP Policy

### H1. Validate Settings at Construction

#### Reason

Invalid environment values currently fail later and with less useful errors. Relative cookie paths also use process CWD rather than the project-root rule.

#### Source

- `whakoom_scraper/config.py:18-60`

#### Implementation

Change:

```python
cookie_file: Path | None
```

Resolve it with the same project-relative helper used by database and archive paths.

Validate:

- Profile is nonempty.
- User agent is nonempty.
- Delay is finite and nonnegative.
- Jitter is finite and nonnegative.
- Retry attempts are at least one.
- Booleans are valid explicit representations rather than silent typos.

Check cookie-file existence when the gated resolver starts, not when a public command runs.

#### Tests

Use table-driven invalid-value tests for:

- Negative delay.
- `nan` or `inf` delay.
- Negative jitter.
- Zero retries.
- Misspelled boolean.
- Empty profile.
- Empty user agent.
- Relative cookie path.

Ensure tests do not read the developer's real `.env`.

### H2. Fetch Robots Through `WhakoomSession`

#### Reason

`RobotsPolicy.from_client()` accepts a raw `httpx.Client`, bypassing the centralized politeness and retry contract.

#### Sources

- `whakoom_scraper/http/policy.py:45-72`
- `whakoom_scraper/http/session.py:117-120`

#### Implementation

Separate fetching from parsing:

```python
response = session.get("/robots.txt")
policy = RobotsPolicy.from_text(...)
```

Remove `RobotsPolicy.from_client()` and avoid exposing `WhakoomSession.client` publicly unless a concrete caller needs it.

Tests can continue injecting a prepared `httpx.Client` into `WhakoomSession`.

#### Tests

- Robots retrieval uses normal politeness.
- Transient robots failures use normal retries.
- Permanent robots failures abort initialization.
- Text parsing remains independently testable.

---

## 12. Track I: CLI and Tooling

### I1. Make Unimplemented Commands Fail

#### Reason

Every current command prints a not-implemented message and returns success. This is expected during scaffolding but dangerous for scripts and CI.

#### Source

- `whakoom_scraper/cli.py:31-114`

#### Implementation

Until each stage is implemented, its stub should return a nonzero exit code. Remove each stub when the stage is wired.

Document the complete exit contract:

```text
0 success
1 stage failure
2 validation failure
3 session expired
```

Enforce mutual exclusion for `--list-id` and `--all`.

### I2. Resolve Typer and Rich Drift

#### Reason

`V2.md` explicitly chooses stdlib `argparse` and describes a complete runtime dependency list. The implementation added Typer and Rich without a recorded architectural decision.

#### Sources

- `V2.md:97-127`
- `V2.md:559-573`
- `pyproject.toml:15-23`
- `whakoom_scraper/cli.py`

#### Recommendation

Return to argparse before real stage behavior is implemented.

Seven commands do not justify two additional runtime dependencies, and argparse gives direct control over the project's required exit codes.

If Typer is intentionally retained, record that decision in a new ADR and supersede the argparse portion of the design. Do not keep undocumented drift.

### I3. Honor the Python 3.12 Compatibility Promise

#### Reason

The package declares Python 3.12 compatibility, but Ruff and mypy target Python 3.13.

#### Sources

- `pyproject.toml:6`
- `pyproject.toml:58-64`
- `docs/adr/0004-python-313-and-uv.md`

#### Implementation

Set:

```toml
[tool.ruff]
target-version = "py312"

[tool.mypy]
python_version = "3.12"
```

Continue using Python 3.13 as the pinned development runtime. Add one Python 3.12 CI job later if the compatibility promise remains.

### I4. Contain the Existing Tool Matrix

#### Reason

The owner declined tool consolidation, but several rewriting hooks can still modify frozen legacy code and configurations are split between hook arguments and project files.

#### Sources

- `.pre-commit-config.yaml`
- `TECH_DEBT.md:8-9`
- `TECH_DEBT.md:58-69`

#### Implementation

Without changing the accepted tool list:

- Scope isort, pyupgrade, Ruff, mypy, and pydocstyle to `^whakoom_scraper/`.
- Use non-mutating check modes in CI.
- Keep automatic fixes local to pre-commit if desired.
- Move SQLFluff dialect and shared line-length settings into canonical configuration.
- Add no further quality tools.

---

## 13. Track J: ADR and Documentation Governance

### J1. Establish One Phase Authority

#### Reason

`V2.md` and `phases.md` use incompatible phase numbering, making statements such as "Phase 2 completed" ambiguous.

#### Implementation

Document the authority rule:

```text
V2.md = target architecture and behavior
phases.md = implementation sequence and completion status
```

Do not renumber completed phases. Add a short clarification to the V2 roadmap when documentation changes are permitted.

### J2. Supersede ADR-0003

#### Reason

ADR-0003 requires external enrichment from day one. V2 and the current implementation defer it. The deferred approach is more appropriate because external APIs and fuzzy matching do not help validate the core Whakoom pipeline.

#### Sources

- `docs/adr/0003-external-enrichment.md`
- `V2.md:615-621`

#### Implementation

Create:

```text
ADR-0011: Defer external enrichment until the core Whakoom pipeline is validated
```

It should supersede ADR-0003 and record:

- No enrichment table or stage in the core V2 pipeline.
- External matching remains analytically useful but nonessential.
- Fuzzy title matching introduces correctness and review requirements.
- Future enrichment gets its own forward migration and confidence model.

Update the ADR index to mark ADR-0003 superseded and ADR-0011 accepted.

### J3. Correct Phase Test Commands

#### Reason

Phase-specific gates point at a nonexistent root `tests/` directory. Tests live under `whakoom_scraper/tests`.

#### Sources

- `phases.md:151-155`
- `phases.md:184-188`
- `pyproject.toml:55-56`

#### Implementation

Use explicit existing paths:

```bash
uv run pytest whakoom_scraper/tests/test_store_db.py whakoom_scraper/tests/test_store_repositories.py
uv run pytest whakoom_scraper/tests/test_http_session.py whakoom_scraper/tests/test_http_policy.py whakoom_scraper/tests/test_http_archive.py
```

Apply the same path convention to later phase gates.

### J4. Raise the Threshold for New ADRs

#### Reason

Several accepted ADRs record implementation details rather than durable architectural decisions. Continuing this pattern will create documentation slope.

#### Policy

Use ADRs for:

- Framework and language choices.
- Authentication and source-policy strategy.
- Data identity and schema semantics.
- Resolver request contract.
- Enrichment scope.
- Persistence and history strategy.

Use `phases.md`, code comments, or `TECH_DEBT.md` for:

- Linter invocation details.
- Hash choices made only to satisfy a static-analysis rule.
- Minor test seams.
- Local refactors.

Do not delete or edit accepted ADRs. Apply the stricter threshold only to future decisions.

---

## 14. Consolidated Test Plan

### Store Tests

Add or refine:

```text
test_migration_rolls_back_partial_schema
test_failed_migration_is_not_recorded
test_migration_rejects_transaction_control
test_database_transaction_commits
test_database_transaction_rolls_back
test_failed_reconciliation_preserves_old_rows
test_invalid_list_type_rejected
test_negative_counts_rejected
test_null_and_boundary_ratings_allowed
test_upsert_missing_row_raises
test_changed_list_card_becomes_pending
test_global_slug_mapping_is_reused
```

### HTTP Tests

Add:

```text
test_timeout_is_retried
test_unlisted_exception_is_not_retried
test_post_body_is_preserved_across_retries
test_invalid_retry_count_rejected
test_invalid_delay_rejected
test_robots_fetch_uses_session
test_same_url_different_post_body_archives_separately
test_archive_is_separated_by_run
test_atomic_archive_write_preserves_previous_file
```

### Resolver Tests

Add:

```text
test_quickview_401_expires_session
test_quickview_login_redirect_expires_session
test_expiry_does_not_attempt_fallback
test_fallback_login_redirect_expires_session
test_quickview_nested_title_text
test_fallback_body_extracts_name
test_redirect_only_ref_has_no_name
test_resolver_uses_at_most_two_requests
```

### Integration Test Before Live Phase 4

Build one complete offline flow:

```text
MockTransport
    -> list index response
    -> list page response
    -> pagination responses
    -> parsed domain records
    -> temporary SQLite
    -> list reconciliation
    -> completed list state
    -> raw archive files
    -> idempotent rerun
```

Include a permanently failing pagination request and prove:

- Existing list items remain unchanged.
- The list is not marked completed.
- The run records the failure.
- No partial result replaces current list state.

---

## 15. Execution Sequence

### Stabilization Phase 2.1: Store and Archive Guarantees

1. Fix migration atomicity.
2. Add database transaction and cleanup behavior.
3. Correct archive request identity.
4. Make archive writes atomic.
5. Add adversarial migration and archive tests.
6. Add the integrity-guard migration.
7. Correct phase-specific test paths.
8. Run all five project quality gates.

#### Exit Criteria

- Failed migrations leave no partial schema.
- Failed repository transactions leave prior state intact.
- Every unique pagination and QuickView request is recoverable from the archive.
- Schema constraints reject invalid analytical counts.

### Stabilization Phase 2.2: Domain and HTTP Boundaries

1. Remove surrogate IDs from parser-facing models.
2. Update repository APIs to resolve local keys internally.
3. Replace sentinel zero IDs with explicit failures.
4. Validate settings and normalize cookie paths.
5. Fetch robots through `WhakoomSession`.
6. Decide argparse versus Typer.
7. Align Python tooling with the 3.12 lower bound.
8. Run all five project quality gates.

#### Exit Criteria

- Phase 3 parsers need no database knowledge.
- Invalid runtime configuration fails before making requests.
- No normal HTTP caller bypasses the centralized session policy.

### Phase 3: Pure Parsers and Fixtures

1. Implement the list-index parser.
2. Implement list-detail and pagination parsers.
3. Implement the series parser.
4. Convert resolver behavior into pure response parsers.
5. Harvest representative real fixtures.
6. Assert every documented field and error contract.
7. Avoid live stage orchestration until parser tests pass.

### Phase 4: Public List Stages

1. Implement list discovery.
2. Implement full-list pagination and reconciliation.
3. Make `run-all` reconcile every selected list.
4. Add run bookkeeping and request-aware archiving.
5. Add the full MockTransport-to-database integration test.
6. Perform controlled live public validation.

### Phase 5: Authenticated Resolution

1. Add the superseding resolver ADR.
2. Implement QuickView primary and optional fallback orchestration.
3. Add strict session-expiry handling.
4. Reuse existing global slug mappings.
5. Archive every gated request distinctly.
6. Map expiry to exit code `3`.
7. Measure primary, fallback, and total gated requests.

### Phase 6: Series Current State and History

1. Correct publisher and author identity promotion.
2. Add per-series volume and credit reconciliation.
3. Write current state and observation in one transaction.
4. Ensure failed series are not retried implicitly forever.
5. Add adversarial refresh tests.

---

## 16. Final Acceptance Gate for Stabilization

The Phase 0-2 foundation is ready for parser implementation when:

- Migration application and migration recording are atomic.
- `Database.transaction()` provides commit and rollback safety.
- Initialization failures close database connections.
- Raw archive keys distinguish method and request body.
- Different runs cannot overwrite each other's artifacts.
- Archive writes are atomic.
- Parser-facing dataclasses contain no SQLite surrogate IDs.
- Repository upserts cannot return surrogate ID zero.
- Invalid configuration fails before requests begin.
- Robots retrieval uses the centralized HTTP session.
- Missing analytical constraints are enforced.
- Phase-specific test commands point at real files.
- Resolver request and expiry contracts are unambiguous in ADRs.
- External enrichment is explicitly deferred by a superseding ADR.
- All project quality gates pass:

```bash
uv run pytest
uv run ruff check .
uv run mypy .
uv run bandit -c pyproject.toml -r whakoom_scraper/
uv run pre-commit run --all-files
```

## 17. Final Recommendation

Implement the stabilization work as two small corrective phases before Phase 3. Do not redesign the entire project.

The existing architectural direction remains appropriate:

- Python and synchronous HTTPX match the scale.
- SQLite and named SQL are proportionate.
- Pure parsers remain the correct seam.
- Per-list reconciliation is simple and deterministic.
- Current-state series plus append-only observations satisfy the analytical history requirement.

The work required is foundational hardening, not expansion. Keep every correction local, explicit, and covered by an adversarial test.
