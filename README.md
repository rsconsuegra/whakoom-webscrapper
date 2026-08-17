# Whakoom Manga Lists Scraper — V2

A Python 3.13 scraper that builds an analytical dataset of manga from a public
Whakoom user profile: the profile's lists, every title on them, and full series
metadata (volumes, authors, publishers, ratings) — scraped **once per title**
with observation history over time.

- **Design:** `V2.md` (architecture authority) · `phases.md` (implementation stages) · `docs/adr/` (decisions)
- **Agent rules:** `AGENTS.md`
- **Stack:** httpx + tenacity (HTTP), parsel (HTML), SQLite (persistence), DuckDB (analytics), Typer + rich (CLI)
- **Status:** V2 complete (phases P0–P8); dataset validated end-to-end from an empty database

> This is a **cataloging and research** project. It does not estimate sales,
> track purchases, or support commercial use of Whakoom's data (see
> [Ethics](#ethics--compliance)).

---

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                     # install runtime + dev deps into .venv
cp .env.example .env        # then edit (see Configuration below)
uv run wk run-all           # full pipeline: scrape → validate → analyze
```

For the `resolve` stage you also need a cookie file — see
[Cookie setup](#cookie-setup-authenticated-resolution).

## The pipeline

Six stages, each one responsibility, each resumable and idempotent:

| # | Command | What it does | Auth | Requests |
|---|---------|--------------|------|----------|
| 1 | `wk lists [--reset]` | Fetch the profile's list index; upsert list cards | public | ~1 |
| 2 | `wk list-detail [--list-id N \| --all]` | Fetch each list + paginate; reconcile items per list | public | ~1 per list + 1 per extra page |
| 3 | `wk resolve [--limit N]` | Map each distinct `volume_slug` → `whakoom_series_id` | **gated** (cookies) | exactly 1 per new slug |
| 4 | `wk series [--force] [--limit N]` | Scrape `/ediciones/{id}/{slug}`; upsert series, volumes, authors; append one observation row per series | public | 1 per pending series |
| 5 | `wk validate` | 8 read-only consistency checks; snapshots row counts | local | 0 |
| 6 | `wk analyze [--force]` | Classify lists, build DuckDB views, export CSVs | local | 0 |

`wk run-all` chains 1→6, stopping at the first failure and propagating its exit
code. On re-runs stages are no-ops for settled data (reconciliation deletes
stale rows, upserts are idempotent). Observation history grows only when you
re-scrape explicitly: `wk series --force` appends one `series_observations` row
per series per run (owner decision 2026-08-16 — `run-all` never re-scrapes
completed series implicitly).

**Exit codes:** `0` success · `1` stage failure · `2` validation failure (or
analyze refusing to run after a failed validate, unless `--force`) · `3`
session expired during `resolve` (refresh cookies, re-run; resumable).

## Configuration

All settings come from environment variables / `.env` (see `.env.example`).
Paths resolve relative to the repo root, never the working directory.
Misconfiguration fails fast with a named-variable error.

| Variable | Default | Meaning |
|----------|---------|---------|
| `WHAKOOM_PROFILE` | `deirdre` | Target user profile |
| `WHAKOOM_COOKIE_FILE` | *(empty)* | Netscape-format cookie jar for stage 3; must exist if set |
| `WK_ALLOW_GATED_RESOLUTION` | `0` | Must be `1` or stage 3 refuses to run (explicit opt-in, see [Ethics](#ethics--compliance)) |
| `WK_DB_PATH` | `data/whakoom.db` | SQLite database path |
| `WK_DELAY_SECONDS` | `1.5` | Politeness delay before every request |
| `WK_JITTER_SECONDS` | `0.5` | Uniform jitter added to the delay |
| `WK_MAX_RETRIES` | `3` | Retry attempts for timeouts / connect errors / 429 / 5xx |
| `WK_SAVE_RAW` | `1` | Gzip raw HTML responses to the archive |
| `WK_RAW_DIR` | `data/raw` | Raw archive root (`{date}/{stage}/` inside) |
| `WK_USER_AGENT` | `whakoom-scraper/2.0 (personal research)` | Honest user agent sent on every request |

## Cookie setup (authenticated resolution)

Stage 3 resolves volume slugs to series ids via Whakoom's QuickView endpoint,
which requires a logged-in session:

1. Log in to whakoom.com in your browser.
2. Export cookies in **Netscape format** (any "cookies.txt" browser extension).
3. Save as e.g. `cookies.txt` in the repo root (gitignored) and set in `.env`:
   ```
   WHAKOOM_COOKIE_FILE=cookies.txt
   WK_ALLOW_GATED_RESOLUTION=1
   ```
4. Run `uv run wk resolve`.

If the session expires mid-run the stage aborts loudly with exit code `3`;
re-export fresh cookies and re-run — it resumes with only the unresolved slugs.

## Ethics & compliance

- Bulk scraping (stages 1, 2, 4) hits **public, robots.txt-allowed** pages at a
  polite rate (`1.5s + U(0, 0.5s)` per request) with an honest user agent and
  one request per unique page per run.
- **Stage 3 is a deliberate, documented exception:** it uses an authenticated
  session against `/comics/` paths, which `robots.txt` disallows. This is an
  owner-approved tradeoff for a single-user personal/research project — it is
  gated behind `WK_ALLOW_GATED_RESOLUTION=1`, issues exactly one request per
  unique slug, and is the only way to obtain `whakoom_series_id` for list items.
- No secrets in code or git; the cookie file path lives in `.env` (gitignored).
- The data is used for **cataloging and personal analysis, not sales
  estimation or commercial exploitation**.
- **Site drift:** the parsers depend on Whakoom's current HTML and JSON
  contracts (verified 2026-08). When the site changes, expect parse failures —
  fix forward via new fixtures in `whakoom_scraper/tests/fixtures/`.

## Run profile

Measured on the current dataset (61 lists · 1,643 list items · 1,183 series):

| Run | Requests | Wall time |
|-----|----------|-----------|
| First full `run-all` (empty DB) | ~1,500 | ~45–60 min (dominated by stage 4: 1,183 series pages) |
| Steady-state `run-all` | ~100 (index + list refresh; stages 3–4 no-op) | ~4–5 min |
| `wk series --force` (new observation batch) | 1,183 | ~35 min |

Retries: timeouts/connect errors/429/5xx back off exponentially (max 3
attempts); permanent errors (404) fail immediately and are logged.

## Data & outputs

| Path | Contents |
|------|----------|
| `data/whakoom.db` | SQLite: `lists`, `list_items`, `series`, `volumes`, `authors`, `publishers`, `series_observations`, `scrape_runs`, `validation_snapshots` |
| `data/whakoom.duckdb` | DuckDB database with the analytics views (re-ATTACHes the SQLite file read-only) |
| `data/exports/*.csv` | Flat exports of the five core tables, written by `wk analyze` |
| `data/raw/{date}/{stage}/` | Gzipped raw HTML archive of every response (`WK_SAVE_RAW=1`) |
| `analysis/views.sql` | The six view definitions (`v_titles_by_year`, `v_titles_by_magazine`, `v_publisher_share_by_year`, `v_rating_by_publisher`, `v_score_history`, `v_list_overlap`) |
| `analysis/explore.ipynb` | Executed notebook with starter queries (top publishers by year, score distribution, score/ownership trend) |

Schema evolves via forward-only SQL migrations in
`whakoom_scraper/store/migrations/`, applied once in filename order. All SQL
lives in named query files (`whakoom_scraper/store/queries/*.sql`) — the
application never writes inline SQL.

## Development

```bash
uv run pytest                                  # offline test suite
uv run ruff check .                            # lint
uv run mypy .                                  # types
uv run bandit -c pyproject.toml -r whakoom_scraper/
uv run pre-commit run --all-files              # all hooks (incl. pylint, sqlfluff)
uv run --group analysis jupyter lab analysis/  # notebook work
```

Layout:

```
whakoom_scraper/
├── cli.py, config.py, domain.py     # Typer CLI, env settings, dataclasses
├── http/                            # session (retries/politeness), robots, raw archive
├── scrapers/                        # pure HTML/JSON → dataclass parsers
├── store/                           # Database, repositories, queries/, migrations/
├── pipeline/                        # stages 1–4 + validate + export + run_all
└── analysis/                        # list-name classification
analysis/                            # views.sql + explore.ipynb (repo root, not packaged)
data/                                # db, duckdb, exports, raw archive (gitignored)
legacy/                              # archived Scrapy+Selenium V1 tree (reference only)
docs/                                # ADRs and legacy docs
```

The archived V1 scraper lives in `legacy/whakoom_webscrapper/` (Scrapy +
Selenium, broken against the live site). It is reference material only: never
imported, never deleted — its selector knowledge now lives on in the V2 test
fixtures.

## Known limitations & future work

- List classification (`list_type`, `canonical_name`) is regex-based
  (`whakoom_scraper/analysis/classification.py`); a hand-curated
  `config/lists.toml` remains a deferred option (V2 §20).
- No external enrichment (AniList/MAL), no async HTTP, no scheduling — all
  deliberately deferred (V2 §20–21).
- Observation history only grows via explicit `wk series --force` runs.
