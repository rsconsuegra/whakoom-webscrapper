"""Manages database connections, named queries, and migrations."""

import os
import re
import sqlite3
from typing import Any


class SQLManager:
    """Manages database connections, named queries, and migrations."""

    def __init__(
        self,
        db_path: str,
        sql_dir: str | None = None,
        migrations_dir: str | None = None,
    ):
        """Initialize the SQLManager with the provided database path and directories.

        Args:
            db_path (str): The path to the SQLite database file.
            sql_dir (str): The directory containing the SQL files with named queries.
            migrations_dir (str): The directory containing migration SQL files.

        Attributes:
            db_path (str): The path to the SQLite database file.
            sql_dir (str): The directory containing the SQL files with named queries.
            migrations_dir (str): The directory containing migration SQL files.
            queries (dict): A dictionary containing the named queries loaded from the SQL files.
        """
        self.db_path = db_path
        self.sql_dir = sql_dir
        self.migrations_dir = migrations_dir
        self.queries = {} if sql_dir is None else self._load_queries_from_files()

    def _load_queries_from_files(self) -> dict[str, str]:
        """Load named queries from SQL files in the sql_dir.

        Returns:
            dict: A dictionary mapping query names to SQL queries.
        """
        queries = {}
        if self.sql_dir and os.path.exists(self.sql_dir):
            for filename in os.listdir(self.sql_dir):
                if filename.endswith(".sql"):
                    file_path = os.path.join(self.sql_dir, filename)
                    with open(file_path, "r", encoding="utf-8") as file:
                        sql_content = file.read()
                    named_queries = self._parse_named_queries(sql_content)
                    queries.update(named_queries)
        return queries

    def _parse_named_queries(self, sql_content: str) -> dict[str, str]:
        """Parse named queries from SQL content.

        Args:
            sql_content (str): The SQL content containing named queries.

        Returns:
            dict: A dictionary mapping query names to SQL queries.
        """
        queries = {}
        pattern = r"#\s*(\w+)\s*\n(.*?)(?=\n#|$)"
        matches = re.findall(pattern, sql_content, re.DOTALL)
        for name, query in matches:
            queries[name.strip().upper()] = query.strip()
        return queries

    def _sanitize_query(self, query: str) -> str:
        """Sanitize a SQL query (placeholder for future sanitization logic).

        Args:
            query (str): The SQL query to sanitize.

        Returns:
            str: The sanitized SQL query.
        """
        return query

    def format_query(self, query: str, params: dict[str, Any]) -> str:
        """Format a query with the provided parameters.

        Args:
            query (str): The SQL query with placeholders.
            params (dict): The parameters to substitute into the query.

        Returns:
            str: The formatted SQL query.
        """
        sanitized_query = self._sanitize_query(query)
        return sanitized_query.format(**params)

    def execute_query(self, query_name: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        """Execute a named query with optional parameters.

        Args:
            query_name (str): The name of the query to execute.
            params (dict, optional): The parameters to substitute into the query.

        Returns:
            list: The query results.

        Raises:
            ValueError: If the query name is not found.
        """
        query = self.queries.get(query_name.upper())
        if not query:
            raise ValueError(f"Query '{query_name}' not found.")
        if params:
            formatted_query = self.format_query(query, params)
        else:
            formatted_query = query
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(formatted_query)
            conn.commit()
            return cursor.fetchall()

    def execute_parametrized_query(self, query_name: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        """Execute a named query with positional parameters.

        Args:
            query_name (str): Name of query in the SQL files.
            params (tuple): Tuple of parameters for the query.

        Returns:
            Query results.

        Raises:
            ValueError: If the query name is not found.
        """
        query = self.queries.get(query_name.upper())
        if not query:
            raise ValueError(f"Query '{query_name}' not found.")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.fetchall()

    def create_migrations_table(self) -> None:
        """Create the migrations table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

    def get_applied_migrations(self) -> list[dict[str, Any]]:
        """Get all applied migrations.

        Returns:
            list: A list of dictionaries containing migration information.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM migrations ORDER BY version")
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_migrations(self) -> list[dict[str, str]]:
        """Get all pending migrations (not yet applied).

        Returns:
            list: A list of dictionaries containing migration information.
        """
        if not self.migrations_dir or not os.path.exists(self.migrations_dir):
            return []

        applied = {m["version"] for m in self.get_applied_migrations()}
        pending = []

        for filename in sorted(os.listdir(self.migrations_dir)):
            if filename.endswith(".sql"):
                file_path = os.path.join(self.migrations_dir, filename)
                with open(file_path, "r", encoding="utf-8") as file:
                    sql_content = file.read()

                version_match = re.search(r"#\s*MIGRATION_VERSION\s*\n(\d+)", sql_content)
                name_match = re.search(r"#\s*MIGRATION_NAME\s*\n(.+)", sql_content)

                if version_match and name_match:
                    version = version_match.group(1).strip()
                    name = name_match.group(1).strip()

                    if version not in applied:
                        pending.append(
                            {
                                "version": version,
                                "name": name,
                                "file_path": file_path,
                            }
                        )

        return pending

    def apply_migrations(self) -> None:
        """Apply all pending migrations in order."""
        self.create_migrations_table()
        pending = self.get_pending_migrations()

        for migration in pending:
            version = migration["version"]
            file_path = migration["file_path"]

            with open(file_path, "r", encoding="utf-8") as file:
                sql_content = file.read()

            up_match = re.search(r"#\s*UP\s*\n(.*?)(?=\n#.*DOWN|$)", sql_content, re.DOTALL)
            if up_match:
                up_script = up_match.group(1).strip()

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.executescript(up_script)
                        conn.commit()
                    except sqlite3.Error as e:
                        conn.rollback()
                        raise RuntimeError(f"Migration {version} failed: {e}") from e

    def log_scraping_operation(
        self,
        scrapper_name: str,
        operation_type: str,
        entity_id: int,
        status: str,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Log a scraping operation to the scraping_log table.

        Args:
            scrapper_name (str): Name of the scrapper.
            operation_type (str): Type of operation (e.g., 'list', 'title', 'volume').
            entity_id (int): ID of the entity being processed.
            status (str): Status of the operation ('started', 'success', 'failed').
            error_message (str, optional): Error message if the operation failed.
            duration_ms (int, optional): Duration of the operation in milliseconds.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scraping_log
                (scrapper_name, operation_type, entity_id, status, error_message, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scrapper_name,
                    operation_type,
                    entity_id,
                    status,
                    error_message,
                    duration_ms,
                ),
            )
            conn.commit()
