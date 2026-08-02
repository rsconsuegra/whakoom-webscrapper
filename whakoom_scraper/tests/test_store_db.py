"""Tests for the store core: query loader, connection pragmas, migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from whakoom_scraper.store.db import Database, load_queries

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
