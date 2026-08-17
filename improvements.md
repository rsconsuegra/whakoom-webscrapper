# V2 Migration Improvement Plan

## Purpose

This plan converts the migration review into executable work. The goal is to
make the V2 pipeline correct, resumable, testable, and honestly represented by
`V2.md`, `phases.md`, and the current dataset.

The plan is ordered by dependency. Do not advance to validation and analytics
until the data-producing stages satisfy their contracts.

## Current Baseline

- Store, HTTP, parser, public-list, and resolver code exists.
- Stage 4 (`series`) exists but has no dedicated pipeline test suite.
- `validate`, `analyze`, and `run-all` are still CLI stubs.
- The current staged database reported by `p6.md` contains 61 lists and 1,646
  items, below the P4 acceptance target of 66 lists and at least 4,000 items.
- `uv run ruff check .` and `uv run mypy .` pass.
- The full test suite is blocked by an obsolete smoke test that invokes the
  now-real `series` command and can perform live work.

## Decisions Required First

### D1: Resolver request budget

The documents currently conflict:

- `V2.md` and `phases.md` require exactly one request per unique slug.
- The resolver implementation uses QuickView plus a `/comics/` fallback.

Choose one contract before changing code:

1. Keep the fallback and change the acceptance criterion to a maximum of two
   requests per slug, with both requests archived and counted.
2. Enforce one request per slug by selecting one resolver endpoint and treating
   failure as unresolved.

Recommended: retain the fallback because it improves resolution coverage, but
change all documentation and tests to say "at most two authenticated requests
per unique slug". The authenticated footprint must still be bounded and
auditable.

### D2: Slug identity model

Decide whether `volume_slug` is globally unique to one series. If yes, enforce
and validate that invariant. If no, resolution must be scoped by another stable
identifier and must not update every list item sharing a slug.

Recommended: treat a resolved volume slug as one-to-one with its parent series,
but detect conflicting observations and abort that slug instead of silently
selecting an arbitrary mapping.

## Workstream 1: Restore Test Safety

### 1.1 Replace the obsolete CLI smoke test

Update `whakoom_scraper/tests/test_phase0_smoke.py` so it tests the current
`series` command through dependency injection or mocks. It must never issue a
live request. Add CLI tests for:

- `validate` exit code `2` on validation failure.
- `analyze` refusing to run after validation failure unless `--force` is set.
- `run-all` ordering and stop-on-failure behavior.
- resolver session expiry propagating exit code `3`.
- all command help and option parsing.

### 1.2 Add a CI-safe network guard

Add a test fixture or transport guard that fails if any test attempts an
unmocked network request. All tests must remain offline by construction.

### 1.3 Establish a temporary baseline gate

Before further work, require:

```text
uv run pytest
uv run ruff check .
uv run mypy .
uv run bandit -c pyproject.toml -r whakoom_scraper/
uv run pre-commit run --all-files
```

## Workstream 2: Correct Stage 1 and Stage 2

### 2.1 Invalidate changed lists

Modify `upsert_list` so content-affecting changes reset a completed list to
`pending`. Preserve completion only when the fetched card metadata is
unchanged. Add repository tests for changed count, URL, name, and unchanged
metadata.

### 2.2 Validate HTTP responses before parsing

Call `raise_for_status()` after every stage GET and POST response, before raw
archiving/parsing where appropriate. Add tests proving 404 and permanent 4xx
responses mark the target failed and never mark it completed.

### 2.3 Avoid unnecessary pagination

Use the advertised count and/or first-page result to avoid posting page 2 when
the first page is complete. Keep the endpoint terminator as a defensive stop.
Add a request-count assertion for one-page and multi-page lists.

### 2.4 Record reconciliation deltas

Capture `ReconcileResult` from `replace_list_items()`. When rows are removed,
reordered, or changed:

- emit a warning containing the list id and counts;
- record the delta in `scrape_runs.notes`;
- continue with the newly fetched list as the source of truth.

Add tests for removed slugs, reordered positions, and resolved-link
preservation.

### 2.5 Fail on malformed required list data

Introduce typed parse errors for missing list identity, invalid volume URLs,
and malformed pagination payloads. Optional fields may remain nullable and
logged. Required-field failures must leave the list non-completed.

## Workstream 3: Harden Resolution

### 3.1 Implement the selected request-budget decision

Update implementation, archive naming, run notes, and tests according to D1.
Count logical requests separately from retry attempts. Retries must not make
the audit ambiguous.

### 3.2 Archive every resolver response

Archive QuickView and fallback responses when `WK_SAVE_RAW=1`, including the
request method and body in the archive key. Add tests that assert archive count
and deterministic keys.

### 3.3 Make fallback resolution name-aware

When a fallback returns HTTP 200, parse both the parent series reference and
the series name. Add a fixture and test for this path.

### 3.4 Preserve all unresolved work on session expiry

When the session expires, write both already-unresolved and unprocessed slugs
to `review_unresolved.csv`. Record processed, unresolved, and skipped counts in
the aborted run notes. Add a resume test.

### 3.5 Detect ambiguous mappings

Change global slug-map construction and `set_item_series()` so conflicting
slug-to-series mappings are detected and logged as unresolved rather than
silently choosing the last database row.

## Workstream 4: Complete Stage 4

### 4.1 Enforce required series structure

Add a typed `SeriesParseError`. Missing `h1` or the required volume block must
raise it. Stage 4 must mark that series `failed`, continue with other series,
and close the run with accurate counters.

### 4.2 Complete parser coverage

Implement and test:

- per-volume publisher;
- author roles such as script/writing and drawing;
- missing optional-field warnings;
- tomo unico and multi-volume pages;
- required-field failures;
- invalid rating/count values.

Every documented output field must have an assertion in a fixture test.

### 4.3 Add Stage 4 integration tests

Create `test_pipeline_series.py` covering:

- happy path persistence;
- publisher, author, junction, volume, and observation rows;
- malformed-page failure and continuation;
- transient failure and continuation;
- `--limit` request cap;
- `--force` producing exactly one new observation per series;
- robots denial;
- raw archive output;
- idempotent reruns.

Handle `SessionExpiredError` explicitly if it can occur on the public series
path; no run may remain stuck in `running`.

### 4.4 Remove stale volumes and author links

When a series page changes, reconcile its current volumes and author junctions
instead of only upserting new rows. Otherwise deleted volumes/authors remain
in the analytical dataset.

## Workstream 5: Repair Store Integrity

### 5.1 Align schema and documentation

Reconcile the `series.slug` uniqueness decision between the migration and
`V2.md`. Restore the `list_type` check constraint or document why it is
deferred and add validation for invalid values.

Rename external ID fields to explicit names such as
`whakoom_publisher_id` and `whakoom_author_id`, or update the identifier rule
to explicitly allow the generic form.

### 5.2 Fix author and publisher identity reconciliation

Handle transitions between name-only and ID-bearing authors without duplicate
rows. Handle publisher name/ID conflicts deterministically and report identity
conflicts instead of raising an opaque uniqueness error.

### 5.3 Make repository writes observable

Check affected-row counts for status updates and run closure. Reject negative
counters, invalid run transitions, nonexistent run IDs, and conflicting
observation inserts.

Preserve `{}` rating distributions as JSON instead of converting them to
`NULL`.

### 5.4 Simplify transaction ownership

Choose either the context-managed transaction API or explicit `begin`/`commit`/
`rollback`. If both remain public, keep `_in_transaction` synchronized and add
tests for mixed usage and rollback behavior.

### 5.5 Add missing repository tests

Cover changed-list invalidation, ambiguous slugs, author identity upgrades,
publisher conflicts, zero-row updates, invalid counters, observation conflicts,
empty JSON objects, and transaction failures.

## Workstream 6: Implement Validation and Analytics

### 6.1 Implement `wk validate`

Add read-only checks for:

- list advertised-count reconciliation;
- foreign-key violations;
- duplicate natural keys;
- unresolved item counts;
- rating and count bounds;
- row-count deltas against the previous successful run;
- parse-failure rate below 5%.

Return exit code `2` for validation failure and write the summary to the
current run record.

### 6.2 Implement `wk analyze`

Require successful validation unless `--force` is supplied. Load DuckDB's
SQLite extension, create the documented views, and export lists, list items,
series, volumes, and observations.

### 6.3 Implement `wk run-all`

Run stages in order, stop on fatal stage errors, stop before analytics when
validation fails, and preserve each stage's exit code semantics. Add a mocked
orchestration test rather than relying only on shell execution.

## Workstream 7: Reconcile Migration Status and Data

### 7.1 Update phase status honestly

Add explicit status notes to `phases.md` for P3 through P6 only after their
gates pass. Update `docs/README.md`, `docs/architecture.md`, and `p6.md` so
they agree about what is implemented, deferred, or blocked.

### 7.2 Re-run public stages from a clean database

After Stage 1 and Stage 2 fixes:

```text
rm -f data/whakoom.db
uv run wk lists
uv run wk list-detail --all
```

Verify the actual list and item counts against P4 acceptance criteria. Any
missing lists must be explained by parser coverage or site drift, not silently
accepted.

### 7.3 Run resolution and series stages incrementally

Use `--limit` first, inspect raw archives and database rows, then process the
full dataset. Verify unresolved output, request budgets, failure rates, and
observation counts before proceeding.

### 7.4 Prove clean-run idempotency

Run the complete pipeline twice. The second run must introduce no duplicate
current-state rows or constraint errors and must create exactly one new
observation batch when the series stage is intentionally rerun.

## Definition of Done

The migration is ready for owner approval when all of the following hold:

- all seven CLI commands are implemented and have contract tests;
- all tests are offline and the full suite passes;
- the five global quality gates pass;
- P4-P6 numeric acceptance criteria are met on a freshly rebuilt database;
- validation passes on the populated dataset;
- analytics exports and views work on real data;
- a second full run is idempotent for current-state data;
- `V2.md`, `phases.md`, `p6.md`, and supporting documentation describe the same
  implementation state;
- the legacy package remains untouched until explicit archive approval.

## Suggested Execution Order

1. Fix the live-network smoke test and establish a green offline baseline.
2. Fix Stage 1/2 status, HTTP, pagination, and reconciliation defects.
3. Decide and implement the resolver request-budget contract.
4. Harden resolver auditing and resume behavior.
5. Complete Stage 4 parser and pipeline tests.
6. Repair store integrity and add missing repository tests.
7. Rebuild and verify the dataset against P4-P6 acceptance criteria.
8. Implement validation, analytics, and `run-all`.
9. Update phase documents and complete the full clean-run/idempotency gate.
