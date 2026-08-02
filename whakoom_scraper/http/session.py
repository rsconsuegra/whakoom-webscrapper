"""Polite, retrying sync HTTP client wrapping :mod:`httpx`.

Design (V2 §10):

* sync :class:`httpx.Client` with ``follow_redirects=True`` by default; the
  resolver passes ``follow_redirects=False`` per-request to inspect
  ``Location`` headers.
* politeness sleep ``WK_DELAY_SECONDS + U(0, WK_JITTER_SECONDS)`` before every
  request attempt.
* :mod:`tenacity` retry on transient transport errors
  (:class:`httpx.TimeoutException`, :class:`httpx.ConnectError`) and on
  transient HTTP statuses (429, 5xx); permanent statuses (e.g. 404) are
  returned immediately.
* cookie jar loaded from ``WHAKOOM_COOKIE_FILE`` (Netscape format) when set.
"""

from __future__ import annotations

import random
import time
from http.cookiejar import MozillaCookieJar
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from whakoom_scraper.config import Settings

BASE_URL = "https://www.whakoom.com"
DEFAULT_TIMEOUT = httpx.Timeout(30.0)

_RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError)


class TransientRequestError(Exception):
    """Raised when a request is still 429/5xx after exhausting retries.

    Attributes:
        status_code: The final HTTP status code.
        url: The URL that was requested.
    """

    def __init__(self, status_code: int, url: str) -> None:
        """Initialize the error.

        Args:
            status_code: The final HTTP status code.
            url: The URL that was requested.
        """
        super().__init__(f"Transient failure for {url}: HTTP {status_code}")
        self.status_code = status_code
        self.url = url


def load_cookies(cookie_file: str | None) -> httpx.Cookies | None:
    """Load a Netscape-format cookie file into an httpx cookie jar.

    Args:
        cookie_file: Path to a ``cookies.txt`` file, or ``None``.

    Returns:
        A populated ``httpx.Cookies`` instance, or ``None`` when no file is set.
    """
    if not cookie_file:
        return None
    jar = MozillaCookieJar(cookie_file)
    jar.load(ignore_discard=True, ignore_expires=True)
    cookies = httpx.Cookies()
    for cookie in jar:
        if cookie.value is None:
            continue
        cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
    return cookies


class WhakoomSession:
    """A polite, retrying sync HTTP client for Whakoom."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        retry_wait: wait_base | None = None,
    ) -> None:
        """Initialize the session.

        Args:
            settings: Runtime settings (delay, jitter, retries, UA, cookie file).
            client: Optional pre-built client (e.g. a mock transport for tests);
                when ``None`` a real client targeting Whakoom is built.
            retry_wait: Optional tenacity wait strategy; defaults to exponential
                backoff. Tests pass ``wait_none()`` to skip real waiting.
        """
        self._settings = settings
        self._client = client if client is not None else self._build_client(settings)
        self._retry_wait = retry_wait if retry_wait is not None else wait_exponential(multiplier=2, exp_base=2, max=30)
        self._rng = random.SystemRandom()

    @staticmethod
    def _build_client(settings: Settings) -> httpx.Client:
        """Build the default httpx client for Whakoom."""
        return httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
            cookies=load_cookies(settings.cookie_file),
            timeout=DEFAULT_TIMEOUT,
        )

    @property
    def client(self) -> httpx.Client:
        """The underlying httpx client."""
        return self._client

    def get(self, url: str, *, follow_redirects: bool | None = None, **kwargs: Any) -> httpx.Response:
        """Send a GET request.

        Args:
            url: Absolute or base-relative URL.
            follow_redirects: Per-request redirect override; ``None`` uses the
                client default.
            **kwargs: Additional kwargs forwarded to ``httpx.Client.request``.

        Returns:
            The final ``httpx.Response``.
        """
        return self._request("GET", url, follow_redirects=follow_redirects, **kwargs)

    def post(
        self,
        url: str,
        *,
        json: Any = None,
        follow_redirects: bool | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a POST request.

        Args:
            url: Absolute or base-relative URL.
            json: JSON-serializable request body.
            follow_redirects: Per-request redirect override; ``None`` uses the
                client default.
            **kwargs: Additional kwargs forwarded to ``httpx.Client.request``.

        Returns:
            The final ``httpx.Response``.
        """
        return self._request("POST", url, json=json, follow_redirects=follow_redirects, **kwargs)

    def close(self) -> None:
        """Close the underlying client."""
        self._client.close()

    def __enter__(self) -> WhakoomSession:
        """Enter the context, returning this session."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Exit the context, closing the underlying client."""
        self.close()

    def _polite_sleep(self) -> None:
        """Sleep for the configured delay plus uniform jitter before a request."""
        delay = self._settings.delay_seconds + self._rng.uniform(0, self._settings.jitter_seconds)
        time.sleep(delay)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute a request with politeness delay and transient-error retry."""
        follow_redirects = kwargs.pop("follow_redirects", None)
        request_kwargs: dict[str, Any] = dict(kwargs)
        if follow_redirects is not None:
            request_kwargs["follow_redirects"] = follow_redirects

        retrying = Retrying(
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS + (TransientRequestError,)),
            wait=self._retry_wait,
            stop=stop_after_attempt(self._settings.max_retries),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                self._polite_sleep()
                response = self._client.request(method, url, **request_kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    raise TransientRequestError(response.status_code, url)
                return response
        raise RuntimeError("retry loop exited without a result")  # pragma: no cover
