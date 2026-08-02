# Whakoom Scraper — Documentation

Reference documentation for the V2 Whakoom scraper (`whakoom_scraper/`), a plain-Python
`httpx`-based pipeline that extracts manga-collection data from curated Whakoom user lists.

> This documentation describes **only what is built today** plus **what is immediately next**
> (Phase 3 — the public parsers). Later phases (stages, validation, analytics) are tracked in
> [`../phases.md`](../phases.md) and are not detailed here yet.

## Where to start

| If you want to… | Read |
|---|---|
| Understand the system at a glance (components, data model, request lifecycle) | [architecture.md](architecture.md) |
| See why a decision was made | [adr/](adr/) — in particular the [ADR index](adr/README.md) |
| Run the scraper | [`../phases.md`](../phases.md) (CLI stages) — commands run via `uv run wk <stage>` |
| Compare against the legacy Scrapy/Selenium implementation | [legacy/](legacy/) (frozen reference, not wired in) |

## Documents

- **[architecture.md](architecture.md)** — system overview with Mermaid diagrams: component graph,
  database ERD, domain class diagram, and sequence/flow diagrams for the request lifecycle, list-detail
  pagination, and gated series resolution.
- **[adr/](adr/)** — Architecture Decision Records (Nygard format). See the
  [ADR index](adr/README.md) for the full list. Key decisions:
  - [ADR-0001](adr/0001-rewrite-as-httpx-pipeline.md) — rewrite V2 as a plain-Python `httpx` pipeline
  - [ADR-0002](adr/0002-cookie-backed-series-resolution.md) — cookie-backed resolution for the gated step
  - [ADR-0006](adr/0006-http-retry-and-transient-error-contract.md) — HTTP retry & transient-error contract
  - [ADR-0007](adr/0007-bandit-safe-randomness-and-hashing.md) — bandit-safe randomness & hashing
- **[legacy/](legacy/)** — the **frozen** Scrapy/Selenium-era documentation. Kept as reference only; the
  legacy `whakoom_webscrapper/` package is never imported or wired into V2.

## Build status

| Area | Phase | Status |
|---|---|---|
| Package scaffold, config, CLI, domain models | P0 | ✅ Built |
| Store layer (SQLite, migrations, named queries, repositories) | P1 | ✅ Built |
| HTTP layer (session, robots policy, raw archive) | P2 | ✅ Built |
| Series resolver (gated, cookie-backed) | P3 (partial) | ✅ `resolve.py` built |
| Public parsers (`lists_index`, `list_detail`, `series_page`) + fixtures | P3 | ⏳ Next |
| Stages, validation, analytics | P4–P8 | 🔜 Planned (see [`../phases.md`](../phases.md)) |
