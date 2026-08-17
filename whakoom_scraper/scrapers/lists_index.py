"""Pure parser for the Whakoom profile lists-index page.

Transforms the server-rendered HTML of ``/{profile}/lists/`` into a list of
:class:`~whakoom_scraper.domain.List` objects. No I/O, no DB (V2 §5 layering).
"""

from __future__ import annotations

import logging

from parsel import Selector

from whakoom_scraper.domain import List
from whakoom_scraper.scrapers._helpers import leading_int, text_or_none

log = logging.getLogger(__name__)


def parse_lists_index(html: str) -> list[List]:
    """Parse the lists-index HTML into list cards.

    Args:
        html: Raw HTML of the ``/{profile}/lists/`` page.

    Returns:
        One :class:`List` per ``div.list-item`` card. Cards missing required
        fields (title or URL) are skipped with a warning.
    """
    selector = Selector(text=html)
    cards: list[List] = []
    for card in selector.css("#pp-lists .list-item"):
        title_node = card.css("h3 > a::text").get()
        url = card.css("h3 > a::attr(href)").get()
        if not title_node or not url:
            log.warning("skipping list card without title/url")
            continue

        title = title_node.strip()
        try:
            whakoom_list_id = int(url.rsplit("_", 1)[-1])
        except ValueError:
            log.warning("skipping list card with non-numeric id: %s", url)
            continue

        profile = url.split("/")[1]
        description = text_or_none(card.css(".desc::text").get())
        comic_count = leading_int(card.css(".ccount::text").get())
        likes = leading_int(card.css(".like::text").get())

        cards.append(
            List(
                whakoom_list_id=whakoom_list_id,
                name=title,
                url=url,
                user_profile=profile,
                description=description,
                comic_count=comic_count,
                likes=likes,
            )
        )
    return cards
