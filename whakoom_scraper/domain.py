"""Domain dataclasses for the Whakoom V2 pipeline.

These models are framework-free: parsers produce them, repositories persist
them. External identifiers always carry a ``whakoom_*`` prefix; surrogate
database ``id`` values are never stored in these objects across namespaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(kw_only=True)
class List:
    """A Whakoom list card from the profile lists index."""

    whakoom_list_id: int
    name: str
    url: str
    user_profile: str = "deirdre"
    description: str | None = None
    comic_count: int | None = None
    likes: int | None = None


@dataclass(kw_only=True)
class ListItem:
    """A single entry within a list, at a given position."""

    list_id: int
    position: int
    volume_slug: str
    volume_url: str
    whakoom_publication_id: int | None = None
    volume_number: int | None = None
    publisher: str | None = None
    series_id: int | None = None


@dataclass(kw_only=True)
class Publisher:
    """A publisher, optionally tied to a Whakoom publisher page."""

    name: str
    whakoom_id: int | None = None
    url: str | None = None


@dataclass(kw_only=True)
class Author:
    """A creator with an optional role within a series."""

    name: str
    role: str = "author"
    whakoom_id: int | None = None
    url: str | None = None


@dataclass(kw_only=True)
class Volume:
    """A published volume belonging to a series."""

    volume_slug: str
    series_id: int | None = None
    number: int | None = None
    title: str | None = None
    publisher: str | None = None
    cover_url: str | None = None


@dataclass(kw_only=True)
class Series:
    """A series as published on its ``/ediciones/`` page."""

    whakoom_series_id: int
    slug: str
    url: str
    name: str | None = None
    original_title: str | None = None
    publisher: Publisher | None = None
    status: str | None = None
    format: str | None = None
    language: str | None = None
    volumes_count: int | None = None
    rating: float | None = None
    rating_count: int | None = None
    rating_distribution: dict[str, int] | None = None
    ownership_count: int | None = None
    synopsis: str | None = None
    scrape_status: str = "pending"
    authors: list[Author] = field(default_factory=list)
    volumes: list[Volume] = field(default_factory=list)


@dataclass(kw_only=True)
class Observation:
    """An append-only snapshot of a series' popularity metrics per run."""

    series_id: int
    run_id: int
    rating: float | None = None
    rating_count: int | None = None
    rating_distribution: dict[str, int] | None = None
    ownership_count: int | None = None
    volumes_count: int | None = None
    status: str | None = None


@dataclass(frozen=True, kw_only=True)
class SeriesRef:
    """The minimum identity needed to stub a series after resolution.

    ``name`` may be ``None``: the pure redirect fallback yields no series name
    without a second request, and one request per unique slug is a hard
    constraint (V2 §11). The name is filled wherever parseable and completed
    during Stage 4.
    """

    whakoom_series_id: int
    slug: str
    url: str
    name: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReconcileResult:
    """Outcome of replacing a list's items with a freshly fetched set.

    ``removed_slugs`` lists slugs present in the previous version of the list
    that are gone now; ``written`` and ``removed`` are their counts. Stages log
    a warning and record the delta when anything changed, but proceed.
    """

    previous_count: int
    new_count: int
    written: int
    removed: int
    removed_slugs: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ListPageMeta:
    """Header metadata parsed from a list-detail page.

    ``name`` and ``comic_count`` are the advertised list title and comic count
    rendered in the page header; either may be absent on malformed pages.
    """

    name: str | None = None
    comic_count: int | None = None
