"""Tests for :mod:`whakoom_scraper.http.resolve` (session I/O + expiry).

The pure parsing helpers are tested in
:mod:`whakoom_scraper.tests.test_scrapers_resolve`; this module covers the
network orchestration (``resolve_series_id``) and the three login-expiry signals
(F3): 401, pre-follow 3xx → /login, and a followed redirect landing on /login.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from tenacity import wait_none

from whakoom_scraper.config import Settings
from whakoom_scraper.http.resolve import SessionExpiredError, resolve_series_id
from whakoom_scraper.http.session import WhakoomSession


def _fast_settings() -> Settings:
    """Return settings with politeness delay disabled."""
    return Settings(delay_seconds=0.0, jitter_seconds=0.0)


def _make_session(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    follow_redirects: bool = False,
) -> WhakoomSession:
    """Build a session backed by a MockTransport invoking ``handler``.

    Args:
        handler: MockTransport request handler.
        follow_redirects: Whether the underlying client follows redirects; the
            real Whakoom client follows them by default, so the followed-login
            case (F3) is exercised with this set to ``True``.

    Returns:
        A ``WhakoomSession`` wrapping the mock client.
    """
    client = httpx.Client(
        base_url="https://www.whakoom.com",
        transport=httpx.MockTransport(handler),
        follow_redirects=follow_redirects,
    )
    return WhakoomSession(_fast_settings(), client=client, retry_wait=wait_none())


def _quickview_handler(request: httpx.Request) -> httpx.Response:
    """Serve a JSON-wrapped QuickView card with the series link and a nested title."""
    assert request.url.path == "/pwkws.asmx/QuickView"
    return httpx.Response(
        200,
        json={
            "ControlID": None,
            "Html": '<a href="/ediciones/673392/rosen_blood"><span><b>Rosen Blood</b></span></a>',
        },
    )


def test_resolve_quickview_returns_named_ref() -> None:
    """The QuickView primary path returns a SeriesRef with a name."""
    session = _make_session(_quickview_handler)
    try:
        ref = resolve_series_id(session, "rosen_blood_t1")
    finally:
        session.close()
    assert ref is not None
    assert ref.whakoom_series_id == 673392
    assert ref.slug == "rosen_blood"
    assert ref.name == "Rosen Blood"


def _redirect_handler(request: httpx.Request) -> httpx.Response:
    """Return a 404 for QuickView and a 302 carrying the ediciones Location."""
    if request.url.path == "/pwkws.asmx/QuickView":
        return httpx.Response(404)
    return httpx.Response(302, headers={"Location": "/ediciones/673392/rosen_blood"})


def test_resolve_redirect_fallback_has_no_name() -> None:
    """The redirect fallback yields a SeriesRef whose name is None."""
    session = _make_session(_redirect_handler)
    try:
        ref = resolve_series_id(session, "rosen_blood_t1")
    finally:
        session.close()
    assert ref is not None
    assert ref.whakoom_series_id == 673392
    assert ref.name is None


def _login_redirect_handler(request: httpx.Request) -> httpx.Response:
    """Return a pre-follow 302 to /login for any request."""
    assert request.url.path in ("/pwkws.asmx/QuickView", "/comics/rosen_blood_t1/")
    return httpx.Response(302, headers={"Location": "/login"})


def test_resolve_session_expiry_raises_on_login_redirect() -> None:
    """A pre-follow 302 to /login aborts via SessionExpiredError (F3 case b)."""
    session = _make_session(_login_redirect_handler)
    try:
        with pytest.raises(SessionExpiredError):
            resolve_series_id(session, "rosen_blood_t1")
    finally:
        session.close()


def _unauthorized_handler(request: httpx.Request) -> httpx.Response:
    """Return 401 for the QuickView request."""
    assert request.url.path == "/pwkws.asmx/QuickView"
    return httpx.Response(401)


def test_resolve_401_raises_session_expired() -> None:
    """A 401 response aborts via SessionExpiredError (F3 case a)."""
    session = _make_session(_unauthorized_handler)
    try:
        with pytest.raises(SessionExpiredError):
            resolve_series_id(session, "rosen_blood_t1")
    finally:
        session.close()


def _followed_login_handler(request: httpx.Request) -> httpx.Response:
    """Serve a 302 → /login that the client follows into a 200 login page."""
    if request.url.path == "/pwkws.asmx/QuickView":
        return httpx.Response(302, headers={"Location": "/login"})
    assert request.url.path == "/login"
    return httpx.Response(200, text="<html>login page</html>")


def test_resolve_followed_login_redirect_raises() -> None:
    """A followed redirect landing on /login aborts via SessionExpiredError (F3 case c)."""
    session = _make_session(_followed_login_handler, follow_redirects=True)
    try:
        with pytest.raises(SessionExpiredError):
            resolve_series_id(session, "rosen_blood_t1")
    finally:
        session.close()
