"""SQLite persistence core: connection factory, named-query loader, migrations.

Design follows V2 §8. All SQL lives in ``.sql`` files under
``store/queries/`` (referenced by ``-- name:`` markers) and ``store/migrations/``
(applied in filename order and tracked in ``_migrations``). No raw SQL is ever
written in application code, and query parameters always use ``?`` placeholders.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from whakoom_scraper.config import PROJECT_ROOT

NAME_MARKER = re.compile(r"^-- name:\s*(\S+)\s*$", re.MULTILINE)
QUERIES_DIR = PROJECT_ROOT / "whakoom_scraper" / "store" / "queries"
MIGRATIONS_DIR = PROJECT_ROOT / "whakoom_scraper" / "store" / "migrations"


def _is_blank_or_comment(text: str) -> bool:
    """Check whether a SQL fragment carries no executable statement.

    Args:
        text: A SQL fragment produced by the statement splitter.

    Returns:
        True if every line is empty or a ``--`` comment.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def _split_statements(text: str) -> Iterator[str]:
    """Split a SQL script into statements using sqlite's own parser.

    Walks the script char-by-char; each time
    :func:`sqlite3.complete_statement` reports a complete statement, the
    accumulated buffer is flushed. Comment-only or blank fragments are skipped,
    and string literals are never split (``complete_statement`` tracks quotes).
    Migration files are owned by this repo, so the splitter is defensive.

    Args:
        text: A full SQL migration script.

    Yields:
        Each non-empty, non-comment-only statement.
    """
    buffer = ""
    for char in text:
        buffer += char
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement and not _is_blank_or_comment(statement):
                yield statement
    trailer = buffer.strip()
    if trailer and not _is_blank_or_comment(trailer):
        yield trailer


def load_queries(queries_dir: Path) -> dict[tuple[str, str], str]:
    """Load every named query from ``*.sql`` files in a directory.

    Args:
        queries_dir: Directory containing query files.

    Returns:
        Mapping of ``(filename_stem, query_name)`` to the SQL statement.

    Raises:
        ValueError: If a query marker has an empty body, a duplicated name,
            or a non-empty ``.sql`` file yields zero ``-- name:`` markers.
    """
    queries: dict[tuple[str, str], str] = {}
    for path in sorted(queries_dir.glob("*.sql")):
        content = path.read_text(encoding="utf-8")
        markers = list(NAME_MARKER.finditer(content))
        if content.strip() and not markers:
            raise ValueError(f"No query markers in non-empty file {path.name}")
        for index, marker in enumerate(markers):
            name = marker.group(1)
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(content)
            sql = content[start:end].strip()
            if not sql:
                raise ValueError(f"Empty query '{name}' in {path.name}")
            key = (path.stem, name)
            if key in queries:
                raise ValueError(f"Duplicate query '{name}' in {path.name}")
            queries[key] = sql
    return queries


class Database:
    """Owns a sqlite3 connection plus the named queries and migrations."""

    def __init__(
        self,
        db_path: Path,
        *,
        queries_dir: Path = QUERIES_DIR,
        migrations_dir: Path = MIGRATIONS_DIR,
    ) -> None:
        """Open the database, set pragmas, and apply pending migrations.

        Args:
            db_path: Path to the SQLite file (parent directory is created).
            queries_dir: Directory with named-query ``*.sql`` files.
            migrations_dir: Directory with ordered ``NNN_*.sql`` migrations.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        try:
            self._queries = load_queries(queries_dir)
            self._apply_migrations(migrations_dir)
        except BaseException:
            self._conn.close()
            raise

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying sqlite3 connection."""
        return self._conn

    def sql(self, query_file: str, query_name: str) -> str:
        """Look up the SQL text of a named query.

        Args:
            query_file: Query file stem (e.g. ``lists``).
            query_name: Name marker within that file.

        Returns:
            The SQL statement.

        Raises:
            KeyError: If the named query does not exist.
        """
        return self._queries[(query_file, query_name)]

    def execute(self, query_file: str, query_name: str, params: Sequence[object] = ()) -> sqlite3.Cursor:
        """Execute a named query and return its cursor.

        Args:
            query_file: Query file stem.
            query_name: Name marker within that file.
            params: Positional parameters for the statement.

        Returns:
            The resulting cursor.
        """
        return self._conn.execute(self.sql(query_file, query_name), params)

    def executemany(
        self,
        query_file: str,
        query_name: str,
        seq_of_params: Sequence[Sequence[object]],
    ) -> sqlite3.Cursor:
        """Execute a named query once per parameter set.

        Args:
            query_file: Query file stem.
            query_name: Name marker within that file.
            seq_of_params: Iterable of positional parameter sets.

        Returns:
            The resulting cursor.
        """
        return self._conn.executemany(self.sql(query_file, query_name), seq_of_params)

    def fetchone(self, query_file: str, query_name: str, params: Sequence[object] = ()) -> sqlite3.Row | None:
        """Execute a named query and return the first row.

        Args:
            query_file: Query file stem.
            query_name: Name marker within that file.
            params: Positional parameters for the statement.

        Returns:
            The first row, or ``None`` if there are no rows.
        """
        return self._conn.execute(self.sql(query_file, query_name), params).fetchone()

    def fetchall(self, query_file: str, query_name: str, params: Sequence[object] = ()) -> list[sqlite3.Row]:
        """Execute a named query and return all rows.

        Args:
            query_file: Query file stem.
            query_name: Name marker within that file.
            params: Positional parameters for the statement.

        Returns:
            All resulting rows.
        """
        return list(self._conn.execute(self.sql(query_file, query_name), params).fetchall())

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def begin(self) -> None:
        """Begin an explicit ``BEGIN IMMEDIATE`` transaction on the connection."""
        self._conn.execute("BEGIN IMMEDIATE")

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._conn.execute("ROLLBACK")

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Context-managed transaction: commit on clean exit, rollback on error.

        Yields:
            This Database handle inside an open transaction.

        Raises:
            RuntimeError: If a transaction is already open on this connection.
        """
        if self._in_transaction:
            raise RuntimeError("Nested transactions are not supported")
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        try:
            yield self
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def _apply_migrations(self, migrations_dir: Path) -> list[str]:
        """Apply pending migrations in filename order, one transaction each.

        Args:
            migrations_dir: Directory with ordered ``NNN_*.sql`` migrations.

        Returns:
            The filenames of migrations applied in this call.
        """
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "filename TEXT PRIMARY KEY,"
            "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))"
            ")"
        )
        applied = {row[0] for row in self._conn.execute("SELECT filename FROM _migrations")}
        pending = [path for path in sorted(migrations_dir.glob("*.sql")) if path.name not in applied]
        for path in pending:
            self._apply_migration_file(path)
        return [path.name for path in pending]

    def _apply_migration_file(self, path: Path) -> None:
        """Apply one migration inside its own transaction, recording it on success.

        Any failure triggers ``ROLLBACK`` and re-raise so a broken migration
        can never leave a partially-applied schema with no ``_migrations`` row.

        Args:
            path: Path to the migration ``.sql`` file.

        Raises:
            Exception: Any sqlite error is re-raised after rollback.
        """
        text = path.read_text(encoding="utf-8")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in _split_statements(text):
                self._conn.execute(statement)
            self._conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (path.name,))
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
