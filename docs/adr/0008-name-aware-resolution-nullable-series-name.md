# ADR-0008 — Name-aware resolution with nullable `series.name`

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)
- **Related:** ADR-0002 (cookie-backed resolution — same stage), ADR-0009 (per-list reconciliation — sibling robustness fix from the same review)

## Context

Stage 3 (`wk resolve`) maps `volume_slug → series_id`. On success it stubs a `series` row via
`stub_series` so Stage 4 can later fill the full record. The stub carries `whakoom_series_id`,
`slug`, `url`, and `name`.

Two constraints collided in the Phase 1 schema:

1. `series.name TEXT NOT NULL` (migration 001), while
2. the resolver does not always have a name available.

Resolution proceeds through three paths, in order:

- **QuickView** (`POST /pwkws.asmx/QuickView`, primary) — the card carries the series title, so a
  name is almost always parseable.
- **Redirect fallback** (`GET /comics/{slug}/...`, `follow_redirects=False` → `Location` contains
  `/ediciones/{id}`) — yields ID + slug **but no name**.
- **Parent-link parse** on a 200 body — name may be present.

Extracting a name in the redirect case would cost a second request, violating the hard
**one-request-per-unique-slug** constraint from ADR-0002 / V2 §11. The series *name* is genuinely
Stage 4's job (parsed from the `/ediciones/{id}/{slug}` page).

As designed, the first `wk resolve` hitting a `name=None` stub raises `IntegrityError`. The
repository test suite never caught this because `test_stub_then_full_upsert_shares_id` fed the stub a
`Series` that already had a name.

Notably, V2.md §8.3 already declared `name TEXT` nullable — the migration had drifted from the design.

## Decision

1. **Make `series.name` nullable.** Edit migration 001 in place (safe: no production DB exists yet;
   the database is fresh and no migration has ever run against real data). The schema now matches the
   V2 §8.3 design.
2. **Make the resolver name-aware.** `scrapers/resolve.py` exposes
   `resolve_series_id(session, volume_slug) -> SeriesRef | None` where `SeriesRef(whakoom_series_id,
   slug, url, name: str | None = None)`:
   - Populate `name` wherever it is parseable (QuickView card first, 200-volume-page body second).
   - Leave `name = None` when only the pure redirect is available — still resolve, never a second
     request.
3. **`stub_series` accepts a `SeriesRef`** and passes the (possibly `None`) name through; Stage 4
   fills the name on the full series upsert.

## Consequences

**Positive:** the stage never blocks a resolved slug on a missing name; resolution coverage stays at
the ≥95% goal (no resolved slug is deferred to `review_unresolved.csv` purely for lack of a name);
the one-request-per-slug constraint is preserved; the migration now matches the published design.

**Negative:** `series.name` can be `NULL` until Stage 4 runs; any consumer reading the name before
then must tolerate `None` (the domain type already expresses this as `str | None`).

## Alternatives considered

- **Keep `NOT NULL`; treat nameless slugs as unresolved.** Rejected: resolvable slugs would land in
  `review_unresolved.csv`, artificially dropping resolution coverage below the ≥95% acceptance bar and
  forcing manual re-work on data the resolver already identified.
- **Second request to fetch the name in the redirect path.** Rejected: breaks the one-request-per-slug
  hard constraint (ADR-0002) and roughly doubles the resolve stage's runtime for a field Stage 4
  obtains for free.
