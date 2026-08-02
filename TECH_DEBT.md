# Tech Debt — Whakoom Scraper V2

Tracked refinements discovered during review of Phases 0–2. Each entry records the
issue, its impact, the proposed fix, and when it should be addressed. Items here are
**not** blockers — the code works without them — but each one will cost more the
longer it stays open.

> Lint/format consolidation (11 overlapping pre-commit tools) was reviewed and
> **explicitly declined** by the owner (2026-08-02). It is intentionally absent.
>
> Items **R1, R2, R5** are addressed by `PRE_PHASE3_PLAN.md` (items A1, E4, B1) and are
> closed once that plan is executed. R3, R4 and the "Deferred from PRE_PHASE3 review"
> sections below remain open.

---

## R1 — Failed items are re-requested forever

- **Where:** `store/queries/lists.sql` (`get_pending_lists`), `store/queries/series.sql` (`get_pending_series`)
- **Problem:** both select `scrape_status != 'completed'`, which **includes** `'failed'`.
  A permanently-failing list or series is retried on every run, forever, with no backoff
  and no retry budget.
- **Impact:** wasted requests and runtime on every full run; failure mode is invisible
  (a failing item looks "pending").
- **Proposed fix:** exclude `'failed'` from the default pending selection, and only retry
  failed items when the stage is run with `--force` (or add an explicit retry budget).
- **Address in:** Phase 4 (list-detail selection) and Phase 5/6 (resolve/series selection).

---

## R2 — Migration runner is not transactional per file

- **Where:** `whakoom_scraper/store/db.py` (`_apply_migrations`)
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

## R5 — `data/raw/` and `data/exports/` vanish on fresh clone

- **Where:** `.gitignore` + `data/raw/.gitkeep` / `data/exports/.gitkeep`
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

## Closed by PRE_PHASE3_PLAN (on execution)

- **R1 → E4** — pending selection excludes `failed`; retry only via `--force`.
- **R2 → A1** — per-file migration atomicity (explicit transaction instead of `executescript`).
- **R5 → B1** — request-aware archive key (method + body in the digest) and archive dir creation.
