"""Integration tests for the resolve stage (Stage 3, login-gated)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
from pytest import MonkeyPatch

from whakoom_scraper.config import Settings
from whakoom_scraper.domain import List, ListItem
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline import stage_resolve
from whakoom_scraper.pipeline.stage_resolve import run_resolve
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    get_series,
    get_unresolved_slugs,
    replace_list_items,
    upsert_list,
)
from whakoom_scraper.tests.conftest import ROBOTS_ALLOW_ALL


def _gated_settings(*, allow_gated: bool = True) -> Settings:
    """Return fast settings with gated resolution optionally enabled."""
    return Settings(delay_seconds=0.0, jitter_seconds=0.0, allow_gated_resolution=allow_gated)


def _seed(database: Database, slugs: tuple[str, ...]) -> None:
    """Insert a list and unresolved items carrying the given volume slugs."""
    list_db_id = upsert_list(database, List(whakoom_list_id=1, name="t", url="/deirdre/lists/t_1"))
    items = [
        ListItem(
            list_id=1,
            position=index + 1,
            volume_slug=slug,
            volume_url=f"/comics/{slug}/x/{index + 1}",
        )
        for index, slug in enumerate(slugs)
    ]
    replace_list_items(database, list_db_id, items)
    database.commit()


def _latest_run_status(database: Database) -> str:
    """Return the status of the most recent scrape_runs row."""
    row = database.connection.execute("SELECT status FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    return str(row[0])


def test_quickview_resolves_and_links_series(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """A QuickView 200 with an ediciones link stubs the series and links the item."""
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots + a QuickView payload resolving slug abc to series 123."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            return httpx.Response(
                200,
                json={"ControlID": None, "Html": '<a href="/ediciones/123/rg_veda">RG Veda</a>'},
            )
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 0
    assert get_unresolved_slugs(database) == []
    series = get_series(database, 123)
    assert series is not None
    assert series.slug == "rg_veda"


def test_comics_fallback_resolves(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """When QuickView yields no link, the /comics/ redirect fallback resolves."""
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots, empty QuickView, and a /comics/ redirect to ediciones."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            return httpx.Response(200, json={"ControlID": None, "Html": ""})
        if request.url.path == "/comics/abc/":
            return httpx.Response(302, headers={"Location": "/ediciones/456/series_x"})
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 0
    assert get_unresolved_slugs(database) == []
    assert get_series(database, 456) is not None


def test_unresolved_writes_review_csv(
    database: Database,
    make_session: Callable[..., WhakoomSession],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Slugs that resolve to nothing stay unresolved and land in the review CSV."""
    review = tmp_path / "review_unresolved.csv"
    monkeypatch.setattr(stage_resolve, "REVIEW_CSV", review)
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots, empty QuickView, and a 404 /comics/ fallback."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            return httpx.Response(200, json={"ControlID": None, "Html": ""})
        if request.url.path == "/comics/abc/":
            return httpx.Response(404)
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 0
    assert get_unresolved_slugs(database) == ["abc"]
    assert review.exists()
    assert "abc" in review.read_text(encoding="utf-8")


def test_clean_run_clears_stale_review_csv(
    database: Database,
    make_session: Callable[..., WhakoomSession],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A clean run (0 unresolved) removes a pre-existing stale review CSV."""
    review = tmp_path / "review_unresolved.csv"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text("volume_slug\nstale\n", encoding="utf-8")
    monkeypatch.setattr(stage_resolve, "REVIEW_CSV", review)
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Resolve the slug so the run is clean (0 unresolved)."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            return httpx.Response(
                200,
                json={"ControlID": None, "Html": '<a href="/ediciones/9/x">X</a>'},
            )
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 0
    assert get_unresolved_slugs(database) == []
    assert not review.exists()


def test_session_expired_aborts_with_code_3(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """A 401 from QuickView aborts the stage with exit code 3 and status aborted."""
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots and a 401 QuickView (expired cookie)."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            return httpx.Response(401)
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 3
    assert _latest_run_status(database) == "aborted"
    assert get_unresolved_slugs(database) == ["abc"]


def test_limit_caps_slugs(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """--limit caps the number of slugs processed."""
    _seed(database, ("a", "b", "c"))
    quickview_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots and a QuickView that resolves every slug to series 1."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == "/pwkws.asmx/QuickView":
            quickview_calls["n"] += 1
            return httpx.Response(
                200,
                json={"ControlID": None, "Html": '<a href="/ediciones/1/s_1">S1</a>'},
            )
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database, limit=2)
    assert code == 0
    assert quickview_calls["n"] == 2
    assert get_unresolved_slugs(database) == ["c"]


def test_gated_disabled_returns_fatal(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """With gated resolution disabled the stage aborts fatally without resolving."""
    _seed(database, ("abc",))

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve only robots; no QuickView should be requested."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(404)

    code = run_resolve(_gated_settings(allow_gated=False), session=make_session(handler), db=database)
    assert code == 1
    assert get_unresolved_slugs(database) == ["abc"]


def test_no_unresolved_slugs_is_a_clean_noop(database: Database, make_session: Callable[..., WhakoomSession]) -> None:
    """An empty unresolved set exits cleanly without issuing any QuickView call."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve only robots."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(404)

    code = run_resolve(_gated_settings(), session=make_session(handler), db=database)
    assert code == 0
