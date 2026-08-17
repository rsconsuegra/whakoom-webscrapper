"""Tests for the lists-index parser against the harvested fixture."""

from __future__ import annotations

from whakoom_scraper.scrapers.lists_index import parse_lists_index
from whakoom_scraper.tests.conftest import load_fixture


def _load(name: str) -> str:
    """Read a fixture file as text."""
    return load_fixture(name)


def test_parse_lists_index_returns_one_list_per_card() -> None:
    """The parser returns one List per card rendered in the index."""
    cards = parse_lists_index(_load("lists_index.html"))
    assert len(cards) == 61


def test_parse_lists_index_populated_card_fields() -> None:
    """A card with description populates every documented field."""
    cards = {c.whakoom_list_id: c for c in parse_lists_index(_load("lists_index.html"))}
    card = cards[153671]
    assert card.name == "Licencias manga en España, 2026"
    assert card.url.endswith("_153671")
    assert card.url.startswith("/deirdre/lists/")
    assert card.user_profile == "deirdre"
    assert card.comic_count == 49
    assert card.likes == 10
    assert card.description is not None
    assert card.description != ""


def test_parse_lists_index_missing_description_is_none() -> None:
    """A card without the optional description leaves it as None."""
    cards = {c.whakoom_list_id: c for c in parse_lists_index(_load("lists_index.html"))}
    assert cards[116035].description is None


def test_parse_lists_index_required_fields_present_for_all_cards() -> None:
    """Every parsed card carries the required identity fields."""
    cards = parse_lists_index(_load("lists_index.html"))
    assert cards, "fixture must yield at least one card"
    for card in cards:
        assert card.whakoom_list_id > 0
        assert card.name
        assert card.url.startswith("/deirdre/lists/")
        assert card.url.endswith(f"_{card.whakoom_list_id}")
        assert card.user_profile == "deirdre"
