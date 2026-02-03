"""Manages database connections, named queries, and migrations."""

import os
import re
import sqlite3
from dataclasses import fields
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
                    with open(file_path, encoding="utf-8") as file:
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

    def execute_query(
        self, query_name: str, params: dict[str, Any] | None = None
    ) -> list[tuple[Any, ...]]:
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

    def execute_parametrized_query(
        self, query_name: str, params: tuple[Any, ...]
    ) -> list[tuple[Any, ...]]:
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
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

    def _parse_migration_filename(self, filename: str) -> tuple[str, str] | None:
        """Parse migration version and name from filename.

        Args:
            filename: Migration filename (e.g., '001_initial_schema.sql')

        Returns:
            Tuple of (version, name) or None if invalid format.

        Example:
            '001_initial_schema.sql' → ('001', 'initial_schema')
        """
        if not filename.endswith(".sql"):
            return None

        name_without_ext = filename[:-4]
        parts = name_without_ext.split("_", 1)

        if len(parts) != 2:
            return None

        version, name = parts

        if not version or not name:
            return None

        return version, name

    def get_pending_migrations(self) -> list[dict[str, str]]:
        """Get all pending migrations (not yet applied).

        Returns:
            list: A list of dictionaries containing migration information.

        Raises:
            RuntimeError: If migration filename doesn't match expected pattern.
        """
        if not self.migrations_dir or not os.path.exists(self.migrations_dir):
            return []

        applied = {m["version"] for m in self.get_applied_migrations()}
        pending = []

        for filename in sorted(os.listdir(self.migrations_dir)):
            if filename.endswith(".sql"):
                file_path = os.path.join(self.migrations_dir, filename)
                filename_metadata = self._parse_migration_filename(filename)

                if not filename_metadata:
                    raise RuntimeError(
                        f"Invalid migration filename format: {filename}. "
                        "Expected format: XXX_name.sql (e.g., 001_initial_schema.sql)"
                    )

                version, name = filename_metadata

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
            name = migration["name"]
            file_path = migration["file_path"]

            with open(file_path, encoding="utf-8") as file:
                sql_content = file.read()

            up_match = re.search(
                r"--\s*Up\s*\n(.*?)(?=\n--.*Down|$)", sql_content, re.DOTALL
            )
            if up_match:
                up_script = up_match.group(1).strip()

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.executescript(up_script)
                        cursor.execute(
                            "INSERT INTO migrations (version, name) VALUES (?, ?)",
                            (version, name),
                        )
                        conn.commit()
                    except sqlite3.Error as e:
                        conn.rollback()
                        raise RuntimeError(f"Migration {version} failed: {e}") from e

    def _execute_raw(self, query: str, params: tuple) -> None:
        """Execute raw SQL query with parameters.

        Args:
            query: The SQL query to execute.
            params: Tuple of parameters for query.

        Raises:
            sqlite3.Error: If query fails.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()

    def insert(self, model_class: type[Any], instance: Any) -> None:
        """Insert a model instance into database.

        Args:
            model_class: The dataclass model type.
            instance: The instance to insert.

        Raises:
            ValueError: If instance type doesn't match model_class or attributes missing.
            sqlite3.Error: If query fails.
        """
        if not isinstance(instance, model_class):
            raise ValueError(f"Instance must be of type {model_class.__name__}")

        table = getattr(model_class, "table_name", "")
        to_tuple_method = getattr(instance, "to_tuple", None)

        if not table:
            raise ValueError(
                f"Model {model_class.__name__} has no 'table_name' attribute"
            )
        if to_tuple_method is None:
            raise ValueError(
                f"Instance of {model_class.__name__} has no 'to_tuple()' method"
            )

        model_fields = [f.name for f in fields(model_class) if f.name != "table_name"]
        placeholders = ", ".join(["?"] * len(model_fields))
        columns = ", ".join(model_fields)

        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        params = to_tuple_method()

        self._execute_raw(query, params)

    def update(
        self, model_class: type[Any], instance: Any, id_field: str, id_value: int | str
    ) -> None:
        """Update a model instance in database.

        Args:
            model_class: The dataclass model type.
            instance: The instance with updated values.
            id_field: The field name to use as WHERE condition.
            id_value: The value of ID field to match.

        Raises:
            ValueError: If instance type doesn't match model_class or attributes missing.
            sqlite3.Error: If query fails.
        """
        if not isinstance(instance, model_class):
            raise ValueError(f"Instance must be of type {model_class.__name__}")

        table = getattr(model_class, "table_name", "")

        if not table:
            raise ValueError(
                f"Model {model_class.__name__} has no 'table_name' attribute"
            )

        model_fields = [
            f.name
            for f in fields(model_class)
            if f.name not in ["table_name", id_field]
        ]
        set_clause = ", ".join([f"{field} = ?" for field in model_fields])
        query = f"UPDATE {table} SET {set_clause} WHERE {id_field} = ?"

        values = [getattr(instance, field) for field in model_fields]
        values.append(id_value)
        params = tuple(values)

        self._execute_raw(query, params)

    def insert_relationship(self, table: str, **kwargs: Any) -> None:
        """Insert a relationship into a junction table.

        Args:
            table: The junction table name.
            **kwargs: Column name/value pairs.
        """
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        params = tuple(kwargs.values())

        self._execute_raw(query, params)

    def update_single_field(  # pylint: disable=too-many-arguments, R0917
        self,
        table: str,
        id_field: str,
        id_value: int | str,
        field_name: str,
        field_value: Any,
    ) -> None:
        """Update a single field in a table.

        Args:
            table: The table name.
            id_field: The field name to use as WHERE condition.
            id_value: The value of ID field to match.
            field_name: The field to update.
            field_value: The new value for the field.

        Raises:
            sqlite3.Error: If query fails.
        """
        query = f"UPDATE {table} SET {field_name} = ? WHERE {id_field} = ?"
        self._execute_raw(query, (field_value, id_value))

    def select_by_id(
        self, table: str, id_field: str, id_value: int | str
    ) -> list[dict[str, Any]]:
        """Select a record from table by ID field.

        Args:
            table: The table name.
            id_field: The field name to use as WHERE condition.
            id_value: The value of ID field to match.

        Returns:
            List of dictionaries with column names as keys.
        """
        query = f"SELECT * FROM {table} WHERE {id_field} = ?"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (id_value,))
            result = cursor.fetchone()
            if result:
                return [dict(result)]
            return []

    def log_scraping_operation(  # pylint: disable=R0913,R0917
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
