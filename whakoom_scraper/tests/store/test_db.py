"""Tests for the store core: query loader, connection pragmas, migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from whakoom_scraper.store.db import Database, _split_statements, load_queries

SAMPLE_SQL = """\
-- header comment ignored

-- name: select_thing
SELECT id FROM things WHERE name = ?;

-- name: update_thing
UPDATE things SET value = ? WHERE id = ?;
"""


def _write_queries(tmp_path: Path) -> Path:
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "things.sql").write_text(SAMPLE_SQL, encoding="utf-8")
    return queries_dir


def test_load_queries_parses_named_markers(tmp_path: Path) -> None:
    """Named queries are keyed by (file stem, name) with trimmed bodies."""
    queries_dir = _write_queries(tmp_path)
    queries = load_queries(queries_dir)
    assert ("things", "select_thing") in queries
    assert ("things", "update_thing") in queries
    assert queries[("things", "select_thing")] == "SELECT id FROM things WHERE name = ?;"
    assert queries[("things", "update_thing")] == "UPDATE things SET value = ? WHERE id = ?;"


def test_load_queries_rejects_empty_body(tmp_path: Path) -> None:
    """A marker with no SQL body raises ValueError."""
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "broken.sql").write_text("-- name: empty\n\n-- name: next\nSELECT 1;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty query 'empty'"):
        load_queries(queries_dir)


def test_database_applies_migrations_once(tmp_path: Path) -> None:
    """The initial schema applies on first open and is a no-op on reopen."""
    db_path = tmp_path / "whakoom.db"
    first = Database(db_path)
    assert not first.fetchall("lists", "get_lists")
    applied = first.connection.execute("SELECT COUNT(*) AS n FROM _migrations").fetchone()
    assert applied["n"] >= 1
    first.close()

    second = Database(db_path)
    applied_again = second.connection.execute("SELECT COUNT(*) AS n FROM _migrations").fetchone()
    assert applied_again["n"] >= 1
    tables = {row[0] for row in second.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    expected = {
        "_migrations",
        "scrape_runs",
        "lists",
        "publishers",
        "authors",
        "series",
        "series_observations",
        "volumes",
        "series_authors",
        "list_items",
    }
    assert expected <= tables
    second.close()


def test_database_enables_pragmas(tmp_path: Path) -> None:
    """Foreign keys are enforced and journal mode is WAL."""
    db = Database(tmp_path / "whakoom.db")
    fk = db.connection.execute("PRAGMA foreign_keys").fetchone()
    assert fk[0] == 1
    wal = db.connection.execute("PRAGMA journal_mode").fetchone()
    assert wal[0].lower() == "wal"
    db.close()


def test_duplicate_query_name_raises(tmp_path: Path) -> None:
    """Duplicate markers within one file raise ValueError."""
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "dup.sql").write_text("-- name: q\nSELECT 1;\n-- name: q\nSELECT 2;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate query 'q'"):
        load_queries(queries_dir)


def test_missing_query_raises_keyerror(tmp_path: Path) -> None:
    """Looking up an unknown named query raises KeyError."""
    db = Database(tmp_path / "whakoom.db")
    with pytest.raises(KeyError):
        db.sql("lists", "does_not_exist")
    db.close()


def test_connection_is_sqlite3(tmp_path: Path) -> None:
    """The exposed connection is a real sqlite3.Connection."""
    db = Database(tmp_path / "whakoom.db")
    assert isinstance(db.connection, sqlite3.Connection)
    db.close()


def test_non_empty_file_without_markers_raises(tmp_path: Path) -> None:
    """A non-empty .sql file with no -- name: markers raises ValueError."""
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "lonely.sql").write_text("SELECT 1; -- no name marker here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No query markers in non-empty file"):
        load_queries(queries_dir)


def test_split_statements_skips_comment_only_fragments() -> None:
    """The splitter yields executable statements and drops comment blocks."""
    text = "-- header comment\n\nCREATE TABLE t (a INTEGER);\n-- trailing comment\nCREATE INDEX i ON t (a);\n-- tail only\n"
    statements = list(_split_statements(text))
    assert len(statements) == 2
    assert "CREATE TABLE t" in statements[0]
    assert "CREATE INDEX i" in statements[1]


def test_migration_that_fails_leaves_no_partial_schema(tmp_path: Path) -> None:
    """A migration that fails mid-script rolls back fully."""
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    empty_migrations = tmp_path / "empty_migrations"
    empty_migrations.mkdir()
    queries_dir = tmp_path / "queries"
    queries_dir.mkdir()
    (queries_dir / "noop.sql").write_text("-- name: noop\nSELECT 1;\n", encoding="utf-8")
    (migrations_dir / "001_good.sql").write_text("CREATE TABLE t_good (a INTEGER);\n", encoding="utf-8")
    bad_sql = "CREATE TABLE t_bad (a INTEGER);\nCREATE TABLE t_bad2 (b INTEGER);\nINSERT INTO no_such_table (c) VALUES (1);\n"
    (migrations_dir / "002_bad.sql").write_text(bad_sql, encoding="utf-8")
    db_path = tmp_path / "whakoom.db"

    with pytest.raises(sqlite3.OperationalError):
        Database(db_path, queries_dir=queries_dir, migrations_dir=migrations_dir)

    inspected = Database(db_path, queries_dir=queries_dir, migrations_dir=empty_migrations)
    tables = {row[0] for row in inspected.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "t_bad" not in tables
    assert "t_bad2" not in tables
    assert "t_good" in tables
    applied = {row[0] for row in inspected.connection.execute("SELECT filename FROM _migrations")}
    assert applied == {"001_good.sql"}
    inspected.close()

    (migrations_dir / "002_bad.sql").unlink()
    fixed = Database(db_path, queries_dir=queries_dir, migrations_dir=migrations_dir)
    applied_after_fix = {row[0] for row in fixed.connection.execute("SELECT filename FROM _migrations")}
    assert applied_after_fix == {"001_good.sql"}
    fixed.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    """A clean transaction() exit commits the writes."""
    db = Database(tmp_path / "whakoom.db")
    db.connection.execute("CREATE TABLE t (n INTEGER)")
    with db.transaction():
        db.connection.execute("INSERT INTO t (n) VALUES (1)")
    row = db.connection.execute("SELECT COUNT(*) AS c FROM t").fetchone()
    assert row["c"] == 1
    db.close()


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    """An exception inside transaction() rolls back the writes."""
    db = Database(tmp_path / "whakoom.db")
    db.connection.execute("CREATE TABLE t (n INTEGER)")

    class BoomError(RuntimeError):
        """Local sentinel error used to trigger the rollback path."""

    with pytest.raises(BoomError):
        with db.transaction():
            db.connection.execute("INSERT INTO t (n) VALUES (1)")
            raise BoomError("rollback please")

    row = db.connection.execute("SELECT COUNT(*) AS c FROM t").fetchone()
    assert row["c"] == 0
    db.close()


def test_transaction_nesting_raises(tmp_path: Path) -> None:
    """Nested transaction() use raises RuntimeError."""
    db = Database(tmp_path / "whakoom.db")
    db.connection.execute("CREATE TABLE t (n INTEGER)")
    with pytest.raises(RuntimeError, match="Nested transactions"):
        with db.transaction():
            with db.transaction():
                pass
    db.close()


def test_d1_indexes_exist(tmp_path: Path) -> None:
    """The D1 schema indexes are present on series_observations and volumes."""
    db = Database(tmp_path / "whakoom.db")

    def index_names(table: str) -> set[str]:
        """Return the set of index names for a table via PRAGMA index_list."""
        return {str(row[1]) for row in db.connection.execute(f"PRAGMA index_list('{table}')")}

    assert "idx_observations_series" in index_names("series_observations")
    assert "idx_volumes_series" in index_names("volumes")
    db.close()
