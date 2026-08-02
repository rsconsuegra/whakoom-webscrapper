"""Shared pytest fixtures for the Whakoom V2 test suite."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from whakoom_scraper.config import PROJECT_ROOT, Settings
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.store.db import Database

FIXTURES_DIR = PROJECT_ROOT / "whakoom_scraper" / "tests" / "fixtures"

#: Permissive robots.txt body used by pipeline tests (allows everything).
ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    """Yield a fresh Database on a temp file."""
    store = Database(tmp_path / "whakoom.db")
    yield store
    store.close()


@pytest.fixture
def make_session() -> Callable[..., WhakoomSession]:
    """Return a factory that builds a MockTransport-backed session.

    The factory signature mirrors the per-test ``_make_session`` helper: it
    takes a request handler and optional settings, and wires ``wait_none()`` so
    retries do not sleep.
    """

    def _make(
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        settings: Settings | None = None,
        follow_redirects: bool = True,
    ) -> WhakoomSession:
        """Build a WhakoomSession backed by a MockTransport."""
        client = httpx.Client(
            base_url="https://www.whakoom.com",
            follow_redirects=follow_redirects,
            transport=httpx.MockTransport(handler),
        )
        return WhakoomSession(
            settings or Settings(delay_seconds=0.0, jitter_seconds=0.0),
            client=client,
            retry_wait=wait_none(),
        )

    return _make


def load_fixture(name: str) -> str:
    """Read a text fixture from ``tests/fixtures`` as UTF-8.

    Args:
        name: Fixture filename (e.g. ``lists_index.html``).

    Returns:
        The fixture's text contents.
    """
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def fast_settings(*, save_raw: bool = False, raw_dir: Path | None = None) -> Settings:
    """Return settings with politeness delay disabled and raw archiving off.

    Args:
        save_raw: Whether raw archiving is enabled.
        raw_dir: Archive root; ignored unless ``save_raw`` is True.

    Returns:
        A ``Settings`` instance with no delay/jitter.
    """
    return Settings(
        delay_seconds=0.0,
        jitter_seconds=0.0,
        save_raw=save_raw,
        raw_dir=raw_dir or Path("/tmp/raw"),
    )
