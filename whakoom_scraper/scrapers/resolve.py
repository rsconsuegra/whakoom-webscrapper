"""List→series resolution: map a volume slug to a minimal :class:`SeriesRef`.

Stage 3 is the only authenticated step (V2 §11, ADR-0002) and issues at most
two requests per unique slug: the QuickView primary path, then the redirect
fallback when that fails. Because the pure redirect fallback yields no series
name without a second request, the resolver is name-aware but tolerates a
missing name — the schema allows ``series.name`` to stay NULL until Stage 4
fills it (L1 fix).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from parsel import Selector

from whakoom_scraper.domain import SeriesRef
from whakoom_scraper.http.session import WhakoomSession

QUICKVIEW_URL = "/pwkws.asmx/QuickView"
EDICIONES_PATTERN = re.compile(r"/ediciones/(\d+)/([^/?#\"']+)")
LOGIN_PATH = "/login"

BASE_URL = "https://www.whakoom.com"


class SessionExpiredError(Exception):
    """Raised when a resolution request is redirected to the login page.

    Attributes:
        url: The URL that triggered the redirect.
    """

    def __init__(self, url: str) -> None:
        """Initialize the error.

        Args:
            url: The URL that triggered the redirect.
        """
        super().__init__(f"Session expired: {url} redirected to /login")
        self.url = url


def _ediciones_ref(text: str) -> SeriesRef | None:
    """Extract the first ``/ediciones/{id}/{slug}`` reference from markup or a URL.

    Args:
        text: HTML or a URL string to scan.

    Returns:
        A SeriesRef with the parsed identity, or ``None`` if absent.
    """
    match = EDICIONES_PATTERN.search(text)
    if match is None:
        return None
    series_id = int(match.group(1))
    slug = match.group(2)
    return SeriesRef(
        whakoom_series_id=series_id,
        slug=slug,
        url=f"{BASE_URL}/ediciones/{series_id}/{slug}",
    )


def _name_from_quickview(selector: Selector, ref: SeriesRef) -> str | None:
    """Extract the series name from a QuickView card when the anchor has text.

    Args:
        selector: Parsel selector over the QuickView response body.
        ref: The already-parsed SeriesRef whose anchor to inspect.

    Returns:
        The trimmed anchor text, or ``None`` if not available.
    """
    anchor = selector.css(f'a[href*="{ref.whakoom_series_id}"]')
    if not anchor:
        return None
    text = anchor.css("::text").get()
    return text.strip() if text and text.strip() else None


def _raise_if_login_expired(response: httpx.Response) -> None:
    """Raise SessionExpiredError when a response redirects to the login page.

    Args:
        response: The ``httpx.Response`` to inspect.

    Raises:
        SessionExpiredError: If the response is a redirect to ``/login``.
    """
    location = response.headers.get("Location", "")
    if response.status_code in (301, 302, 303, 307, 308) and LOGIN_PATH in location:
        raise SessionExpiredError(location)


def resolve_series_id(session: WhakoomSession, volume_slug: str) -> SeriesRef | None:
    """Resolve a volume slug to its series, name-aware.

    Primary path: POST ``/pwkws.asmx/QuickView`` and extract the embedded
    ``/ediciones/{id}/{slug}`` link plus the card title. Fallback: GET the
    volume page with ``follow_redirects=False``; a ``Location`` containing
    ``/ediciones`` yields the identity (without a name), a 200 body is scanned
    for the parent-series link.

    Args:
        session: Authenticated HTTP session (cookie-backed for this stage).
        volume_slug: The volume token to resolve.

    Returns:
        A SeriesRef, or ``None`` when every path failed.

    Raises:
        SessionExpiredError: If a request is redirected to ``/login``.
    """
    quick = session.post(QUICKVIEW_URL, json={"cid": f"comic{volume_slug}"})
    _raise_if_login_expired(quick)
    if quick.status_code == 200:
        selector = Selector(text=quick.text)
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
