# ADR-0009 — Per-list reconciliation instead of item upsert

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)
- **Related:** ADR-0008 (name-aware resolution — sibling robustness fix from the same review)

## Context

Stage 2 (`wk list-detail`) writes a list's items to `list_items`. The Phase 1 implementation used a
per-item upsert:

```sql
INSERT INTO list_items (...) ON CONFLICT(list_id, volume_slug)
DO UPDATE SET position = excluded.position, ...;
```

Three properties of the schema and the data made this unsafe for re-runs:

1. `position` participates in a `UNIQUE (list_id, position)` constraint. Updating a row's `position`
   can collide with another row's current position, so any swap, shrink, or reorder between runs
   raises `IntegrityError` mid-`executemany`.
2. Stale rows are never deleted. An item removed from the list on the site stays in the database
   forever.
3. Consequently the documented "re-run is a no-op" property only holds when the list is *unchanged*.
   Any change made the stage neither idempotent nor resumable.

The fetched list is the version of truth: the site is the source, the database is a mirror.

## Decision

Replace the per-item upsert with **per-list reconciliation**, executed **once per list after all
pagination pages are fetched** (never per page):

`replace_list_items(db, list_id, items) -> ReconcileResult` in `store/repositories.py`:

1. Snapshot the current `volume_slug → series_id` map for the list.
2. `DELETE` all rows for the list.
3. `INSERT` the freshly fetched set, restoring `series_id` from the snapshot for slugs the resolver
   already linked (new slugs keep `series_id = NULL` and wait for Stage 3).

`ReconcileResult(previous_count, new_count, inserted, removed, removed_slugs)` reports the delta. The
stage logs a WARNING and records the delta in `scrape_runs.notes` whenever `removed > 0` or counts
drift — then **proceeds** (latest version wins).

Supporting changes:

- `store/queries/list_items.sql`: `upsert_list_item` removed; added `get_list_item_series_map`,
  `delete_list_items_for_list`, and a plain `insert_list_item`.
- `store/repositories.py`: `upsert_list_items` removed; `replace_list_items` added. Repos still never
  commit — the calling stage owns the transaction, so the delete+insert pair runs atomically.
- Tests: added for stale-row removal (`removed_slugs` reported), position swap no longer raising,
  and `series_id` link preservation across a re-scrape.

## Consequences

**Positive:** re-runs are idempotent regardless of site-side changes (adds, removes, reorders,
shrinks); stale items are removed rather than accumulating; resolved `series_id` links survive
re-scrapes; positions are deterministic (the fetched order *is* the state); deltas are visible in
`scrape_runs.notes` for validation and forensics.

**Negative:** a slug removed from a list loses its resolved `series_id` if it is re-added later and
must be re-resolved (Stage 3 handles this); surrogate `id`s for `list_items` churn on every reconcile
— safe because `list_items` has no inbound foreign keys, so no referential integrity is disturbed.

## Alternatives considered

- **Keep upsert, then delete rows not in the fetched set.** Rejected: does not fix the `UNIQUE
  (list_id, position)` collision on swaps/reorders, and adds a second pass over the same rows.
- **Reassign positions in a transaction (re-number everything, then upsert).** Rejected: more moving
  parts for the same outcome; reconciliation achieves identical state with strictly less SQL.
