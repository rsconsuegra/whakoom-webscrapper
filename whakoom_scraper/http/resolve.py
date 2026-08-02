"""Authenticated resolution of a volume slug to a :class:`SeriesRef`.

Stage 3 is the only authenticated step (V2 §11, ADR-0002). The I/O here issues at
most two requests per unique slug: the QuickView primary path (POST), then a
redirect-fallback GET when that fails. Pure parsing helpers live in
:mod:`whakoom_scraper.scrapers.resolve`; this module owns the session I/O and
login-expiry detection (F2, F3).
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx
from parsel import Selector

from whakoom_scraper.constants import BASE_URL, LOGIN_PATH, QUICKVIEW_URL
from whakoom_scraper.domain import SeriesRef
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.scrapers.resolve import _ediciones_ref, _name_from_quickview

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class SessionExpiredError(Exception):
    """Raised when a resolution request indicates the cookie session expired.

    Attributes:
        url: The URL (Location header or final response URL) that signalled the
            login redirect.
    """

    def __init__(self, url: str) -> None:
        """Initialize the error.

        Args:
            url: The URL (Location header or final response URL) that signalled
                the login redirect.
        """
        super().__init__(f"Session expired: {url} redirected to {LOGIN_PATH}")
        self.url = url


def _raise_if_login_expired(response: httpx.Response) -> None:
    """Raise SessionExpiredError when ``response`` indicates an expired session.

    Three signals are detected (F3):

    1. a ``401`` status;
    2. a pre-follow ``3xx`` whose ``Location`` targets ``/login``;
    3. a followed response whose final URL path contains ``/login`` (httpx
       followed the redirect into the login page).

    Args:
        response: The ``httpx.Response`` to inspect.

    Raises:
        SessionExpiredError: If any login-expiry signal is present.
    """
    if response.status_code == 401:
        raise SessionExpiredError(str(response.url))
    location = response.headers.get("Location", "")
    if response.status_code in _REDIRECT_STATUSES and LOGIN_PATH in location:
        raise SessionExpiredError(location)
    if LOGIN_PATH in response.url.path:
        raise SessionExpiredError(str(response.url))


def _quickview_html(response: httpx.Response) -> str | None:
    """Extract the ``Html`` payload from a QuickView JSON response.

    QuickView returns a JSON object ``{"ControlID": ..., "Html": "<html>"}``;
    the series link lives inside the ``Html`` string (not the raw JSON body,
    which parsel would treat as a JSON selector and refuse CSS on).

    Args:
        response: The QuickView ``httpx.Response``.

    Returns:
        The ``Html`` string, or ``None`` when the body is not valid JSON or has
        no string ``Html`` field.
    """
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    html = payload.get("Html")
    return html if isinstance(html, str) else None


def resolve_series_id(session: WhakoomSession, volume_slug: str) -> SeriesRef | None:
    """Resolve a volume slug to its series, name-aware.

    Primary path: POST ``/pwkws.asmx/QuickView`` and extract the embedded
    ``/ediciones/{id}/{slug}`` link plus the card title from the JSON-wrapped
    ``Html`` payload. Fallback: GET the volume page with
    ``follow_redirects=False``; a ``Location`` containing ``/ediciones`` yields
    the identity (without a name), a 200 body is scanned for the parent-series
    link.

    Args:
        session: Authenticated HTTP session (cookie-backed for this stage).
        volume_slug: The volume token to resolve.

    Returns:
        A SeriesRef, or ``None`` when every path failed.

    Raises:
        SessionExpiredError: If a request signals an expired session (401 or a
            redirect/final URL targeting ``/login``).
    """
    quick = session.post(QUICKVIEW_URL, json={"cid": f"comic{volume_slug}"})
    _raise_if_login_expired(quick)
    if quick.status_code == 200:
        html_body = _quickview_html(quick)
        if html_body:
            selector = Selector(text=html_body)
            for anchor in selector.css("a[href]"):
                ref = _ediciones_ref(anchor.attrib.get("href", ""))
                if ref is not None:
                    name = _name_from_quickview(selector, ref)
                    return SeriesRef(
                        whakoom_series_id=ref.whakoom_series_id,
                        slug=ref.slug,
                        url=ref.url,
                        name=name,
                    )

    fallback = session.get(
        urljoin(BASE_URL, f"/comics/{volume_slug}/"),
        follow_redirects=False,
    )
    _raise_if_login_expired(fallback)
    location = fallback.headers.get("Location", "")
    ref = _ediciones_ref(location)
    if ref is not None:
        return ref
    if fallback.status_code == 200:
        return _ediciones_ref(fallback.text)
    return None
