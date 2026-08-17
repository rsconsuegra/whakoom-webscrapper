"""Tests for the series-page parser against the harvested fixture."""

from __future__ import annotations

from whakoom_scraper.scrapers.series_page import parse_series_page
from whakoom_scraper.tests.conftest import load_fixture

SERIES_ID = 673392
SLUG = "rosen_blood"
URL = f"/ediciones/{SERIES_ID}/{SLUG}"


def _load(name: str) -> str:
    """Read a fixture file as text."""
    return load_fixture(name)


def test_parse_series_page_identity_and_name() -> None:
    """The identity fields are echoed from the URL and the name from the h1."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.whakoom_series_id == SERIES_ID
    assert series.slug == SLUG
    assert series.url == URL
    assert series.name == "Rosen Blood"


def test_parse_series_page_publisher() -> None:
    """The publisher name, whakoom id and url are extracted from the publisher link."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    publisher = series.publisher
    assert publisher is not None
    assert publisher.name == "Panini Comics España"
    assert publisher.whakoom_id == 19081
    assert publisher.url == "/publisher/19081/panini_comics_espana"


def test_parse_series_page_status_format_language_and_count() -> None:
    """Status, format, language and volumes_count are parsed from the info block."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.status == "Terminada"
    assert series.format == "Rústica con sobrecubierta"
    assert series.language == "Español (España)"
    assert series.volumes_count == 5


def test_parse_series_page_rating_comma_decimal_and_count() -> None:
    """The European comma decimal rating is parsed as a float."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.rating == 4.3
    assert series.rating_count == 16


def test_parse_series_page_ownership_count() -> None:
    """The ownership count is parsed from the 'Lo tienen' info item."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.ownership_count == 0


def test_parse_series_page_rating_distribution() -> None:
    """The star distribution percentages are parsed from the rates-chart bars."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.rating_distribution == {"5": 56, "4": 19, "3": 25, "2": 0, "1": 0}


def test_parse_series_page_synopsis_and_original_title() -> None:
    """The synopsis is parsed under 'Argumento'; original_title is None when absent."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert series.original_title is None
    assert series.synopsis is not None
    assert series.synopsis.startswith("Después de sufrir un accidente con su carruaje")


def test_parse_series_page_authors() -> None:
    """Authors are parsed with name, role, whakoom id and url."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert len(series.authors) == 1
    author = series.authors[0]
    assert author.name == "Kachiru Ishizue"
    assert author.role == "author"
    assert author.whakoom_id == 93664
    assert author.url == "/autores/93664/kachiru_ishizue"


def test_parse_series_page_volumes() -> None:
    """Volumes are parsed with slug, number, title and cover url."""
    series = parse_series_page(_load("series_page_rosen_blood.html"), whakoom_series_id=SERIES_ID, slug=SLUG, url=URL)
    assert len(series.volumes) == 5
    first = series.volumes[0]
    assert first.volume_slug == "fxTr6"
    assert first.number == 1
    assert first.title == "Rosen Blood #1"
    assert first.cover_url is not None
    assert first.cover_url.startswith("https://i1.whakoom.com/small/")
    second = series.volumes[1]
    assert second.volume_slug == "fxTMk"
    assert second.number == 2
    assert second.title == "Rosen Blood #2"
