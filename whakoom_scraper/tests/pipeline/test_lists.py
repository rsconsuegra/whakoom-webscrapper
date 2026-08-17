"""Tests for :mod:`whakoom_scraper.pipeline.stage_lists`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from whakoom_scraper.config import Settings
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline.stage_lists import run_lists
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import get_lists
from whakoom_scraper.tests.conftest import ROBOTS_ALLOW_ALL, fast_settings, load_fixture


def _handler_factory(html: str) -> Callable[[httpx.Request], httpx.Response]:
    """Build a handler serving robots.txt + the lists-index HTML.

    Args:
        html: Body to return for the lists-index path.

    Returns:
        A MockTransport handler.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots.txt or the lists-index HTML."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(200, text=html)

    return handler


def test_run_lists_upserts_all_cards(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Stage 1 upserts every list card from the index."""
    handler = _handler_factory(load_fixture("lists_index.html"))
    session = make_session(handler)
    try:
        code = run_lists(fast_settings(), session=session, db=database)
    finally:
        session.close()

    assert code == 0
    all_lists = get_lists(database)
    assert len(all_lists) == 61

    spot = next((card for card in all_lists if card.whakoom_list_id == 153671), None)
    assert spot is not None
    assert spot.name == "Licencias manga en España, 2026"
    assert spot.comic_count == 49


def test_run_lists_is_idempotent(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Running twice yields the same 61 lists with no error."""
    handler = _handler_factory(load_fixture("lists_index.html"))
    session = make_session(handler)
    try:
        assert run_lists(fast_settings(), session=session, db=database) == 0
        assert run_lists(fast_settings(), session=session, db=database) == 0
    finally:
        session.close()

    assert len(get_lists(database)) == 61


def test_run_lists_persists_raw_when_enabled(
    make_session: Callable[..., WhakoomSession],
    database: Database,
    tmp_path: Path,
) -> None:
    """When save_raw is on, a gzip snapshot is written under raw_dir."""
    handler = _handler_factory(load_fixture("lists_index.html"))
    session = make_session(handler)
    settings = fast_settings(save_raw=True, raw_dir=tmp_path / "raw")
    try:
        assert run_lists(settings, session=session, db=database) == 0
    finally:
        session.close()

    archives = list((tmp_path / "raw").rglob("*.html.gz"))
    assert len(archives) == 1


def test_run_lists_robots_denied_returns_1(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """A robots.txt disallowing the lists path aborts the stage with code 1."""
    robots_deny = "User-agent: *\nDisallow: /deirdre/lists/\n"

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve the denying robots.txt and an empty index body."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots_deny)
        return httpx.Response(200, text=load_fixture("lists_index.html"))

    session = make_session(handler)
    try:
        code = run_lists(fast_settings(), session=session, db=database)
    finally:
        session.close()

    assert code == 1
    assert get_lists(database) == []


def test_run_lists_empty_index_succeeds(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """An index with no list cards parses fine and upserts nothing."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots then a malformed index body."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(200, text="<html>not a lists index</html>")

    session = make_session(handler)
    try:
        code = run_lists(fast_settings(), session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert get_lists(database) == []


@pytest.mark.parametrize("reset", [False, True])
def test_run_lists_reset_flag_runs(
    make_session: Callable[..., WhakoomSession],
    database: Database,
    reset: bool,
) -> None:
    """The reset flag is accepted and does not change the upserted count."""
    handler = _handler_factory(load_fixture("lists_index.html"))
    session = make_session(handler, settings=Settings(delay_seconds=0.0, jitter_seconds=0.0))
    try:
        code = run_lists(fast_settings(), reset=reset, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert len(get_lists(database)) == 61
