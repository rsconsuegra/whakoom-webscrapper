"""Tests for :mod:`whakoom_scraper.scrapers.resolve`."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from tenacity import wait_none

from whakoom_scraper.config import Settings
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.scrapers.resolve import (
    SessionExpiredError,
    _ediciones_ref,
    resolve_series_id,
)


def _fast_settings() -> Settings:
    """Return settings with politeness delay disabled."""
    return Settings(delay_seconds=0.0, jitter_seconds=0.0)


def _make_session(handler: Callable[[httpx.Request], httpx.Response]) -> WhakoomSession:
    """Build a session backed by a MockTransport invoking ``handler``."""
    client = httpx.Client(
        base_url="https://www.whakoom.com",
        transport=httpx.MockTransport(handler),
    )
    return WhakoomSession(_fast_settings(), client=client, retry_wait=wait_none())


def test_ediciones_ref_parses_url() -> None:
    """A Location header carrying an ediciones path yields a SeriesRef."""
    ref = _ediciones_ref("https://www.whakoom.com/ediciones/673392/rosen_blood/1")
    assert ref is not None
    assert ref.whakoom_series_id == 673392
    assert ref.slug == "rosen_blood"
    assert ref.name is None


def test_ediciones_ref_returns_none_when_absent() -> None:
    """Text without an ediciones path yields None."""
    assert _ediciones_ref("https://www.whakoom.com/login") is None


def _quickview_handler(request: httpx.Request) -> httpx.Response:
    """Serve a QuickView card with the series link and title."""
    assert request.url.path == "/pwkws.asmx/QuickView"
    return httpx.Response(
        200,
        text=('<a href="/ediciones/673392/rosen_blood" class="item"><span>Rosen Blood</span></a>'),
    )


def test_resolve_quickview_returns_named_ref() -> None:
    """The QuickView primary path returns a SeriesRef with a name."""
    session = _make_session(_quickview_handler)
    ref = resolve_series_id(session, "rosen_blood_t1")
    assert ref is not None
    assert ref.whakoom_series_id == 673392
    assert ref.slug == "rosen_blood"
    assert ref.name == "Rosen Blood"
    session.close()


def _redirect_handler(request: httpx.Request) -> httpx.Response:
    """Return a 404 for QuickView and a 302 carrying the ediciones Location."""
    if request.url.path == "/pwkws.asmx/QuickView":
        return httpx.Response(404)
    return httpx.Response(
        302,
        headers={"Location": "/ediciones/673392/rosen_blood"},
    )


def test_resolve_redirect_fallback_has_no_name() -> None:
    """The redirect fallback yields a SeriesRef whose name is None."""
    session = _make_session(_redirect_handler)
    ref = resolve_series_id(session, "rosen_blood_t1")
    assert ref is not None
    assert ref.whakoom_series_id == 673392
    assert ref.name is None
    session.close()


def _login_redirect_handler(request: httpx.Request) -> httpx.Response:
    """Return a 302 to /login for any request."""
    assert request.url.path in ("/pwkws.asmx/QuickView", "/comics/rosen_blood_t1/")
    return httpx.Response(302, headers={"Location": "/login"})


def test_resolve_session_expiry_raises() -> None:
    """A redirect to /login aborts the stage via SessionExpiredError."""
    session = _make_session(_login_redirect_handler)
    try:
        resolve_series_id(session, "rosen_blood_t1")
    except SessionExpiredError:
        pass
    else:
        raise AssertionError("Expected SessionExpiredError")
    finally:
        session.close()
