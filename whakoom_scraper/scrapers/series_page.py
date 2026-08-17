"""Pure parser for the Whakoom series (``/ediciones/{id}/{slug}``) page.

Transforms the server-rendered series page into a :class:`~whakoom_scraper.domain.Series`
with its publisher, authors, volumes, rating, rating distribution, and metadata.
No I/O, no DB (V2 §5 layering).
"""

from __future__ import annotations

import logging
import re

from parsel import Selector

from whakoom_scraper.domain import Author, Publisher, Series, Volume
from whakoom_scraper.scrapers._helpers import leading_int, parse_decimal, text_or_none

log = logging.getLogger(__name__)

_BAR_CLASS = re.compile(r"bar-(\d+)")
_BAR_WIDTH = re.compile(r"width:\s*(\d+)")
_VOL_NUMBER = re.compile(r"(\d+)")


def parse_series_page(
    html: str,
    *,
    whakoom_series_id: int,
    slug: str,
    url: str,
) -> Series:
    """Parse a series page into a :class:`Series`.

    Args:
        html: Raw HTML of the ``/ediciones/{id}/{slug}`` page.
        whakoom_series_id: The numeric series id (from the URL the stage fetched).
        slug: The series slug (from the URL).
        url: The full series URL.

    Returns:
        A populated :class:`Series`. Optional fields are ``None`` when absent on
        the page; required structural fields raise nothing but log warnings when
        missing.
    """
    selector = Selector(text=html)

    rating, rating_count = _parse_rating(selector)
    series = Series(
        whakoom_series_id=whakoom_series_id,
        slug=slug,
        url=url,
        name=text_or_none(selector.css("h1::text").get()),
        original_title=_parse_original_title(selector),
        publisher=_parse_publisher(selector),
        status=text_or_none(selector.css("p.status::text").get()),
        format=text_or_none(selector.css("p.edition-type::text").get()),
        language=_parse_language(selector),
        volumes_count=_parse_volumes_count(selector),
        rating=rating,
        rating_count=rating_count,
        rating_distribution=_parse_distribution(selector),
        ownership_count=_parse_ownership(selector),
        synopsis=_parse_synopsis(selector),
        authors=_parse_authors(selector),
        volumes=_parse_volumes(selector),
    )
    return series


def _parse_publisher(selector: Selector) -> Publisher | None:
    """Extract the publisher link as a :class:`Publisher`."""
    node = selector.css('a[href*="/publisher/"]')
    if not node:
        return None
    name = text_or_none(node.css("::text").get())
    href = node.attrib.get("href", "")
    whakoom_id = _id_from_path(href)
    if name is None:
        return None
    return Publisher(name=name, whakoom_id=whakoom_id, url=text_or_none(href))


def _parse_volumes_count(selector: Selector) -> int | None:
    """Extract the advertised volume count (``"N cómics"``)."""
    node = selector.css('p[class$="-issues"]')
    if node:
        count = leading_int(node.css("::text").get())
        if count is not None:
            return count
    for text in selector.xpath('//p[contains(text(), "\u00f3mics")]/text()').getall():
        count = leading_int(text)
        if count is not None:
            return count
    return None


def _parse_rating(selector: Selector) -> tuple[float | None, int | None]:
    """Extract (rating, rating_count) from the votes info item.

    The value is read in European comma form (``"4,3"``) and falls back to the
    ``stars-value`` itemprop (dot form ``"4.3"``).
    """
    li_list = selector.xpath('//li[span[contains(@class, "title")][contains(., "votos")]]')
    if not li_list:
        return None, None
    li = li_list[0]
    title = text_or_none(li.css(".title::text").get()) or ""
    count = leading_int(title)
    raw = li.xpath('.//span[contains(@class, "value")]/text()').get()
    rating = parse_decimal(raw)
    if rating is None:
        rating = parse_decimal(li.css(".stars-value::text").get(), dot=True)
    return rating, count


def _parse_ownership(selector: Selector) -> int | None:
    """Extract the ownership count from the ``"Lo tienen"`` info item."""
    li_list = selector.xpath('//li[span[contains(@class, "title")][contains(., "Lo tienen")]]')
    if not li_list:
        return None
    return leading_int(li_list[0].xpath('.//span[contains(@class, "value")]/text()').get())


def _parse_language(selector: Selector) -> str | None:
    """Extract the language label from the flag info item."""
    li_list = selector.xpath('//li[span[contains(@class, "value")][contains(@class, "flag")]]')
    if not li_list:
        return None
    return text_or_none(li_list[0].css(".title::text").get())


def _parse_distribution(selector: Selector) -> dict[str, int] | None:
    """Extract the star-rating distribution from the ``.rates-chart`` bars."""
    distribution: dict[str, int] = {}
    for bar_node in selector.css(".rates-chart span[class^='bar-']"):
        cls = bar_node.attrib.get("class", "")
        style = bar_node.attrib.get("style", "")
        star = _BAR_CLASS.search(cls)
        pct = _BAR_WIDTH.search(style)
        if star and pct:
            distribution[star.group(1)] = int(pct.group(1))
    return distribution or None


def _parse_synopsis(selector: Selector) -> str | None:
    """Extract the synopsis paragraph following the ``Argumento`` heading."""
    node = selector.xpath('//*[contains(@class, "wiki-text")]//h2[contains(text(), "Argumento")]/following-sibling::p[1]')
    if not node:
        return None
    return text_or_none(node[0].css("::text").get())


def _parse_authors(selector: Selector) -> list[Author]:
    """Extract authors from the ``Autores`` section."""
    links = selector.xpath('//h3[contains(@class, "autores")]/following-sibling::p//a[contains(@href, "/autores/")]')
    authors: list[Author] = []
    for link in links:
        name = text_or_none(link.css("::text").get())
        if name is None:
            continue
        href = link.attrib.get("href", "")
        authors.append(Author(name=name, whakoom_id=_id_from_path(href), url=text_or_none(href)))
    return authors


def _parse_volumes(selector: Selector) -> list[Volume]:
    """Extract the same-edition volume list."""
    volumes: list[Volume] = []
    for node in selector.css("ul.v2-cover-list.same-edition li"):
        href = node.css("a.title::attr(href)").get()
        if not href:
            continue
        volume_slug = href.split("/")[2]
        number = _parse_issue_number(node.css(".issue-number::text").get(), href)
        title = text_or_none(node.css("a.title::attr(title)").get())
        cover_url = text_or_none(node.css("img::attr(src)").get())
        volumes.append(
            Volume(
                volume_slug=volume_slug,
                number=number,
                title=title,
                cover_url=cover_url,
            )
        )
    return volumes


def _parse_issue_number(text: str | None, href: str) -> int | None:
    """Parse a volume number from ``#N`` text, falling back to the URL tail."""
    if text is not None:
        match = _VOL_NUMBER.search(text)
        if match:
            return int(match.group(1))
    tail = href.rstrip("/").rsplit("/", 1)[-1]
    match = _VOL_NUMBER.search(tail)
    return int(match.group(1)) if match else None


def _parse_original_title(selector: Selector) -> str | None:
    """Best-effort extraction of the original title (``None`` when absent)."""
    node = selector.xpath('//dt[contains(text(), "Título original")]/following-sibling::dd[1]')
    if not node:
        return None
    return text_or_none(node[0].css("::text").get())


def _id_from_path(href: str) -> int | None:
    """Pull the numeric id segment from a ``/publisher/{id}/...`` or ``/autores/{id}/...`` path."""
    segments = href.split("/")
    if len(segments) < 3:
        return None
    try:
        return int(segments[2])
    except ValueError:
        return None
