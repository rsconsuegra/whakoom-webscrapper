"""Shared domain-object factories for tests.

Single source for the ``List``/``ListItem`` builders that store and pipeline
test modules seed their databases with, so the builders exist in exactly one
place (pylint duplicate-code check).
"""

from __future__ import annotations

from whakoom_scraper.domain import List, ListItem


def make_list(
    whakoom_list_id: int = 1,
    name: str = "Manga 2000",
    comic_count: int | None = 120,
    *,
    description: str = "Toda la colección del año 2000",
    likes: int = 45,
) -> List:
    """Build a list card with stable defaults.

    Args:
        whakoom_list_id: Whakoom's list identifier.
        name: Display name of the list.
        comic_count: Advertised item count (None = not advertised).
        description: Free-text list description.
        likes: Advertised like count.

    Returns:
        A populated ``List`` domain object.
    """
    return List(
        whakoom_list_id=whakoom_list_id,
        name=name,
        url=f"https://www.whakoom.com/deirdre/lists/lista_{whakoom_list_id}",
        description=description,
        comic_count=comic_count,
        likes=likes,
    )


def make_item(list_id: int, position: int, slug: str = "abc12") -> ListItem:
    """Build a list item with stable defaults.

    Args:
        list_id: Surrogate id of the owning list row.
        position: Zero-based position of the item inside the list.
        slug: Volume slug segment of the item's URL.

    Returns:
        A populated ``ListItem`` domain object.
    """
    return ListItem(
        list_id=list_id,
        position=position,
        volume_slug=slug,
        volume_url=f"https://www.whakoom.com/comics/{slug}/una_obra/{position}",
        whakoom_publication_id=position,
        volume_number=position,
        publisher="Planeta Cómic",
    )
