"""Tests for :mod:`whakoom_scraper.http.session`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from whakoom_scraper.config import Settings
from whakoom_scraper.http.session import (
    TransientRequestError,
    WhakoomSession,
    load_cookies,
)


class _Responder:
    """MockTransport handler that serves a canned response/error sequence.

    Each item is either an :class:`httpx.Response` to return or an
    :class:`Exception` to raise. Request paths are recorded for assertions.
    """

    def __init__(self, items: Sequence[httpx.Response | Exception]) -> None:
        """Store the response/error sequence.

        Args:
            items: Ordered responses and/or exceptions, consumed one per call.
        """
        self._items: list[httpx.Response | Exception] = list(items)
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Consume the next item, recording the request path."""
        self.requests.append(request.url.path)
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def calls(self) -> int:
        """Number of requests received so far."""
        return len(self.requests)


def _fast_settings() -> Settings:
    """Return settings with politeness delay disabled."""
    return Settings(delay_seconds=0.0, jitter_seconds=0.0)


def _make_session(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    settings: Settings | None = None,
) -> WhakoomSession:
    """Build a session backed by a MockTransport invoking ``handler``."""
    client = httpx.Client(
        base_url="https://www.whakoom.com",
        follow_redirects=True,
        transport=httpx.MockTransport(handler),
    )
    return WhakoomSession(settings or _fast_settings(), client=client, retry_wait=wait_none())


def _redirect_chain_handler(request: httpx.Request) -> httpx.Response:
    """Return a 302 to /b for /a and a 200 body for /b."""
    if request.url.path == "/a":
        return httpx.Response(302, headers={"Location": "/b"})
    return httpx.Response(200, text="b")


def _redirect_only_handler(request: httpx.Request) -> httpx.Response:
    """Always return a 302 to /b, asserting the requested path."""
    assert request.url.path == "/a"
    return httpx.Response(302, headers={"Location": "/b"})


def test_default_client_construction() -> None:
    """A real client is built when none is injected."""
    session = WhakoomSession(_fast_settings())
    assert isinstance(session.client, httpx.Client)
    session.close()


def test_get_returns_response() -> None:
    """A 200 response is returned unchanged."""
    session = _make_session(_Responder([httpx.Response(200, text="ok")]))
    response = session.get("/deirdre/lists/")
    assert response.status_code == 200
    assert response.text == "ok"
    session.close()


def test_no_retry_on_404() -> None:
    """A permanent 404 is returned immediately, with a single attempt."""
    responder = _Responder([httpx.Response(404)])
    session = _make_session(responder)
    response = session.get("/missing")
    assert response.status_code == 404
    assert len(responder.requests) == 1
    session.close()


def test_retry_on_503_then_success() -> None:
    """A 503 then 200 is retried and ultimately succeeds after three attempts."""
    responder = _Responder([httpx.Response(503), httpx.Response(503), httpx.Response(200, text="ok")])
    session = _make_session(responder)
    response = session.get("/x")
    assert response.status_code == 200
    assert len(responder.requests) == 3
    session.close()


def test_retry_on_429_then_success() -> None:
    """A 429 then 200 is retried once and succeeds."""
    responder = _Responder([httpx.Response(429), httpx.Response(200, text="ok")])
    session = _make_session(responder)
    response = session.get("/x")
    assert response.status_code == 200
    assert len(responder.requests) == 2
    session.close()


def test_retry_on_connect_error_then_success() -> None:
    """A transient ConnectError is retried and the next attempt succeeds."""
    responder = _Responder([httpx.ConnectError("boom"), httpx.Response(200, text="ok")])
    session = _make_session(responder)
    response = session.get("/x")
    assert response.status_code == 200
    assert len(responder.requests) == 2
    session.close()


def test_exhaust_retries_raises_transient() -> None:
    """Persistent 503s exhaust retries and raise TransientRequestError."""
    responder = _Responder([httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    session = _make_session(responder)
    with pytest.raises(TransientRequestError):
        session.get("/x")
    assert len(responder.requests) == _fast_settings().max_retries
    session.close()


def test_follow_redirects_default_follows() -> None:
    """With the default, a 302 chain is followed to the final 200."""
    session = _make_session(_redirect_chain_handler)
    response = session.get("/a")
    assert response.status_code == 200
    assert response.text == "b"
    session.close()


def test_follow_redirects_disabled_returns_redirect() -> None:
    """A per-request override returns the raw 302 without following."""
    session = _make_session(_redirect_only_handler)
    response = session.get("/a", follow_redirects=False)
    assert response.status_code == 302
    session.close()


def test_politeness_sleep_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured delay is slept before each request."""
    sleeps: list[float] = []
    monkeypatch.setattr("whakoom_scraper.http.session.time.sleep", sleeps.append)

    session = _make_session(
        _Responder([httpx.Response(200, text="ok")]),
        settings=Settings(delay_seconds=1.5, jitter_seconds=0.0),
    )
    session.get("/x")
    assert sleeps and sleeps[0] == 1.5
    session.close()


def test_load_cookies_from_file(tmp_path: Path) -> None:
    """A Netscape cookie file populates the httpx cookie jar."""
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n.whakoom.com\tTRUE\t/\tFALSE\t0\tsession\tabc123\n",
        encoding="utf-8",
    )
    cookies = load_cookies(str(cookie_file))
    assert cookies is not None
    assert cookies.get("session") == "abc123"


def test_load_cookies_none_when_no_file() -> None:
    """No cookie file returns None."""
    assert load_cookies(None) is None
