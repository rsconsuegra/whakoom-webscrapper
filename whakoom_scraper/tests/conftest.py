"""Shared pytest fixtures for the Whakoom V2 test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from whakoom_scraper.store.db import Database


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    """Yield a fresh Database on a temp file."""
    store = Database(tmp_path / "whakoom.db")
    yield store
    store.close()
