"""Pure parsers for list→series resolution.

These functions turn text/markup into a :class:`SeriesRef` with **no** network
or session dependencies, so they are unit-testable from fixture text alone. The
network orchestration (QuickView POST, redirect fallback, login-expiry
detection) lives in :mod:`whakoom_scraper.http.resolve` (F2).

Stage 3 is the only authenticated step (V2 §11, ADR-0002) and issues at most two
requests per unique slug. Because the pure redirect fallback yields no series
name without a second request, the resolver is name-aware but tolerates a
missing name — the schema allows ``series.name`` to stay NULL until Stage 4
fills it (L1 fix).
"""

from __future__ import annotations

from parsel import Selector

from whakoom_scraper.constants import BASE_URL, EDICIONES_PATTERN
from whakoom_scraper.domain import SeriesRef


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
    """Extract the series name from a QuickView card, including nested text.

    ``xpath('string(.)')`` concatenates **all** descendant text of the anchor, so
    a title nested under child elements (e.g. ``<a><span><b>Title</b></span></a>``)
    is captured as a single trimmed string rather than missed as direct-only text
    would (F4).

    Args:
        selector: Parsel selector over the QuickView response body.
        ref: The already-parsed SeriesRef whose anchor to inspect.

    Returns:
        The trimmed anchor text, or ``None`` if no anchor or text is present.
    """
    anchor = selector.css(f'a[href*="{ref.whakoom_series_id}"]')
    if not anchor:
        return None
    text = anchor.xpath("string(.)").get()
    return text.strip() if text and text.strip() else None
