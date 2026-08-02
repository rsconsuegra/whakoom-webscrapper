# Whakoom Scraper V2 — Implementation Phases

> Companion to `V2.md` (design). This document breaks the V2 implementation into **validated, measurable
> stages**. Each phase has explicit deliverables, a validation gate, and numeric acceptance criteria.
> A phase is **done** only when its gate passes; do not start the next phase on a failed gate.
>
> **Environment decision (2026-08-01):** the project runs on **Python 3.13** (pinned in `.python-version`,
> venv rebuilt). `V2.md` declares `requires-python = ">=3.12"`, so 3.13 is fully supported.

---

## How to read this document

- **Phase dependencies** are strict: `P0 → P1 → … → P8`.
- Every phase ends with a **Gate** — the single command/check that must pass.
- Every phase lists **Done when** — concrete, numeric criteria. No subjective "looks good".
- **Owner review** is required at each milestone (`M0`, `M1`, …) before the next phase starts.
- Global quality gates (must hold in *every* phase): `uv run pytest`, `uv run ruff check .`,
  `uv run mypy .`, `uv run bandit -c pyproject.toml -r whakoom_scraper/`,
  `uv run pre-commit run --all-files`. (Bandit reads `[tool.bandit]` from `pyproject.toml`, which
  excludes the `tests/` directory — `assert` statements there are legitimate.)
- All commands use `uv run`. Never bare `pip`/`python -m pip`.

---

## Codebase strategy — "extract, then archive" (owner decision, 2026-08-01)

The legacy `whakoom_webscrapper/` package (Scrapy + Selenium, broken against the live site) is handled as
**frozen reference material**, not as integration target or deletion fodder:

1. **Do not delete** — its spiders encode Whakoom's HTML anatomy (selectors, `SeriesPage` contract, URL
   patterns). That knowledge is the cheapest source for V2's `scrapers/`.
2. **Do not wire it in** — the two designs are incompatible at the seams (Twisted event loop vs sync
   `httpx`, disjoint dependency sets, two config/DB layers). Incremental in-place replacement contradicts
   V2's fresh-scratch design (V2 §4.4, §8.4).
3. **Freeze it in P0** — the `pyproject.toml` rewrite removes its runtime deps, so it becomes dead
   reference code. That is acceptable: it is already broken and only ever needs to be *read*, never *run*.
4. **Consume it in P3** — mine the legacy spiders for selectors and endpoint knowledge; lock that into
   `scrapers/` fixtures and tests. This is when its value is exhausted.
5. **Archive it in P8** — with explicit owner permission, move it to `legacy/` or delete it, only after
   V2 is proven end-to-end and the knowledge lives in fixtures.

---

## Phase 0 — Scaffolding & environment

**Objective:** create the V2 package skeleton with the correct runtime, so every later phase has a
compilable home. Rewrite `pyproject.toml` to the V2 dependency set.

**Deliverables**

- `pyproject.toml` → V2 spec (name `whakoom-scraper`, `requires-python = ">=3.12"`, deps from V2 §4.2,
  `[project.scripts] wk`, dev + analysis groups). Legacy deps (`scrapy`, `scrapy-splash`, `selenium`,
  `requests`, `bs4`) removed from `[project]`. This **freezes** the legacy package as dead reference code
  (see "Codebase strategy" above) — no files deleted, but it becomes non-runnable.
- `uv.lock` regenerated via `uv sync`; `python --version` → 3.13.x.
- Package `whakoom_scraper/` with `cli.py`, `config.py`, `domain.py` (empty dataclass stubs:
  `List`, `ListItem`, `Series`, `Volume`, `Author`, `Publisher`, `Observation`), and empty
  `http/`, `scrapers/`, `store/`, `pipeline/`, `analysis/`, `tests/` subpackages.
- `config.py`: `Settings` dataclass reading env vars from V2 §7, all paths PROJECT_ROOT-relative.
- `.env.example` committed; `.env` gitignored and untracked (`git rm --cached .env` — note: a later
  `git reset` can re-track it; re-untrack after any index reset).
- `data/`, `data/raw/`, `data/exports/` directories created; `.gitkeep` where needed.
- `wk` console script wired: `uv run wk --help` prints command list.
- **Pre-commit aligned with V2 (done in Phase 0, revised 2026-08-02):** `pylint` and `sqlfluff` hooks
  scoped to `whakoom_scraper/` (legacy is frozen and cannot import its removed deps). All lint hooks
  (`flake8`, `isort`, `pyupgrade`, `ruff`, `pylint`, `mypy`, `pydocstyle`, `sqlfluff`) now run with
  `language: system` per-hook so they execute the exact tools from the uv venv — pyproject.toml +
  uv.lock is the single source of truth, no per-hook isolated envs, no `additional_dependencies`
  mirroring (which could drift). Those tools were added to `[dependency-groups.dev]`. (Repo-level
  `language` is not a valid pre-commit key — pre-commit warns and ignores it; it must be per-hook.)
  `[tool.pylint.design] max-attributes = 20` in `pyproject.toml` because data-model dataclasses
  legitimately carry many fields (a threshold tuning, not a rule disable); `[tool.bandit]`
  `exclude_dirs = ["whakoom_scraper/tests"]` (asserts in tests are legitimate).
  Note: `pre-commit run --all-files` only sees **tracked** files — validate a new package with
  `git add -N <path>` (then `git reset`) or by staging on commit.

**Validation gate**

```
uv run pytest           # 0 tests → exit 0 (harness boots)
uv run wk --help        # argparse help renders, exit 0
```

**Done when**

- `uv run python --version` reports `3.13.x`.
- `uv sync` resolves with the V2 dependency set; `duckdb`, `httpx`, `parsel`, `tenacity`,
  `python-dotenv` importable.
- `uv run wk --help` exits 0 and lists `lists`, `list-detail`, `resolve`, `series`, `validate`,
  `analyze`, `run-all`.
- `.env.example` exists; `git check-ignore .env` confirms it is ignored.
- All five quality gates pass on the skeleton (trivially).

---

## Phase 1 — Store layer (schema, migrations, repositories)

> **Status: COMPLETED (2026-08-02).** All gates green: `uv run pytest` (23 passed),
> `uv run ruff check .`, `uv run mypy .`, `uv run bandit -c pyproject.toml -r whakoom_scraper/`,
> `uv run pre-commit run --all-files` (pylint 10.00/10, sqlfluff lint+fix clean).
>
> **Delivered:** `store/db.py` (query loader + migration runner + `Database`), `001_initial_schema.sql`,
> `store/queries/{lists,list_items,series,volumes,observations,runs}.sql`, `store/repositories.py`,
> `tests/conftest.py`, `tests/test_store_db.py`, `tests/test_store_repositories.py`.
>
> **Decisions recorded during implementation:**
> - sqlfluff `AM04` forbids `SELECT *` → all read queries enumerate columns explicitly.
> - sqlfluff `AM09` requires `ORDER BY` with `LIMIT` → author-by-name lookups order by `id`.
> - pylint `W0621` (redefined-outer-name) on the pytest `database` fixture → fixture moved to
>   `tests/conftest.py` (canonical structure) instead of disabling the rule.
> - pylint hook no longer carries `additional_dependencies`: as of the 2026-08-02 revision all lint
>   hooks use `language: system` against the uv venv, so test imports resolve natively.
> - `[tool.pylint.design] max-args = 8` + `max-positional-arguments = 8` for `close_run`'s outcome
>   counters (threshold tuning, consistent with the P0 `max-attributes` precedent).
> - `get_author_by_name` query added (repo needs it); `Volume.series_id` and `Series.scrape_status`
>   added to the domain dataclasses.
> - `.env` re-untracked after the `git add -N`/`git reset` validation loop (staged deletion restored).
>
> **Post-review refinements (2026-08-02, applied after owner review):**
> - **L1 — `series.name` made nullable** (was `NOT NULL`): the resolver maps `volume_slug → series_id`
>   and is now name-aware, but the pure redirect fallback yields no name without a second request, and
>   one request per unique slug is a hard constraint (V2 §11). `scrapers/resolve.py` returns a
>   `SeriesRef` whose `name` may be `None`; `stub_series` accepts a `SeriesRef`; Stage 4 fills the name.
>   `V2.md` §8.3 already declared `name TEXT` nullable — the migration now matches the design.
> - **L2 — per-list reconciliation instead of upsert**: `upsert_list_item` updated `position` on conflict
>   against `UNIQUE (list_id, position)`, so reorders/shrinks raised IntegrityError and stale rows were
>   never deleted. `replace_list_items(db, list_id, items) -> ReconcileResult` now deletes the list's
>   stored rows and inserts the fetched set in one call, preserving resolved `series_id` links, then the
>   stage logs a WARNING + records the delta in `scrape_runs.notes` and proceeds. Queries renamed:
>   `get_list_item_series_map`, `delete_list_items_for_list`, `insert_list_item` replace
>   `upsert_list_item` (removed).

**Objective:** build the persistence backbone: connection management, migration runner, named-query
loader, and typed repositories over the V2 schema. This is the largest isolated piece; everything else
reads/writes through it.

**Deliverables**

- `store/db.py`: sqlite3 connection factory (`PRAGMA foreign_keys=ON`, `journal_mode=WAL`), named-query
  loader (`-- name:` markers), migration runner (ordered, tracked in `_migrations`, per-file transactions).
- `store/migrations/001_initial_schema.sql`: the full schema from V2 §8.3 (`scrape_runs`, `lists`,
  `publishers`, `authors`, `series`, `series_observations`, `volumes`, `series_authors`, `list_items`,
  `_migrations`). Identifier discipline per V2 §8.1 (`whakoom_*` prefixes, surrogate `id` FKs only).
- `store/repositories.py` implementing at least: `upsert_list`, `get_pending_lists`, `get_list`,
  `insert_list_items`, `get_unresolved_slugs`, `stub_series`, `get_pending_series`, `upsert_series`,
  `insert_series_observation`, `create_scrape_run`, `close_scrape_run`.
- `store/queries/*.sql`: `lists.sql`, `list_items.sql`, `series.sql`, `volumes.sql`, `observations.sql`.
- Tests: migration runner, query loader, and repository round-trips against a temp SQLite file.

**Validation gate**

```
uv run pytest tests/test_store*.py        # all store tests pass
```

**Done when**

- Fresh-DB run: `001` applies once; re-running the runner is a no-op (skips applied files).
- `PRAGMA foreign_key_check` returns 0 rows after representative inserts.
- Re-inserting the same `whakoom_list_id` / `(list_id, position)` / `(list_id, volume_slug)` /
  `whakoom_series_id` does **not** raise; upserts update in place (idempotency proven at repo level).
- Repository functions are fully typed and documented; ruff/mypy pass on `store/`.

---

## Phase 2 — HTTP layer & raw archive

**Objective:** a single, polite, resumable HTTP client plus robots policy and the raw-response archive —
the substrate all stages share.

**Deliverables**

- `http/session.py`: sync `httpx.Client` wrapper. Defaults `follow_redirects=True`; per-request override
  exposed for the resolver. Politeness sleep `WK_DELAY_SECONDS + U(0, WK_JITTER_SECONDS)` enforced inside
  the wrapper. Tenacity retry (only `Timeout`, `ConnectError`, 429, 5xx) with exponential backoff, budget
  `WK_MAX_RETRIES`. Cookie jar loaded from `WHAKOOM_COOKIE_FILE` when set.
- `http/policy.py`: robots.txt fetch + cache; `is_allowed(path) -> bool`. Stage 3's gated path is the
  config-gated exception (requires `WK_ALLOW_GATED_RESOLUTION=1`).
- `store`-independent archive helper: gzip to `data/raw/{YYYY-MM-DD}/{stage}/{sanitized_url_key}.html.gz`
  when `WK_SAVE_RAW=1`.
- Tests: `httpx.MockTransport` for retry/backoff, redirect handling, robots allow/deny, archive layout.

**Validation gate**

```
uv run pytest tests/test_http*.py         # all http tests pass
```

**Done when**

- Retry only fires on the allowed transient classes; a permanent 404 is returned immediately.
- Robots: public paths allowed, `/comics/` denied; deny is bypassable **only** with the config flag set.
- Archive: a mocked response writes exactly one gzip file under the dated/stage path.
- Bandit/ruff/mypy clean on `http/`.

> **Status: COMPLETED (2026-08-02).** All gates green: `uv run pytest` 43 passed (20 new http
> tests), ruff/mypy clean, bandit 0 issues on `http/`, pre-commit all green (pylint 10.00/10).
>
> **Delivered**
> - `http/session.py`: `WhakoomSession` wraps a sync `httpx.Client` (default real client targets
>   `BASE_URL` with UA + cookies + 30s timeout, `follow_redirects=True`); injectable `client` for
>   tests. `get`/`post` expose a `follow_redirects=None` per-request override. Politeness sleep
>   `delay + U(0, jitter)` before every attempt using `random.SystemRandom()` (avoids bandit B311).
>   Tenacity `Retrying` (reraise) retries `httpx.TimeoutException`/`ConnectError`/`TransientRequestError`
>   (raised on 429/5xx), `stop_after_attempt(max_retries)`, default `wait_exponential(multiplier=2,
>   exp_base=2, max=30)`; tests inject `wait_none()`. 404 returned immediately. `load_cookies()` reads
>   a Netscape `MozillaCookieJar` → `httpx.Cookies` (skips None-valued cookies). Context-manager
>   protocol. Note: `wait_base` imported from `tenacity.wait` (not the top-level `tenacity` export).
> - `http/policy.py`: `RobotsPolicy` — pure ctor from robots text via `urllib.robotparser`;
>   `from_client` classmethod GETs `/robots.txt`. `is_allowed(path)` returns `allow_gated` for any
>   `/comics/` path (the documented gated exception), else `can_fetch(ua, base_url + path)`.
> - `http/archive.py`: `save_raw(raw_dir, stage, url, content)` → gzip to
>   `raw_dir/{YYYY-MM-DD}/{stage}/{key}.html.gz`; `key = sanitized_path[:120]_sha256(url)[:8]`
>   (sha256, not sha1 — avoids bandit B324). Deterministic per URL; creates parent dirs.
>
> **Test design decisions**
> - `test_http_session.py` uses a reusable `_Responder` callable (records `requests`, exposes `calls`
>   property — added to satisfy pylint R0903) served via `httpx.MockTransport`; politeness asserted
>   by monkeypatching `time.sleep` with `list.append` directly (W0108 forbids the wrapping lambda).
>   Module-level `_redirect_chain_handler`/`_redirect_only_handler` for the redirect cases.
> - All test + nested-handler functions carry one-line docstrings (pylint C0116 / pydocstyle enforced
>   on tests). `request` args are used (no `_`-prefixes), per the recorded W0613 convention.
> - D107 (TransientRequestError.__init__) and D105 (__enter__/__exit__) satisfied with docstrings.
>
> **`.env` handling**: re-untracked (`git rm --cached .env`) after the `git add -N`/`git reset` dance;
> confirmed `D .env`. No live-site requests issued (all via MockTransport).

---

## Phase 3 — Parsers & fixtures (pure functions)

**Objective:** all HTML/JSON → dataclass parsing as pure functions, locked down by snapshot fixtures.
No I/O, no DB (V2 §5 layering rule).

**Deliverables**

- `scrapers/lists_index.py`: `parse_lists_index(html) -> list[List]` (id from URL `_<id>` suffix, name,
  url, description, comic_count, likes).
- `scrapers/list_detail.py`: `parse_list_page(html) -> (list_meta, items)` and
  `parse_series_page_json(payload: dict) -> (items, next_page: int | None)` honoring the
  `ExtraInfo == "0"` termination. Item fields: `position`, `volume_url`, `volume_slug`,
  `whakoom_publication_id`, `volume_number` (`"Vol. N"` → N, `"Tomo único"` → NULL), `publisher`.
- `scrapers/series_page.py`: `parse_series_page(html) -> Series` with name, original_title, publisher,
  status, format, language, volumes_count (`"N cómics"`), synopsis (`"Argumento"`), rating
  (`"4,3"` → `4.3`), rating_count (`"N votos"`), rating_distribution (star %), ownership_count, authors
  (+ roles), volumes list (number, title, publisher, cover_url). Missing optional fields → None + logged.
- `scrapers/resolve.py`: `resolve_series_id(session, volume_slug) -> SeriesRef` covering QuickView primary
  path, redirect fallback (`Location` → `/ediciones/{id}`), parent-link parse, and session-expired
  detection.
- Fixtures in `tests/fixtures/`: harvested from the raw archive or saved snapshots (lists index; list
  page 1; SeriesPage JSON; terminal page; ediciones multi-volume; tomo único; missing-optional-fields;
  multi-author).

**Validation gate**

```
uv run pytest tests/test_scrapers*.py      # all parser tests pass
```

**Done when**

- One fixture per parser case; every documented field asserted; comma-decimal parsing verified
  (`"4,3"` → `4.3`; thousands stripped).
- Pagination terminates on `ExtraInfo == "0"`; a page count of 1 never issues a POST.
- Optional-field absence never raises; required-field absence raises a typed parse error.
- Each parser function has **≥ 1 test**, and coverage of the fixture fields is 100% (assert per field).

---

## Phase 4 — Stages 1 & 2 (public lists)

**Objective:** the first end-to-end public path — lists index and list detail with pagination — against
the live site, storing to the V2 DB.

**Deliverables**

- `pipeline/stage_lists.py`: `wk lists [--reset]` — fetch index, upsert lists, mark pending.
- `pipeline/stage_list_detail.py`: `wk list-detail [--list-id N | --all]` — fetch list page, paginate via
  `POST /lists/listdetail.aspx/SeriesPage` (`{"id": <int>, "f": 0, "p": <page>}`), upsert items, compare
  parsed count vs `lists.comic_count` (mismatch logged, list stays non-completed), mark completed.
- `scrape_runs` rows opened/closed per stage; raw archive enabled.
- Integration test: stages 1→2 over `MockTransport` with fixture HTML/JSON + temp DB.

**Validation gate**

```
uv run pytest tests/test_pipeline*.py && uv run wk lists && uv run wk list-detail --all
```

**Done when**

- **All 66 lists** in `lists` with `scrape_status='completed'` where content was fetched.
- `list_items` rows present for every list; total **≥ 4,000 items** (V2 §3 range lower bound).
- Per-list parsed count **==** advertised `comic_count` for ≥ 95% of lists (remaining logged by list id);
  the reconciliation delta is recorded in `scrape_runs.notes`.
- Re-running `wk list-detail --all` produces **0 new rows, 0 UNIQUE constraint errors** (idempotent).
- No `/comics/` request was issued (all public paths), confirmed via the raw archive keys.

---

## Phase 5 — Stage 3 (resolution, authenticated)

**Objective:** map every distinct `volume_slug` → `whakoom_series_id` using the owner's cookie session,
strictly gated and strictly minimal.

**Deliverables**

- `WHAKOOM_COOKIE_FILE` + `WK_ALLOW_GATED_RESOLUTION=1` set in `.env` (cookie file itself stays out of git).
- `pipeline/stage_resolve.py`: `wk resolve [--limit N]` — for each unresolved distinct slug: QuickView →
  redirect-fallback → parent-link parse; stub series from a `SeriesRef` (name-aware: name filled when
  parseable, else NULL until Stage 4); set `list_items.series_id`. Redirect to `/login` →
  **abort stage with exit code 3** and a loud message. Unresolved slugs → `data/review_unresolved.csv`.
- Tests: resolver redirect / parent-link / session-expired / name-aware paths via `MockTransport`.

**Validation gate**

```
uv run pytest tests/test_resolve*.py && uv run wk resolve
```

**Done when**

- ≥ 95% of distinct `volume_slug`s resolved to a `series_id` (residual in `review_unresolved.csv`).
- Exactly **one request per unique slug** (verified by counting archive keys for the resolve stage).
- Session expiry aborts the stage, exit code `3`, and re-running resumes without duplicates.
- The stubbed `series` rows are `scrape_status='pending'` with `whakoom_series_id`, `slug`, `url`;
  `name` is populated for ≥ 95% of resolved slugs (name-aware resolver), others NULL until Stage 4.

---

## Phase 6 — Stage 4 (series scraping)

**Objective:** the complete analytical dataset — current state + first observation history — from public
ediciones pages.

**Deliverables**

- `pipeline/stage_series.py`: `wk series [--force] [--limit N]` — for each pending series, fetch
  `/ediciones/{id}/{slug}`, parse, and in **one transaction**: upsert publisher → series → volumes →
  authors/junction → insert one `series_observations` row → set `completed`. Required-field failures mark
  `failed` and continue (never row-fatal for optional fields).
- `analysis/` seeded: `views.sql` placeholder + `explore.ipynb`.

**Validation gate**

```
uv run pytest tests/test_series*.py && uv run wk series
```

**Done when**

- `series` populated for **≥ 95%** of resolved series (others `failed`, logged).
- Every series has **≥ 1** `series_observations` row; `series_observations` has one row per `(series, run)`.
- `rating` ∈ [0, 5] for all rows; `rating_count`, `ownership_count`, `volumes_count` ≥ 0 (schema-enforced,
  double-checked by `wk validate`).
- A manual spot-check of ≥ 10 series (e.g. `Rosen Blood`) matches the live page field-for-field.
- Re-run with `--force` creates exactly one *new* observation row per series and 0 duplicate errors.

---

## Phase 7 — Validation gate & analytics (DuckDB)

**Objective:** make the dataset trustworthy (hard gate) and turn it into queryable views + exports.

**Deliverables**

- `pipeline/validate.py`: `wk validate` — read-only checks from V2 §12 (per-list count reconciliation,
  `PRAGMA foreign_key_check`, duplicate keys, unresolved count, rating/count bounds, row-count deltas,
  parse-failure rate < 5%). Non-zero exit on failure. `wk analyze` refuses without `--force` after failure.
- `pipeline/export.py`: `wk analyze [--force]` — DuckDB `INSTALL/LOAD sqlite; ATTACH data/whakoom.db`;
  apply `analysis/views.sql` (`v_titles_by_year`, `v_titles_by_magazine`, `v_publisher_share_by_year`,
  `v_rating_by_publisher`, `v_score_history`, `v_list_overlap`); `COPY` exports to `data/exports/`.

**Validation gate**

```
uv run wk validate && uv run wk analyze
```

**Done when**

- `wk validate` exits 0 on the populated dataset; parse-failure rate per stage < 5%; row-count deltas vs
  previous run within tolerance (no unexplained drops).
- `data/exports/` contains **lists, list_items, series, volumes, observations** CSVs.
- The notebook answers on **real data**: (a) top publishers by year; (b) score distribution; (c) score /
  ownership trend of one series over ≥ 2 runs.
- `v_titles_by_year` and `v_titles_by_magazine` return ≥ 1,000 and ≥ 100 rows respectively (sanity floor).

---

## Phase 8 — Polish, docs & full run

**Objective:** make the project reproducible and documented; prove the whole pipeline from empty DB.

**Deliverables**

- `README.md` rewritten: workflow (`uv run wk run-all`), config table, login/cookie setup,
  **ethics note** (public robots-allowed bulk + gated resolution tradeoff, per V2 §19), run profile,
  site-drift caveat.
- `analysis/explore.ipynb` finalized with starter queries; `views.sql` final.
- Pre-commit config aligned with V2 quality gates; `.env.example` final.
- **Legacy archive** (explicit owner permission required): move `whakoom_webscrapper/` to `legacy/` or
  delete it — only after V2 is proven end-to-end and all selectors live in fixtures (Codebase strategy
  step 5).

**Validation gate**

```
rm -f data/whakoom.db && uv run wk run-all && uv run wk validate && uv run wk analyze
# then re-run the whole suite once more to prove idempotency
uv run wk run-all && uv run wk validate
```

**Done when**

- `run-all` (stages 1→5) completes end-to-end from an **empty** database with exit 0; second full run is a
  no-op for data (0 new rows, 0 constraint errors) yet adds a new `series_observations` batch.
- All five quality gates pass on the full package.
- README documents: the workflow, the cookie-file requirement, `WK_ALLOW_GATED_RESOLUTION=1` tradeoff,
  and the "cataloging not sales" guardrail.

---

## Milestones & review points

| Milestone | Phase | Owner confirms |
|---|---|---|
| M0 | 0 | runtime on 3.13, skeleton boots, deps final |
| M1 | 3 | fixture/parser coverage acceptable before live traffic |
| M2 | 4 | live public data in DB; counts reconcile |
| M3 | 5 | cookie flow works; resolution rate acceptable |
| M4 | 6 | full dataset; spot-checks pass |
| M5 | 7 | validation passes; notebook answers on real data |
| M6 | 8 | full re-runnable pipeline; docs complete |

## Phase dependency graph

```
P0 ──▶ P1 ──▶ P2 ──▶ P3 ──▶ P4 ──▶ P5 ──▶ P6 ──▶ P7 ──▶ P8
                         │
                         └── (P4, P5, P6 all depend on P3 parsers)
```

## Definition of "validated" (applies to every phase)

1. The phase's numeric **Done when** criteria are met (not just "it ran").
2. The phase's **validation gate** command(s) exit 0.
3. All five **global quality gates** pass.
4. The owner reviewed the milestone and approved proceeding.
