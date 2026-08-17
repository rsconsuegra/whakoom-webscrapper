"""Tests for the list-detail parser against the harvested fixtures."""

from __future__ import annotations

import json

from whakoom_scraper.scrapers.list_detail import parse_list_page, parse_series_page_json
from whakoom_scraper.tests.conftest import load_fixture


def _load_text(name: str) -> str:
    """Read a fixture file as text."""
    return load_fixture(name)


def _load_json(name: str) -> dict[str, object]:
    """Read a JSON fixture file as a dict."""
    return json.loads(_load_text(name))


def test_parse_list_page_header_and_item_count() -> None:
    """The list page header and page-1 item count are parsed correctly."""
    meta, items = parse_list_page(_load_text("list_detail_wings.html"), list_id=116046)
    assert meta.name == "Mangas publicados en la Wings"
    assert meta.comic_count == 10
    assert len(items) == 10


def test_parse_list_page_item_fields() -> None:
    """Each page-1 item carries position, slug, publication id, number, publisher."""
    _, items = parse_list_page(_load_text("list_detail_wings.html"), list_id=116046)
    first = items[0]
    assert first.list_id == 116046
    assert first.position == 1
    assert first.volume_slug == "81wm6"
    assert first.whakoom_publication_id == 46418
    assert first.volume_number == 1
    assert first.publisher == "Norma Editorial"
    assert first.volume_url == "/comics/81wm6/rg_veda/1"


def test_parse_list_page_positions_are_sequential() -> None:
    """Page-1 positions are assigned 1..N in document order."""
    _, items = parse_list_page(_load_text("list_detail_wings.html"), list_id=116046)
    assert [item.position for item in items] == list(range(1, 11))


def test_parse_list_page_third_item_publisher() -> None:
    """A different publisher on a later item is parsed from the description."""
    _, items = parse_list_page(_load_text("list_detail_wings.html"), list_id=116046)
    third = items[2]
    assert third.volume_slug == "rfgvq"
    assert third.publisher == "Planeta Cómic"
    assert third.volume_number == 1


def test_parse_series_page_json_pagination_terminates() -> None:
    """ExtraInfo == '0' terminates pagination and returns next_page None."""
    payload = _load_json("series_page_json_p2.json")
    items, next_page = parse_series_page_json(payload, list_id=106982, start_position=51)
    assert len(items) == 34
    assert next_page is None


def test_parse_series_page_json_positions_offset_by_start() -> None:
    """JSON-page positions continue from start_position across pages."""
    payload = _load_json("series_page_json_p2.json")
    items, _ = parse_series_page_json(payload, list_id=106982, start_position=51)
    assert [item.position for item in items] == list(range(51, 85))
    assert items[0].list_id == 106982


def test_parse_series_page_json_item_with_volume_number() -> None:
    """A 'Vol. N' description yields the integer volume number."""
    payload = _load_json("series_page_json_p2.json")
    items, _ = parse_series_page_json(payload, list_id=106982, start_position=51)
    first = items[0]
    assert first.position == 51
    assert first.volume_slug == "LdfR7"
    assert first.volume_number == 1
    assert first.publisher == "Odaiba Ediciones"


def test_parse_series_page_json_tomo_unico_has_no_number() -> None:
    """A 'Tomo único' description yields volume_number None."""
    payload = _load_json("series_page_json_p2.json")
    items, _ = parse_series_page_json(payload, list_id=106982, start_position=51)
    second = items[1]
    assert second.position == 52
    assert second.volume_slug == "y1XFO"
    assert second.volume_number is None
    assert second.publisher == "Odaiba Ediciones"


def test_parse_series_page_json_continues_when_extra_info_is_page() -> None:
    """A numeric ExtraInfo returns the next page number for a populated page."""
    html = (
        '<li data-item-id="100" data-item-type="comic">'
        '<span class="title"><a href="/comics/abc/series_x/1">Vol A</a></span>'
        '<span class="desc">Vol. 1, Pub</span></li>'
    )
    payload: dict[str, object] = {"Html": html, "ExtraInfo": "3"}
    items, next_page = parse_series_page_json(payload, list_id=1, start_position=1)
    assert len(items) == 1
    assert items[0].volume_slug == "abc"
    assert next_page == 3
