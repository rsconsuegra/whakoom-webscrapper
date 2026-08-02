# PRE_PHASE3_PLAN — Stabilization before Phase 3

- **Status:** Ready for execution by a long-horizon agent
- **Date:** 2026-08-02
- **Base:** `feature/v2` (Phase 0–2 complete; 51 tests passing, all gates green)
- **Source analysis:** `GPTSol_phase_0_2_stabilization_plan.md` (verified against code; this document is the
  re-prioritized, owner-approved version)
- **Owner decisions baked in:**
  - **typer + rich stay** for the CLI (owner preference). No return to argparse. Drift vs V2.md is
    documented via ADR-0010.
  - **Python 3.13 only.** `requires-python` becomes `>=3.13`, the 3.12 classifier is dropped, tools target
    3.13. Support for other interpreters is **out of scope** — the project fits the owner first
    (ADR-0011 supersedes ADR-0004's `>=3.12` claim).
  - Pre-commit matrix unchanged (owner comfortable with it).

---

## 1. How to use this document

Work items are grouped in three stabilization workstreams:

- **S1.1 — Store & archive** (everything that touches `store/` + the raw archive)
- **S1.2 — Domain & http** (parsers, resolver, session, policy, config)
- **S1.3 — Docs & tooling** (ADRs, version pins, phase numbering, test paths)

Each item is tagged with a **P-priority** (P0 = blocks Phase 3 wiring, do first; P1 = must exist before the
stage that needs it; P2 = correctness/hygiene, cheap now). Do them **in order within each workstream**.
Items tagged **P0 must be fully done and gated before any Phase 3 parser work starts.**

Acceptance for every item = code written, tests added/updated, and the full gate list (§3) green.

---

## 2. Work items

### S1.1 — Store & archive

#### A1. Migration runner must be transactional per file — **P0**

- **Files:** `whakoom_scraper/store/db.py`, `whakoom_scraper/tests/test_store_db.py`
- **Problem:** `_apply_migrations` runs each file via `conn.executescript(...)`. `executescript` issues an
  implicit `COMMIT` *before* the script and executes in autocommit mode, so a migration that fails halfway
  leaves a partially-applied schema with **no** `_migrations` row. Re-running fails again; recovery is manual.
  This contradicts the documented "per-file transaction" guarantee (V2 §8.4, phases.md P1).
- **Change:**
  1. In `_apply_migrations`, for each pending file (in filename order), replace `conn.executescript(text)`
     with an explicit transaction:
     ```python
     conn.execute("BEGIN IMMEDIATE")
     try:
         for statement in _split_statements(text):
             conn.execute(statement)
         conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (filename,))
         conn.execute("COMMIT")
     except BaseException:
         conn.execute("ROLLBACK")
         raise
     ```
  2. Add a module-level helper `_split_statements(text) -> Iterator[str]` that walks the text using
     `sqlite3.complete_statement()` so a statement is not split mid-string. (Migration files are owned by
     this repo, so the `.sql` content is trusted; the splitter is defensive.)
  3. Keep the existing `_migrations` creation (filename PK, `applied_at`).
- **Tests (test_store_db.py):**
  - `test_migration_that_fails_leaves_no_partial_schema` — write a temp migrations dir with two files;
    make the second file fail on its 3rd statement (e.g. `CREATE TABLE t_bad(a); CREATE TABLE t_bad2(b);
    INSERT INTO nonexistent(c) VALUES (1);`). Expect `Database(...)` to raise; assert neither `t_bad` nor
    `t_bad2` exists and the `_migrations` table has only the first filename. Re-open with the bad file
    removed and assert the good file is not re-run.
  - `test_migrations_apply_once_and_record` — existing test must still pass unchanged (regression guard).
- **Acceptance:** a broken migration can never leave a partial schema; a repaired migration applies cleanly.

---

#### A2. Transaction API on `Database` — **P1** (required before Phase 4 list-detail reconcile)

- **Files:** `whakoom_scraper/store/db.py`, `whakoom_scraper/tests/test_store_db.py`
- **Problem:** `Database` has `execute/executemany/fetchone/fetchall/commit/close` but **no**
  `begin/rollback/transaction` context manager. Stage 4's `replace_list_items` is a delete+insert pair that
  must be atomic; today there is no sanctioned way to make a multi-statement write atomic.
- **Change:**
  1. Add `begin()` → `self.conn.execute("BEGIN IMMEDIATE")`.
  2. Add `rollback()` → `self.conn.execute("ROLLBACK")`.
  3. Add a `transaction()` `@contextmanager` that yields `self`, commits on clean exit, rolls back and
     re-raises on exception. Guard against nesting with a `_in_transaction` flag (nested use → `RuntimeError`).
  4. Keep repos never-commit (existing rule); stage code owns `with db.transaction():`.
- **Tests (test_store_db.py):**
  - `test_transaction_commits_on_success` — begin, insert, exit, row persists.
  - `test_transaction_rolls_back_on_exception` — begin, insert, raise inside `with`, row absent.
  - `test_transaction_nesting_raises` — nested `with db.transaction():` raises `RuntimeError`.
- **Acceptance:** any multi-statement stage write can be made atomic with one context manager.

---

#### D1. Schema enforcement — direct edit of `001_initial_schema.sql` — **P1**

- **Files:** `whakoom_scraper/store/migrations/001_initial_schema.sql`, `whakoom_scraper/tests/test_store_db.py`
- **Rationale:** **No production DB exists** (fresh; we already edited 001 in place for L1). Editing 001
  directly is cheaper and matches repo precedent — do **not** build validation-trigger machinery.
- **Change (add to the existing file, no new migration):**
  1. `series`: add `CHECK (volumes_count >= 0)`, `CHECK (rating_count >= 0)`, `CHECK (ownership_count >= 0)`
     (`rating` already has `CHECK (rating BETWEEN 0 AND 5)`).
  2. `series_observations`: add the same three `>= 0` CHECKs.
  3. Add `CREATE INDEX idx_observations_series ON series_observations (series_id);` (referenced by
     `ON CONFLICT(series_id, run_id)` lookups but never created).
  4. Add `CREATE INDEX idx_volumes_series ON volumes (series_id);` (FK lookups from `series → volumes`).
  5. `list_type`: **leave unconstrained** for now and add a `--` comment noting it is intentionally
     unconstrained until Stage 1 defines the value domain.
- **Tests (test_store_db.py):** a new test asserting `PRAGMA index_list('series_observations')` and
  `PRAGMA index_list('volumes')` each contain the new index; existing migration tests stay green.
- **Acceptance:** fresh DB carries full constraints; no test regression.

---

#### C2. Kill the sentinel-`0` id — raise instead — **P1**

- **Files:** `whakoom_scraper/store/repositories.py`, `whakoom_scraper/tests/test_store_repositories.py`
- **Problem:** `upsert_list` (~:106), `upsert_publisher` (~:274), `upsert_author` (~:314), `stub_series`
  (~:363), `upsert_series` (~:425) all `return 0` when their post-insert re-query comes back empty. A
  silently-returned `0` becomes a bogus FK in the caller and fails later, far from the root cause.
- **Change:**
  1. Add `class RecordMissingError(RuntimeError)` in `repositories.py`.
  2. In each of the five functions, replace `return 0` with `raise RecordMissingError(...)` including a
     message that names the entity and the lookup that failed.
  3. Return types stay `int` (now guaranteed a real id) — no caller signature change.
- **Tests (test_store_repositories.py):** for each function, monkeypatch the follow-up getter to return
  `None` and assert `pytest.raises(RecordMissingError)`; assert happy-path ids are `> 0`.
- **Acceptance:** no code path can silently produce id `0`.

---

#### E4. Pending selection must exclude `failed` (retry only with `--force`) — **P1**

- **Files:** `whakoom_scraper/store/queries/lists.sql`, `whakoom_scraper/store/queries/series.sql`,
  `whakoom_scraper/store/repositories.py`, `whakoom_scraper/tests/test_store_repositories.py`
- **Problem:** `get_pending_lists` (lists.sql:73) and `get_pending_series` (series.sql) use
  `scrape_status != 'completed'`, which **includes** `'failed'` → permanently-failing items re-requested
  every run, forever, with no backoff.
- **Change:**
  1. `lists.sql`: `get_pending_lists` → `WHERE scrape_status = 'pending'`; add
     `get_failed_lists` → `WHERE scrape_status = 'failed'`.
  2. `series.sql`: same split (`get_pending_series`, `get_failed_series`).
  3. `repositories.py`: change signatures to `get_pending_lists(db, *, include_failed: bool = False)` and
     `get_pending_series(db, *, include_failed: bool = False)`, returning the union when `include_failed`.
- **Tests:** `test_get_pending_lists_excludes_failed` (a `failed` list is not returned by default, IS
  returned with `include_failed=True`); mirror for series. Update any existing test that relied on the
  old `!= 'completed'` semantics.
- **Acceptance:** default runs skip `failed`; `--force` opts back in.

---

#### E1. List invalidation on refresh (`--reset` must re-scrape) — **P1**

- **Files:** `whakoom_scraper/store/queries/lists.sql`, `whakoom_scraper/store/repositories.py`,
  `whakoom_scraper/tests/test_store_repositories.py`
- **Problem:** `upsert_list` does **not** touch `scrape_status`, so a `completed` list stays completed
  forever even after site-side changes; `wk lists --reset` is a no-op for completed lists.
- **Change:**
  1. Add query `invalidate_lists` → `UPDATE lists SET scrape_status = 'pending', scraped_at = NULL`.
  2. Add repo `invalidate_lists(db)`. Extend `reset_lists_pending` (currently `completed → pending` only)
     to also flip `failed → pending`, or document that `--reset` calls `invalidate_lists` instead.
  3. CLI `lists --reset` will call `invalidate_lists` (wiring happens in Phase 4; the query/repo land now).
- **Tests:** repo test — upsert → mark `completed` → `invalidate_lists()` → list appears in
  `get_pending_lists()`.
- **Acceptance:** a `--reset` run genuinely re-scrapes every list.

---

#### E3. Global slug→series map (resolution links reused across lists) — **P1**

- **Files:** `whakoom_scraper/store/queries/list_items.sql`, `whakoom_scraper/store/repositories.py`,
  `whakoom_scraper/tests/test_store_repositories.py`
- **Problem:** `replace_list_items` only reuses the **same-list** `previous` map, so a slug already resolved
  in list A re-requests resolution when it appears in list B — wasted gated requests.
- **Change:**
  1. Add query `get_global_slug_series_map` →
     `SELECT DISTINCT volume_slug, series_id FROM list_items WHERE series_id IS NOT NULL`.
  2. Add repo `get_global_slug_series_map(db) -> dict[str, int]`.
  3. In `replace_list_items`, build rows with
     `item.series_id or previous.get(item.volume_slug) or global_map.get(item.volume_slug)`.
- **Tests:** resolve a link in list A; `replace_list_items` list B with the same slug; assert B's row
  carries the series_id and no resolution happened. Also keeps the existing same-list preservation test green.
- **Acceptance:** cross-list link reuse works; supersedes the "removed slug must re-resolve" caveat in
  ADR-0009's consequence note.

---

#### E2. `ReconcileResult.inserted` → `written` — **P2** (rename only)

- **Files:** `whakoom_scraper/domain.py`, `whakoom_scraper/store/repositories.py`,
  `whakoom_scraper/tests/test_store_repositories.py`
- **Change:** rename the field `inserted` to `written` (docstring already says rows are physically
  rewritten). Update construction in `replace_list_items` and every test reference.
- **Acceptance:** field name matches its semantics.

---

#### A3. Query loader must reject SQL files without markers — **P2**

- **Files:** `whakoom_scraper/store/db.py` (`load_queries`), `whakoom_scraper/tests/test_store_db.py`
- **Problem:** a non-empty `.sql` file with **no** `-- name:` markers is silently ignored; a typo in the
  marker leaves a whole query set silently missing.
- **Change:** for each `.sql` file whose stripped body is non-empty and yields zero markers, raise
  `ValueError` (consistent with the existing empty-body / duplicate-name strictness).
- **Tests:** `test_non_empty_file_without_markers_raises` — write such a file, expect `ValueError`.
- **Acceptance:** marker typos fail fast at load time.

---

#### A4. `Database.__init__` must not leak the connection on failure — **P2**

- **Files:** `whakoom_scraper/store/db.py`
- **Change:** wrap the `load_queries(...)` and `_apply_migrations(...)` calls in `__init__` in
  `try/except`; on failure `self.conn.close()` then re-raise.
- **Tests:** no dedicated test required; existing tests guard the happy path. (Optional: assert a broken
  migrations dir leaves no open handle — can be skipped if hard to observe.)
- **Acceptance:** a failed init closes the sqlite handle.

---

### S1.2 — Domain & http

#### B1. Request-aware raw archive key — **P0**

- **Files:** `whakoom_scraper/http/archive.py`, `whakoom_scraper/tests/test_http_archive.py`
- **Problem:** `_url_to_key` hashes **URL only**. The QuickView endpoint is a POST to the *same* URL with
  different JSON bodies (`cid=comic{slug}`); once archiving is wired, those bodies would collide and
  overwrite each other. (Collision is latent today — `save_raw` is defined but never called; fix before
  wiring it into `WhakoomSession._request`.)
- **Change:**
  1. Replace `_url_to_key` with `_request_key(method: str, url: str, request_body: bytes | None)` →
     `f"{method}_{sanitized_path[:120]}_{sha256((url + (request_body or b'')).encode()).hexdigest()[:8]}"`.
  2. Extend `save_raw(raw_dir, stage, method, url, content, request_body=None)` and pass through.
  3. When Phase 3 wires the call site in `http/session.py::_request`, pass the actual method and body.
- **Tests (test_http_archive.py):** same URL, different bodies → different keys; same method+url+body →
  identical key (idempotent overwrite); GET vs POST same URL → different keys.
- **Acceptance:** POST-body collisions are impossible once archiving is live.

---

#### F3. Session-expiry detection must catch 401 and followed login redirects — **P0**

- **Files:** `whakoom_scraper/scrapers/resolve.py` (detection moves to `http/resolve.py` per F2; keep the
  logic identical), `whakoom_scraper/tests/test_scrapers_resolve.py`
- **Problem:** `_raise_if_login_expired` only raises on `3xx` **and** `Location` containing `/login`. It
  misses: `401`, redirects that the client follows internally (final `200` login page), and a
  already-followed `302 → /login`.
- **Change:** raise `SessionExpiredError` when **any** of:
  1. `response.status_code == 401`;
  2. pre-follow `3xx` with `Location` containing `LOGIN_PATH`;
  3. post-follow final `response.url` contains `/login` (or the 200 body carries a login signature such as
     an `<input name="login">`).
- **Tests:** `test_resolve_401_raises_session_expired`; `test_resolve_followed_login_redirect_raises`
  (client follows 302 → 200 login page; final-URL check fires).
- **Acceptance:** an expired session aborts Stage 3 with exit code `3`; a login page is never mis-parsed.

---

#### F4. QuickView name extraction must read nested text — **P1**

- **Files:** `whakoom_scraper/scrapers/resolve.py` (`_name_from_quickview`),
  `whakoom_scraper/tests/test_scrapers_resolve.py`
- **Problem:** `.css('::text').get()` returns only **direct** text; when the series title lives inside a
  nested `<span>` the name comes back `None` and the stub is created without a name unnecessarily.
- **Change:** join all descendant text:
  `" ".join(anchor.css("::text").getall()).strip()`, return `None` when empty.
- **Tests:** anchor with `<a ...><span>Rosen</span> Blood</a>` → name `"Rosen Blood"`.
- **Acceptance:** names with child spans are captured.

---

#### F2. Split resolver I/O from pure parsing — **P1**

- **Files:** `whakoom_scraper/scrapers/resolve.py` (edit), new `whakoom_scraper/http/resolve.py`,
  `whakoom_scraper/tests/test_scrapers_resolve.py` (edit), new `whakoom_scraper/tests/test_http_resolve.py`
- **Problem:** `scrapers/resolve.py` imports `httpx` and `WhakoomSession` and performs network I/O. The
  scraper package contract (AGENTS.md S5/S6, V2.md) is **pure parsing**; network calls belong to `http/`.
- **Change:**
  1. `scrapers/resolve.py` keeps **only pure functions**, no `httpx`/`WhakoomSession` imports:
     `parse_quickview(text: str) -> SeriesRef | None`, `parse_volume_page(text: str) -> SeriesRef | None`,
     `_ediciones_ref`, `_name_from_quickview`.
  2. New `http/resolve.py` owns `resolve_series_id(session, volume_slug) -> SeriesRef | None` (QuickView
     POST → redirect fallback GET → parent-link parse), plus `SessionExpiredError` and
     `_raise_if_login_expired`. It imports the pure parsers.
  3. Move/duplicate the 5 resolver tests accordingly (pure-parser tests stay in
     `test_scrapers_resolve.py`; HTTP orchestration + expiry tests move to `test_http_resolve.py`).
- **Acceptance:** `rg "import httpx|WhakoomSession" whakoom_scraper/scrapers/` → no matches; parsing is
  unit-testable from fixture text alone.

---

#### H1. Config validation (strict bools, numeric bounds, cookie path) — **P1**

- **Files:** `whakoom_scraper/config.py`, `whakoom_scraper/tests/test_phase0_smoke.py`
- **Problem:** `WK_SAVE_RAW=yes` silently becomes `False` (`== '1'` test); `delay_seconds`/`jitter`/
  `max_retries` accept nonsense (negatives); `WHAKOOM_COOKIE_FILE` relative paths resolve against CWD
  instead of `PROJECT_ROOT`.
- **Change:**
  1. Add `_env_bool(value, name)` accepting `1/true/yes/0/false/no` (case-insensitive), else
     `ValueError` naming the variable.
  2. Use it for `save_raw` and `allow_gated_resolution`.
  3. Validate `delay_seconds > 0`, `jitter_seconds >= 0`, `max_retries >= 0` → `ValueError` otherwise.
  4. Resolve `cookie_file` through the existing `_path()` helper when relative.
- **Tests:** invalid bool raises; negative delay raises; relative cookie file resolves to `PROJECT_ROOT`;
  existing defaults/from-env tests stay green.
- **Acceptance:** any invalid env value fails fast with a named error.

---

#### H2. robots.txt fetch must go through the session — **P1**

- **Files:** `whakoom_scraper/http/policy.py` (`from_client`), `whakoom_scraper/tests/test_http_policy.py`
- **Problem:** `from_client` calls `client.get('/robots.txt')` directly, bypassing `WhakoomSession`
  politeness delay and retries.
- **Change:** change `from_client` to accept the `WhakoomSession` (or a fetch callable) so the robots fetch
  travels the same delay/retry path as every other request.
- **Tests:** MockTransport test asserting the robots request is issued once through the session wrapper
  (retry/delay path) and its content feeds `RobotsPolicy`.
- **Acceptance:** no policy fetch bypasses the session.

---

### S1.3 — Docs & tooling

#### I1. Unimplemented CLI stages must not exit 0 — **P1**

- **Files:** `whakoom_scraper/cli.py`, `whakoom_scraper/tests/test_phase0_smoke.py`
- **Problem:** every `_not_implemented` command prints the stub message but `main()` returns **0** — a
  script/CI run of `wk lists` looks successful when nothing happened.
- **Change:** `_not_implemented` returns exit code **1** (stage failure) once S1.1/S1.2 are merged and
  stages still stub. Keep the message.
- **Tests:** `test_stub_command_exits_nonzero` — invoking any unimplemented subcommand returns `1`.
- **Acceptance:** a stub can never masquerade as a completed stage.

---

#### I2. ADR-0010 — typer + rich CLI (keep, document the drift)

- **Files:** new `docs/adr/0010-typer-rich-cli.md`, `V2.md` (§561), `docs/adr/README.md`
- **Context:** `cli.py` uses `typer.Typer` + rich markup; V2.md §561 says "Stdlib argparse". Owner decided
  typer stays.
- **ADR-0010 content:** Status Accepted; supersedes the V2.md CLI wording (not an ADR); Context (drift);
  Decision (typer + rich for the `wk` CLI; argparse claim in V2.md retired); Consequences (7 commands,
  grouped options via `Annotated[...] typer.Option`, `CliRunner` in tests). Update V2.md §561 to reference
  ADR-0010. Add row to `docs/adr/README.md`.
- **Acceptance:** the CLI choice has a single written authority; V2.md no longer contradicts it.

---

#### I3. Python 3.13-only (owner-first; other interpreters OOS)

- **Files:** `pyproject.toml`, new `docs/adr/0011-python-313-only.md`, `docs/adr/README.md`
- **Change:**
  1. `pyproject.toml`: `requires-python = ">=3.13"`; drop the `Python :: 3.12` classifier (keep 3.13);
     ruff/mypy already target `py313`/3.13.
  2. **ADR-0011 — Python 3.13-only runtime:** Status Accepted; **Supersedes:** ADR-0004 *on the
     `requires-python >= 3.12` point only*; Context: owner-first fit, single toolchain, no cross-version
     matrix; Decision: `>=3.13`, other Python versions OOS; Consequences: cleaner mypy/ruff config, cannot
     install on 3.12; note the supersession scope explicitly so ADR-0004's uv/pinning content stays valid.
  3. Add row to `docs/adr/README.md`.
- **Acceptance:** `uv run python --version` is 3.13; `requires-python` and classifiers agree; ADR trail is
  coherent (0004 remains valid except the version floor).

---

#### J1. Phase numbering mapping (phases.md P# ↔ V2.md roadmap Phase N) — **P2**

- **Files:** `phases.md` (header), `V2.md` (§17)
- **Problem:** `phases.md` uses P0–P8 (implementation workstreams) while V2.md §17 uses Phase 0–5
  (roadmap); "Phase 2 completed" is ambiguous.
- **Change:** add a short mapping table to both docs:
  | V2.md roadmap | phases.md workstream |
  |---|---|
  | Phase 0 Scaffolding | P0 (scaffolding), P1 (store), P2 (http), P3 (parsers) |
  | Phase 1 Public lists | P4 (stages 1–2) |
  | Phase 2 Resolution | P5 (stage 3 resolve) |
  | Phase 3 Series | P6 (stage 4 series) |
  | Phase 4 Validation & analytics | P7 |
  | Phase 5 Polish | P8 |
  Note explicitly that "Phase 2 completed" = phases.md **P2** (http layer).
- **Acceptance:** a reader can disambiguate any "Phase N" reference.

---

#### J3. Fix test commands in phases.md — **P2**

- **Files:** `phases.md`
- **Problem:** commands like `uv run pytest tests/test_store*.py` (~:154), `tests/test_http*.py` (~:187),
  `test_scrapers*.py` (~:258) point at a nonexistent root `tests/`; pyproject `testpaths` is
  `whakoom_scraper/tests`.
- **Change:** rewrite every pytest path to `whakoom_scraper/tests/...` in phases.md.
- **Acceptance:** every command in phases.md runs from a fresh checkout.

---

## 3. Gates (run after each workstream, and at the end)

```bash
uv run pytest
uv run ruff check .
uv run mypy .
uv run bandit -c pyproject.toml -r whakoom_scraper/
uv run pre-commit run --all-files
```

Expected: pytest count grows from the 51 baseline (new tests listed per item); no lint/type/security
findings.

Extra structural checks:

```bash
# no network imports left in the scraper package
rg "import httpx|WhakoomSession" whakoom_scraper/scrapers/ || echo "clean"
```

## 4. Definition of done for PRE_PHASE3

1. All P0 items merged first, then P1, then P2 (S1.3 may proceed in parallel once P0 is green).
2. Every item above has its tests in the specified file and the full gate list is green.
3. ADR-0010 and ADR-0011 written, accepted, indexed in `docs/adr/README.md`.
4. `TECH_DEBT.md` updated to mark R1/R2/R5 as addressed by this plan's A1/E4/B1 items (see TECH_DEBT §"Deferred from PRE_PHASE3 review").
5. Phase 3 (parsers + fixtures) starts only after P0 items and D1 are green.

## 5. Explicitly NOT in this plan (deferred — see TECH_DEBT.md)

- C1 (remove surrogate ids from domain models) — opportunistic, not a Phase-3 gate.
- C3 (surface `publisher_id`/surrogate ids in row mappers) — Phase 6.
- G1 (publisher identity by whakoom_id) — when Stage 4 links publishers.
- G2 (series-child reconciliation for volumes/observations) — Phase 6.
- J2 (ADR-0003 vs schema enrichment contradiction) — resolved with the `enrich` stage.
- J4 (ADR-threshold policy) — forward-looking convention.
- Linter consolidation, ORM/async/DI/browser/workflow-engine/event-bus — owner-declined or rejected.
