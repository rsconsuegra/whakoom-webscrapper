# Tech Debt — Whakoom Scraper V2

> **Status (2026-08-02): PRE_PHASE3 complete.** Every item in
> `PRE_PHASE3_PLAN.md` (A1, A2, A3, A4, B1, C2, D1, E1, E2, E3, E4, F2, F3, F4, H1,
> H2, I1, I2, I3, J1, J3) is resolved; ADR-0010 (typer+rich CLI) and ADR-0011
> (Python 3.13-only) are accepted and indexed. All five quality gates pass on 88
> tests. The open items below (R3, R4, C1, C3, G1, G2, J2, J4) are the deferred set
> (§"Explicitly NOT in this plan", `PRE_PHASE3_PLAN.md` §5).

Tracked refinements discovered during review of Phases 0–2. Each entry records the
issue, its impact, the proposed fix, and when it should be addressed. Items here are
**not** blockers — the code works without them — but each one will cost more the
longer it stays open.

> Lint/format consolidation (11 overlapping pre-commit tools) was reviewed and
> **explicitly declined** by the owner (2026-08-02). It is intentionally absent.

---

## R1 — Failed items are re-requested forever — RESOLVED

- **Where:** `store/queries/lists.sql` (`get_pending_lists`), `store/queries/series.sql` (`get_pending_series`)
- **Status:** ✅ Resolved by PRE_PHASE3 **E4** — `get_pending_*` now selects
  `scrape_status = 'pending'` only; failed items are excluded by default and surface
  via the new `get_failed_*` queries, retried only with `--force` (repo flag
  `include_failed=True`).
- **Problem:** both select `scrape_status != 'completed'`, which **includes** `'failed'`.
  A permanently-failing list or series is retried on every run, forever, with no backoff
  and no retry budget.
- **Impact:** wasted requests and runtime on every full run; failure mode is invisible
  (a failing item looks "pending").
- **Proposed fix:** exclude `'failed'` from the default pending selection, and only retry
  failed items when the stage is run with `--force` (or add an explicit retry budget).
- **Address in:** Phase 4 (list-detail selection) and Phase 5/6 (resolve/series selection).

---

## R2 — Migration runner is not transactional per file — RESOLVED

- **Where:** `whakoom_scraper/store/db.py` (`_apply_migrations`)
- **Status:** ✅ Resolved by PRE_PHASE3 **A1** — each migration file now runs inside
  an explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` with a `_split_statements` helper;
  a failing file leaves no partial schema and no `_migrations` row.
- **Problem:** migrations run through `conn.executescript(...)`, which issues an implicit
  `COMMIT` before the script and executes in autocommit mode. A migration that fails
  halfway leaves a partially-applied schema with **no** `_migrations` marker, so the file
  re-runs and fails again — recovery is manual.
- **Impact:** contradicts the documented "per-file transaction" guarantee (V2 §8.4,
  phases.md P1); a bad migration can corrupt the schema with no automatic rollback.
- **Proposed fix:** wrap each migration in an explicit `BEGIN`/`COMMIT` (or `executescript`
  inside a manual transaction) so a failure rolls back the whole file, or correct the docs
  to state the real semantics.
- **Address in:** next migration (before the first real schema change).

---

## R3 — Lossy row mappers drop surrogate ids

- **Where:** `whakoom_scraper/store/repositories.py` (`_series_from_row`, `_list_from_row`)
- **Problem:** `_series_from_row` does not map `publisher_id` back onto the domain object,
  and `_list_from_row` does not surface the surrogate `id`. Repository round-trips lose
  information that later stages need for FK linkage (e.g. relinking volumes/authors without
  a re-query).
- **Impact:** forces extra queries in Stage 4/6; any future cross-entity linkage must
  work around the gap.
- **Proposed fix:** surface `publisher_id` and the surrogate `id` on the relevant domain
  dataclasses (or dedicated link objects) when Phase 6 wiring needs them.
- **Address in:** Phase 6 (series scraping).

---

## Deferred from PRE_PHASE3 review

Items surfaced by the GPTSol stabilization analysis but explicitly **deferred** (owner-approved):
not blockers, they do not gate Phase 3, and each should be revisited at the phase indicated.

### C1 — Surrogate ids on domain models

- **Where:** `whakoom_scraper/domain.py` (`ListItem.list_id`, `Volume.series_id`, `Series.scrape_status`,
  `Observation.series_id/run_id`)
- **Problem:** domain dataclasses carry surrogate DB ids and workflow state alongside external ids, mixing
  persistence concerns into pure models.
- **Impact:** low today; the parser seam (stage fills `list_id`; `SeriesRef` returns external ids) already
  isolates the surrogates.
- **Proposed fix:** remove surrogates from the pure models and pass them as explicit stage arguments;
  surface workflow state through repository queries instead of the model.
- **Address in:** opportunistically, alongside Phase 6 wiring — **not** a Phase-3 gate.

### C3 — Lossy row mappers drop surrogate ids

- **Where:** `whakoom_scraper/store/repositories.py` (`_series_from_row` drops `publisher_id`;
  `_list_from_row` drops surrogate `id`)
- **Problem:** repository round-trips lose information later stages need for FK linkage, forcing re-queries.
- **Proposed fix:** surface `publisher_id` and the surrogate `id` on the relevant domain objects (or
  dedicated link objects) when Stage 4/6 needs them.
- **Address in:** Phase 6 (series scraping).

### G1 — Publisher/author identity by external id

- **Where:** `whakoom_scraper/store/repositories.py` (`upsert_publisher` is name-only;
  `upsert_author` is already id-first when `whakoom_id` is present)
- **Problem:** publishers are keyed by name only; a publisher renamed on Whakoom becomes a duplicate row.
  Authors are already on the better (external-id-first) path.
- **Impact:** cosmetic until Stage 4 starts writing publishers.
- **Proposed fix:** mirror the author pattern — upsert publishers by `whakoom_id` first, fall back to name.
- **Address in:** Phase 4/6 when publishers are first scraped.

### G2 — Series-child reconciliation

- **Where:** `whakoom_scraper/store/repositories.py` (`upsert_volumes`, `insert_observation`)
- **Problem:** volumes and observations upsert but never reconcile; a volume removed from the site (or a
  changed `volumes_count`) leaves stale child rows. Same class of problem L2 fixed for list items.
- **Proposed fix:** per-series reconciliation mirroring `replace_list_items` when Stage 4 re-scrapes a
  series.
- **Address in:** Phase 6.

### J2 — Enrichment contradiction (ADR-0003 vs schema vs V2.md)

- **Where:** `docs/adr/0003-external-enrichment.md` (day-one table) vs `whakoom_scraper/store/migrations/001_initial_schema.sql`
  (no `series_enrichment`) vs V2.md §20 (deferred)
- **Problem:** ADR-0003 promises a first-class `series_enrichment` table from day one; the schema and V2.md
  defer it to the optional `enrich` stage.
- **Proposed fix:** supersede ADR-0003 with a new ADR when the `enrich` stage is built (table arrives via
  migration), or document the deferral now.
- **Address in:** with the `enrich` stage (post-Phase-8 roadmap).

### J4 — ADR threshold policy

- **Where:** `docs/adr/`
- **Problem:** ADR-0005 and ADR-0007 are implementation details (hook language; a hash function) rather
  than architecture decisions — the bar for "significant technical decision" is undefined.
- **Proposed fix:** codify a threshold (e.g. "changes an external contract, the data model, or cross-stage
  behavior → ADR; internal implementation choices → code + comment") and apply it retroactively.
- **Address in:** whenever convenient (forward-looking convention).

---

## R4 — Linter configuration is split across pre-commit args

- **Where:** `.pre-commit-config.yaml` (per-hook `args`) vs `pyproject.toml`
- **Problem:** `sqlfluff`'s `--dialect sqlite` and the line-length settings only exist as
  pre-commit hook arguments. Running `uv run sqlfluff lint` directly defaults to the ANSI
  dialect and reports false positives, and there is no `.sqlfluff`/`.pylintrc` to make
  direct invocation match the hooks.
- **Impact:** tool drift between pre-commit and manual runs; a contributor running tools
  directly sees different results than CI.
- **Proposed fix:** move dialect/line-length config into `pyproject.toml`
  (`[tool.sqlfluff]`, `[tool.pylint]`) so both pre-commit and direct runs agree.
- **Address in:** whenever convenient (low urgency, pre-commit is the canonical path).

---

## R5 — `data/raw/` and `data/exports/` vanish on fresh clone — RESOLVED

- **Where:** `.gitignore` + `data/raw/.gitkeep` / `data/exports/.gitkeep`
- **Status:** ✅ Resolved by PRE_PHASE3 **B1** — the request-aware archive layer
  (`http/archive.py::save_raw`) creates parent dirs with `mkdir(parents=True,
  exist_ok=True)`; archive keys now include method + request body so POST QuickView
  bodies can no longer collide on the same URL.
- **Problem:** both directories are gitignored, so their `.gitkeep` files are never tracked
  and the directories don't exist on a fresh clone. Any stage that writes to them without
  creating parents fails at runtime.
- **Impact:** `data/raw/` and `data/exports/` must be recreated manually or the first write
  must `mkdir -p`; first run on a new checkout can error unexpectedly.
- **Proposed fix:** the HTTP archive layer and export stage create their directories with
  `mkdir(parents=True, exist_ok=True)` (config.py already does this for `WK_DB_PATH`).
- **Address in:** Phase 2 (http layer archive) and Phase 7 (exports).

---

## Accepted and closed

- **L1 — `series.name` nullable** — fixed in place (no DB exists yet); migration now matches
  V2 §8.3 design. Name-aware resolver in `scrapers/resolve.py` returns `SeriesRef` with
  `name: str | None`.
- **L2 — per-list reconciliation** — `replace_list_items` + `ReconcileResult` replace the
  position-unsafe upsert; stale rows removed, resolved links preserved, deltas logged in
  `scrape_runs.notes`.
- **Linter consolidation (R-informal)** — owner declined; pre-commit matrix stays as-is.
- **typer + rich CLI (I2)** — owner requested; stays. Documented in ADR-0010 (see
  `PRE_PHASE3_PLAN.md` S1.3.I2).
- **Python 3.13-only (I3)** — owner requested; other interpreters out of scope. Documented in
  ADR-0011 (see `PRE_PHASE3_PLAN.md` S1.3.I3).

## Closed by PRE_PHASE3_PLAN (all resolved 2026-08-02)

> Every work item in `PRE_PHASE3_PLAN.md` §2 is done; the five quality gates pass on
> 88 tests; ADR-0010 and ADR-0011 are accepted and indexed. One-line notes per item:

- **A1 → R2** — migration runner now transactional per file via explicit
  `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` + `_split_statements`.
- **A2** — `Database.transaction()` context manager + `begin()`/`rollback()`; nested
  use raises `RuntimeError`.
- **A3** — query loader now rejects non-empty `.sql` files with zero `-- name:`
  markers (`ValueError`).
- **A4** — `Database.__init__` closes the sqlite handle on migration/query-load
  failure before re-raising.
- **B1 → R5** — archive key is request-aware (method + url + body digest);
  `save_raw` creates parent dirs.
- **C2** — sentinel-`0` ids replaced by `RecordMissingError` in `upsert_list`,
  `upsert_publisher`, `upsert_author`, `stub_series`, `upsert_series`.
- **D1** — `001_initial_schema.sql` enriched with `>= 0` CHECKs on
  `series`/`series_observations` plus `idx_observations_series` and
  `idx_volumes_series`; `list_type` left unconstrained with a comment.
- **E1** — `invalidate_lists` query + repo flip every list (incl. `failed`) back to
  `pending` for `wk lists --reset`.
- **E2** — `ReconcileResult.inserted` renamed to `written` (matches its semantics).
- **E3** — `get_global_slug_series_map` query + repo; `replace_list_items` reuses
  resolved `series_id` across lists.
- **E4 → R1** — `get_pending_*` excludes `failed`; new `get_failed_*` queries; repo
  flag `include_failed=True` opts back in (`--force`).
- **F2** — resolver split: pure parsers stay in `scrapers/resolve.py`; HTTP
  orchestration moved to `http/resolve.py` (`resolve_series_id`, `SessionExpiredError`).
- **F3** — `SessionExpiredError` now fires on `401`, pre-follow `3xx → /login`, and
  post-follow final-URL `/login` (or login-form signature).
- **F4** — `_name_from_quickview` joins all descendant `::text` so nested
  `<span>` titles are captured.
- **H1** — strict `_env_bool`, numeric bounds (`delay > 0`, `jitter >= 0`,
  `max_retries >= 0`), and `cookie_file` resolved through `PROJECT_ROOT`.
- **H2** — `RobotsPolicy.from_client` now takes the `WhakoomSession` so the robots
  fetch travels the same delay/retry path as every other request.
- **I1** — `_not_implemented` raises `typer.Exit(code=1)`; a stub can never masquerade
  as a completed stage.
- **I2** — `docs/adr/0010-typer-rich-cli.md` accepted; V2.md §16 points to it.
- **I3** — `requires-python = ">=3.13"`, 3.12 classifier dropped; `docs/adr/0011-python-313-only.md`
  accepted (supersedes ADR-0004 on the version-floor point only).
- **J1** — `phases.md` → "Phase numbering" maps roadmap Phase 0–5 ↔ workstream P0–P8;
  `V2.md` §17 carries the matching pointer.
- **J3** — every phase-gate command in `phases.md` corrected to
  `whakoom_scraper/tests/...` (matching `testpaths`); `-k` equivalents noted.

## Still open (deferred — see PRE_PHASE3_PLAN §5)

R3, R4, C1, C3, G1, G2, J2, J4 — these are **not** PRE_PHASE3 items and remain open
at the phase indicated in their entries above.
