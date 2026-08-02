# ADR-0003 — External enrichment (MAL/AniList/MangaUpdates) from day one

- **Status:** Accepted
- **Date:** 2026-08-01
- **Supersedes:** (none)

## Context

The core dataset (Whakoom lists, series metadata, ratings, volumes) answers "what was published in
Spain, by which publisher and magazine". The owner also wants external, community-curated ratings to
enrich the analysis (MAL, AniList, MangaUpdates). Enrichment is orthogonal to the scraping stages and
must not block them. Deciding it upfront avoids retrofitting a schema and pipeline later.

## Decision

Include enrichment in the V2 design from the start, as a dedicated optional stage (`enrich`) and a
dedicated table (`series_enrichment`):

- **Sources:** AniList (GraphQL, free, no key) and Jikan/MAL (REST, free, no key) as the pragmatic
  pair; MangaUpdates (public API) optional.
- **Matching:** exact ES title → normalized title (case/diacritics/punctuation) → search fallback;
  each match stores a `match_confidence`; rows below a threshold export to `review_unmatched.csv`.
- **Non-blocking:** the stage only touches series with `scrape_status = 'completed'` and
  `enriched_at IS NULL`; it never gates stages 1–4.

## Consequences

**Positive:** enrichment is a first-class citizen in schema (`series_enrichment`), stage ordering, and
the analytics exports; no retrofit later; external lookups are rate-limited and resumable.

**Negative:** extra moving parts (three external APIs, matching logic) and external availability
dependencies; enrichment data can be stale relative to the snapshot unless re-run.

## Alternatives considered

- **Add enrichment post-hoc after the core scraper** — rejected: schema and analytics changes would
  ripple later; the owner approved including it from the start.
- **Only Whakoom-native ratings** — rejected: external ratings are an explicit owner requirement.
