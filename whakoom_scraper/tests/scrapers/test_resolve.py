"""Tests for the pure parsers in :mod:`whakoom_scraper.scrapers.resolve`.

These cover text/Selector → SeriesRef helpers only; the network orchestration
and login-expiry detection (``resolve_series_id``, ``SessionExpiredError``) are
tested in :mod:`whakoom_scraper.tests.test_http_resolve` (F2).
"""

from __future__ import annotations

from parsel import Selector

from whakoom_scraper.domain import SeriesRef
from whakoom_scraper.scrapers.resolve import _ediciones_ref, _name_from_quickview


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


def test_name_from_quickview_reads_nested_text() -> None:
    """A title nested under child elements is captured as a single string."""
    selector = Selector(
        text='<a href="/ediciones/673392/rosen_blood"><span><b>Rosen Blood</b></span></a>',
    )
    ref = SeriesRef(whakoom_series_id=673392, slug="rosen_blood", url="u")
    assert _name_from_quickview(selector, ref) == "Rosen Blood"


def test_name_from_quickview_joins_split_text() -> None:
    """Text split across child and direct nodes is joined and trimmed."""
    selector = Selector(
        text='<a href="/ediciones/673392/rosen_blood"><span>Rosen</span> Blood</a>',
    )
    ref = SeriesRef(whakoom_series_id=673392, slug="rosen_blood", url="u")
    assert _name_from_quickview(selector, ref) == "Rosen Blood"


def test_name_from_quickview_returns_none_without_anchor() -> None:
    """When no matching anchor exists, the name is None."""
    selector = Selector(text="<div>no anchor here</div>")
    ref = SeriesRef(whakoom_series_id=673392, slug="rosen_blood", url="u")
    assert _name_from_quickview(selector, ref) is None
