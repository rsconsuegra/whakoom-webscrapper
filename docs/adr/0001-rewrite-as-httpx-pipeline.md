# ADR-0001 — Rewrite V2 as a plain-Python httpx pipeline

- **Status:** Accepted
- **Date:** 2026-08-01
- **Supersedes:** (none)

## Context

The legacy scraper (`whakoom_webscrapper/`) is built on Scrapy + Twisted with a Selenium/ChromeDriver
loop for list pagination. It is unmaintainable and broken against the live site:

- Whakoom now hard-redirects `/comics/` to `/login` and disallows crawlers there in `robots.txt`, so
  the legacy pipeline that walks `/comics/` volume links can no longer run anonymously.
- List pagination is a single JSON POST (`/lists/listdetail.aspx/SeriesPage`) that works anonymously
  with a plain HTTP client — it needs no browser.
- Scrapy's spider/pipeline/middleware machinery is heavy for ~3 static page types.
- The hand-rolled ORM (`to_tuple`, `table_name`, `__getitem__`) duplicates the schema across
  models, queries, and migrations.
- There are zero tests, and the config has two divergent DB-path sources of truth.

## Decision

Rewrite the scraper as `whakoom_scraper/`, a plain-Python 3.12+ package:

- **HTTP:** synchronous `httpx.Client` with `tenacity` retries/backoff and a politeness limiter;
  `parsel` for selectors (same syntax as the legacy Scrapy selectors).
- **Persistence:** stdlib `sqlite3` behind a small `store/` layer (named-query loader, migration
  runner, typed repositories). No ORM, no Scrapy item pipeline.
- **Flow:** six explicit CLI stages (`lists`, `list-detail`, `resolve`, `series`, `validate`,
  `analyze`), each idempotent and resumable via DB state.
- **Fresh database:** the legacy DB is empty (`databases/` holds no data), so V2 starts with a new
  schema and no legacy data migration.

The legacy package is frozen reference material: never deleted or wired in; its selectors are mined
during parser development and it is archived only with explicit owner permission.

## Consequences

**Positive:** testable (fixture-based parser tests, `httpx.MockTransport` integration tests); one
config source (`config.py`, PROJECT_ROOT-relative); single page-parse concern per module; retry and
politeness are centralized; the tool is debuggable and deterministic.

**Negative:** we lose Scrapy's built-in concurrency, retry middleware, and item exporters; a full run
is slower (~2–4 h at 1 req/1.5 s politeness). The Selenium approach to JS pages is gone — pages that
require JS must be solved with their backing JSON endpoints instead.

## Alternatives considered

- **Patch the legacy Scrapy pipeline** — rejected: the `/comics/` dependency is broken at its core
  and Selenium is a maintenance liability.
- **Async httpx from the start** — deferred: the async `Client` is a near drop-in later; sync-first
  keeps determinism and debuggability, a stated project value.
