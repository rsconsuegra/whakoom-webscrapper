"""Stage 6: DuckDB analytics — list enrichment, views, CSV exports.

Gates on the validation stage: ``wk analyze`` refuses to run when the last
``validate`` run did not complete, unless ``force`` is passed (V2 §12).

The enrichment step classifies every list whose ``list_type`` is null (V2 §14
"canonical name joins in post-enrichment") and writes ``list_type`` plus
``canonical_name`` before any view is built, so the year/magazine views have
their filter columns.

Views persist in ``{db_path}.duckdb`` (e.g. ``data/whakoom.duckdb``) for the
``analysis/explore.ipynb`` notebook; CSV exports land in
``{db_path.parent}/exports/``. Because the views reference the session-scoped
``wh`` catalog, any new session (notebook included) must re-ATTACH the sqlite
file read-only before querying them.

Exit codes:
    * 0 — views built and floors satisfied
    * 1 — the stage failed (duckdb/sqlite error or sanity floor miss)
    * 2 — refused: last validation did not pass and ``force`` not set
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

from whakoom_scraper.analysis.classification import classify_list_name
from whakoom_scraper.config import PROJECT_ROOT, Settings
from whakoom_scraper.pipeline._runtime import owned_db
from whakoom_scraper.store.db import Database, _split_statements
from whakoom_scraper.store.repositories import (
    close_run,
    create_run,
    get_last_run_status,
    get_unclassified_lists,
    set_list_classification,
)

log = logging.getLogger(__name__)

ANALYZE_OK = 0
ANALYZE_FAILED = 1
ANALYZE_REFUSED = 2

VIEWS_SQL = PROJECT_ROOT / "analysis" / "views.sql"

#: Sanity floors (phases.md P7 "Done when", recalibrated 2026-08-16 with owner
#: approval: the complete dataset holds ~600 year-list titles across 8 year
#: lists, below the original 1,000 estimate; 500 keeps drift protection).
FLOOR_TITLES_BY_YEAR = 500
FLOOR_TITLES_BY_MAGAZINE = 100

#: SQLite tables exported verbatim to CSV (phases.md P7).
EXPORT_TABLES = ("lists", "list_items", "series", "volumes", "series_observations")


def run_analyze(settings: Settings, *, force: bool = False, db: Database | None = None) -> int:
    """Run Stage 6: build DuckDB views and export CSVs.

    Owns (and closes) a :class:`Database` when one is not supplied by the
    caller, so production CLI use needs no extra plumbing while tests inject
    a pre-built instance.

    Args:
        settings: Runtime settings (db path, exports location).
        force: When True, run even if the last validation failed.
        db: Optional pre-opened database (tests); opened and closed when None.

    Returns:
        Process exit code (0 ok, 1 failure, 2 validation-gate refusal).
    """
    with owned_db(settings, db) as store:
        return _run_analyze(store, settings, force)


def _run_analyze(db: Database, settings: Settings, force: bool) -> int:
    """Enrich lists, build views, export CSVs, and record the run.

    Args:
        db: Open database handle.
        settings: Runtime settings (db path, exports location).
        force: Whether a failed validation is overridden.

    Returns:
        Process exit code (0 ok, 1 failure, 2 validation-gate refusal).
    """
    last_validate = get_last_run_status(db, "validate")
    if last_validate != "completed":
        if not force:
            log.error("refusing to analyze: last validate run status=%r (pass --force to override)", last_validate)
            return ANALYZE_REFUSED
        log.warning("analyzing despite validate status=%r (--force)", last_validate)

    run_id = create_run(db, "analyze")
    db.commit()

    try:
        enriched = _enrich_lists(db)
        db.commit()

        duckdb_path = settings.db_path.with_suffix(".duckdb")
        exports_dir = settings.db_path.parent / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        connection = duckdb.connect(str(duckdb_path))
        try:
            _load_sqlite_extension(connection)
            _attach_sqlite(connection, settings.db_path)
            for statement in _split_statements(VIEWS_SQL.read_text(encoding="utf-8")):
                connection.execute(statement)
            exported = _export_tables(connection, exports_dir)
            counts = {
                "v_titles_by_year": _count_view(connection, "v_titles_by_year"),
                "v_titles_by_magazine": _count_view(connection, "v_titles_by_magazine"),
            }
        finally:
            connection.close()

        floor_failures = _check_floors(counts)
        _render_report(enriched, counts, exported)
        _close_analyze_run(db, run_id, enriched, counts, exported, floor_failures)
        if floor_failures:
            log.error("analyze sanity floors not met: %s", ", ".join(floor_failures))
            return ANALYZE_FAILED
        log.info("analyze: %d lists enriched, %d CSV exports, views built", enriched, len(exported))
        return ANALYZE_OK
    except (duckdb.Error, sqlite3.Error, ValueError, OSError) as exc:
        close_run(db, run_id, "failed", items_processed=0, items_failed=0, notes=f"analyze error: {exc}")
        db.commit()
        log.error("analyze stage failed: %s", exc)
        return ANALYZE_FAILED


def _enrich_lists(db: Database) -> int:
    """Classify every unclassified list and persist type + canonical name.

    Args:
        db: Open database handle.

    Returns:
        The number of lists classified by this call.
    """
    enriched = 0
    for list_row_id, name in get_unclassified_lists(db):
        list_type, canonical_name = classify_list_name(name)
        set_list_classification(db, list_row_id, list_type, canonical_name)
        enriched += 1
    return enriched


def _load_sqlite_extension(connection: duckdb.DuckDBPyConnection) -> None:
    """Load DuckDB's sqlite extension, installing it when not bundled.

    Args:
        connection: The DuckDB connection to configure.

    Raises:
        duckdb.Error: When the extension cannot be loaded at all.
    """
    try:
        connection.execute("LOAD sqlite")
    except duckdb.Error:
        connection.execute("INSTALL sqlite")
        connection.execute("LOAD sqlite")


def _attach_sqlite(connection: duckdb.DuckDBPyConnection, db_path: Path) -> None:
    """Attach the SQLite database read-only for querying.

    Args:
        connection: The DuckDB connection.
        db_path: Path of the SQLite database file.

    Raises:
        duckdb.Error: When the attach fails.
    """
    connection.execute(f"ATTACH '{_sql_path(db_path)}' AS wh (TYPE sqlite, READ_ONLY)")


def _sql_path(path: Path) -> str:
    """Render a filesystem path as a safely quoted SQL string literal body.

    Args:
        path: The filesystem path.

    Returns:
        The path with any single quotes doubled, for use inside ``'...'``.
    """
    return path.as_posix().replace("'", "''")


def _fetch_count(connection: duckdb.DuckDBPyConnection, target: str) -> int:
    """Count the rows of a table or view.

    Args:
        connection: Attached DuckDB connection.
        target: A fully-qualified table or view name (e.g. ``wh.lists``).

    Returns:
        The row count.

    Raises:
        ValueError: When the count query unexpectedly returns no row.
        duckdb.Error: When the target does not exist.
    """
    row = connection.table(target).count("*").fetchone()
    if row is None:
        raise ValueError(f"COUNT(*) over {target} returned no row")
    return int(row[0])


def _export_tables(connection: duckdb.DuckDBPyConnection, exports_dir: Path) -> dict[str, int]:
    """COPY every export table to CSV and return the row counts written.

    Args:
        connection: Attached DuckDB connection.
        exports_dir: Destination directory for ``{table}.csv`` files.

    Returns:
        Mapping of table name to exported row count.

    Raises:
        duckdb.Error: When any COPY fails.
    """
    exported: dict[str, int] = {}
    for table in EXPORT_TABLES:
        destination = (exports_dir / f"{table}.csv").resolve()
        connection.execute(f"COPY wh.{table} TO '{_sql_path(destination)}' (HEADER, DELIMITER ',')")
        exported[table] = _fetch_count(connection, f"wh.{table}")
    return exported


def _count_view(connection: duckdb.DuckDBPyConnection, view: str) -> int:
    """Count the rows of a built view.

    Args:
        connection: Attached DuckDB connection.
        view: View name (must exist).

    Returns:
        The view's row count.

    Raises:
        ValueError: When the count query unexpectedly returns no row.
        duckdb.Error: When the view does not exist.
    """
    return _fetch_count(connection, view)


def _check_floors(counts: dict[str, int]) -> list[str]:
    """Check view row counts against the P7 sanity floors.

    Args:
        counts: View name to row count.

    Returns:
        Human-readable failure descriptions; empty when all floors pass.
    """
    floors: dict[str, int] = {
        "v_titles_by_year": FLOOR_TITLES_BY_YEAR,
        "v_titles_by_magazine": FLOOR_TITLES_BY_MAGAZINE,
    }
    return [
        f"{view} has {counts[view]} rows, floor is {floor}" for view, floor in floors.items() if counts.get(view, 0) < floor
    ]


def _close_analyze_run(
    db: Database,
    run_id: int,
    enriched: int,
    counts: dict[str, int],
    exported: dict[str, int],
    floor_failures: list[str],
) -> None:
    """Close the analyze run record with its outcome.

    Args:
        db: Open database handle.
        run_id: The analyze run's id.
        enriched: Number of lists classified during enrichment.
        counts: View name to row count.
        exported: Exported table name to row count.
        floor_failures: Floor failure descriptions (empty when all passed).
    """
    notes = "; ".join(
        [
            f"enriched={enriched}",
            f"v_titles_by_year={counts.get('v_titles_by_year', 0)}",
            f"v_titles_by_magazine={counts.get('v_titles_by_magazine', 0)}",
            f"exports={len(exported)}",
            *(f"floor fail: {failure}" for failure in floor_failures),
        ]
    )
    with db.transaction():
        close_run(
            db,
            run_id,
            "failed" if floor_failures else "completed",
            items_processed=len(exported),
            items_failed=len(floor_failures),
            notes=notes,
        )


def _render_report(enriched: int, counts: dict[str, int], exported: dict[str, int]) -> None:
    """Print the analyze summary as a rich table.

    Args:
        enriched: Number of lists classified during enrichment.
        counts: View name to row count.
        exported: Exported table name to row count.
    """
    table = Table(title="wk analyze — views & exports")
    table.add_column("Artifact")
    table.add_column("Rows", justify="right")
    table.add_row("lists enriched", str(enriched))
    for view, row_count in sorted(counts.items()):
        table.add_row(view, str(row_count))
    for name, row_count in sorted(exported.items()):
        table.add_row(f"export: {name}.csv", str(row_count))
    Console().print(table)
