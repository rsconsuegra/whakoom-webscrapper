"""Pure parsers for Whakoom list-detail pages and SeriesPage JSON pagination.

``parse_list_page`` handles the first 50 server-rendered items of a list page;
``parse_series_page_json`` handles the ``POST /lists/listdetail.aspx/SeriesPage``
JSON payload used to paginate beyond the first page. Both share the same item
``<li>`` structure. No I/O, no DB (V2 §5 layering).
"""

from __future__ import annotations

import logging
import re

from parsel import Selector

from whakoom_scraper.domain import ListItem, ListPageMeta
from whakoom_scraper.scrapers._helpers import leading_int, text_or_none

log = logging.getLogger(__name__)

_VOLUME_NUMBER = re.compile(r"Vol\.\s*(\d+)")
_TERMINATOR = "0"


def parse_list_page(html: str, *, list_id: int) -> tuple[ListPageMeta, list[ListItem]]:
    """Parse the server-rendered first page of a list.

    Args:
        html: Raw HTML of the ``/{profile}/lists/{slug}_{id}`` page.
        list_id: The Whakoom list id this page belongs to (from the stage/URL).

    Returns:
        A tuple of the parsed header metadata and the page-1 items, with
        positions assigned 1..N.
    """
    selector = Selector(text=html)
    meta = _parse_list_meta(selector)
    items = _parse_items(selector, list_id=list_id, start_position=1)
    return meta, items


def parse_series_page_json(
    payload: dict[str, object],
    *,
    list_id: int,
    start_position: int,
) -> tuple[list[ListItem], int | None]:
    """Parse one SeriesPage JSON payload into items and the next page number.

    Args:
        payload: Decoded JSON ``{"Html": "<li>...</li>", "ExtraInfo": "..."}``.
        list_id: The Whakoom list id these items belong to.
        start_position: The 1-based position of the first item on this page
            (i.e. items fetched so far + 1), so positions stay globally unique
            per list.

    Returns:
        A tuple of the parsed items and the next page number, or ``None`` when
        ``ExtraInfo == "0"`` signals the end of pagination.
    """
    html = payload.get("Html")
    if not isinstance(html, str) or not html:
        return [], None
    selector = Selector(text=html)
    items = _parse_items(selector, list_id=list_id, start_position=start_position)
    return items, _next_page(payload.get("ExtraInfo"))


def _parse_list_meta(selector: Selector) -> ListPageMeta:
    """Extract the list header (name + advertised comic count)."""
    name = text_or_none(selector.css("h1 > span::text").get())
    comic_count = leading_int(selector.css("h1 > small::text").get())
    return ListPageMeta(name=name, comic_count=comic_count)


def _parse_items(selector: Selector, *, list_id: int, start_position: int) -> list[ListItem]:
    """Parse all ``li[data-item-id]`` items, assigning positions by offset."""
    items: list[ListItem] = []
    for offset, node in enumerate(selector.css("li[data-item-id]")):
        position = start_position + offset
        item = _parse_item(node, list_id=list_id, position=position)
        if item is not None:
            items.append(item)
    return items


def _parse_item(node: Selector, *, list_id: int, position: int) -> ListItem | None:
    """Parse a single item ``<li>`` into a :class:`ListItem`."""
    volume_url = node.css(".title a::attr(href)").get()
    if not volume_url:
        log.warning("skipping list item %d without volume url", position)
        return None

    publication_id_raw = node.attrib.get("data-item-id")
    whakoom_publication_id: int | None = None
    if publication_id_raw is not None:
        try:
            whakoom_publication_id = int(publication_id_raw)
        except ValueError:
            log.warning("non-numeric data-item-id on item %d: %s", position, publication_id_raw)

    volume_slug = volume_url.split("/")[2]
    number, publisher = _parse_desc(node.css(".desc::text").get())

    return ListItem(
        list_id=list_id,
        position=position,
        volume_slug=volume_slug,
        volume_url=volume_url,
        whakoom_publication_id=whakoom_publication_id,
        volume_number=number,
        publisher=publisher,
    )


def _parse_desc(desc: str | None) -> tuple[int | None, str | None]:
    """Split an item description into (volume_number, publisher).

    Descriptions look like ``"Vol. 1, Odaiba Ediciones"`` or
    ``"Tomo único, Odaiba Ediciones"``. The publisher is the text after the
    first ``", "``; the volume number is parsed from a leading ``Vol. N`` and is
    ``None`` for single volumes.
    """
    if desc is None:
        return None, None
    parts = desc.strip().split(", ", 1)
    number_part = parts[0]
    publisher = text_or_none(parts[1]) if len(parts) > 1 else None
    match = _VOLUME_NUMBER.search(number_part)
    number = int(match.group(1)) if match else None
    return number, publisher


def _next_page(extra_info: object) -> int | None:
    """Decode the ``ExtraInfo`` field into the next page number, or ``None``."""
    if not isinstance(extra_info, str) or extra_info == _TERMINATOR:
        return None
    try:
        return int(extra_info)
    except ValueError:
        log.warning("unexpected ExtraInfo %r — treating as end of pagination", extra_info)
        return None
