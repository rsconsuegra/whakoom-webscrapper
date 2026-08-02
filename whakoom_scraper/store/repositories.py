"""Typed repository functions over the Whakoom V2 schema.

Every function takes a :class:`Database` and uses named queries only; no raw SQL
is written in this module. Functions are single-statement helpers — the calling
stage owns transaction boundaries and calls :meth:`Database.commit`.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from whakoom_scraper.domain import (
    Author,
    List,
    ListItem,
    Observation,
    Publisher,
    ReconcileResult,
    Series,
    SeriesRef,
    Volume,
)
from whakoom_scraper.store.db import Database

SCRAPE_STATUSES = ("pending", "completed", "failed")
RUN_STATUSES = ("running", "completed", "failed", "aborted")


class RecordMissingError(RuntimeError):
    """Raised when a post-upsert lookup cannot find the row just written."""


def _list_from_row(row: sqlite3.Row) -> List:
    return List(
        whakoom_list_id=row["whakoom_list_id"],
        name=row["name"],
        url=row["url"],
        user_profile=row["user_profile"],
        description=row["description"],
        comic_count=row["comic_count"],
        likes=row["likes"],
    )


def _publisher_from_row(row: sqlite3.Row) -> Publisher:
    return Publisher(
        name=row["name"],
        whakoom_id=row["whakoom_id"],
        url=row["url"],
    )


def _author_from_row(row: sqlite3.Row) -> Author:
    return Author(
        name=row["name"],
        whakoom_id=row["whakoom_id"],
        url=row["url"],
    )


def _series_from_row(row: sqlite3.Row) -> Series:
    distribution: dict[str, int] | None = None
    if row["rating_distribution"]:
        distribution = json.loads(row["rating_distribution"])
    return Series(
        whakoom_series_id=row["whakoom_series_id"],
        slug=row["slug"],
        url=row["url"],
        name=row["name"],
        original_title=row["original_title"],
        status=row["status"],
        format=row["format"],
        language=row["language"],
        volumes_count=row["volumes_count"],
        rating=row["rating"],
        rating_count=row["rating_count"],
        rating_distribution=distribution,
        ownership_count=row["ownership_count"],
        synopsis=row["synopsis"],
        scrape_status=row["scrape_status"],
    )


def upsert_list(db: Database, list_: List) -> int:
    """Insert or update a list card by its Whakoom list id.

    Args:
        db: Database handle.
        list_: List domain object.

    Returns:
        The surrogate row id.

    Raises:
        RecordMissingError: If the post-upsert lookup cannot find the row.
    """
    db.execute(
        "lists",
        "upsert_list",
        (
            list_.whakoom_list_id,
            list_.name,
            list_.url,
            list_.user_profile,
            list_.description,
            list_.comic_count,
            list_.likes,
        ),
    )
    row = db.fetchone("lists", "get_list", (list_.whakoom_list_id,))
    if row is None:
        raise RecordMissingError(f"upsert_list: list whakoom_id={list_.whakoom_list_id} vanished after upsert")
    return int(row["id"])


def get_list(db: Database, whakoom_list_id: int) -> List | None:
    """Fetch a list by its Whakoom id.

    Args:
        db: Database handle.
        whakoom_list_id: Whakoom list id.

    Returns:
        The list, or ``None`` if absent.
    """
    row = db.fetchone("lists", "get_list", (whakoom_list_id,))
    return _list_from_row(row) if row else None


def get_lists(db: Database) -> list[List]:
    """Fetch all lists in insertion order.

    Args:
        db: Database handle.

    Returns:
        Every list.
    """
    return [_list_from_row(row) for row in db.fetchall("lists", "get_lists")]


def get_pending_lists(db: Database, *, include_failed: bool = False) -> list[List]:
    """Fetch lists that still need their contents scraped.

    Args:
        db: Database handle.
        include_failed: When True, also include lists marked ``failed`` so a
            ``--force`` retry can pick them up; the default excludes them.

    Returns:
        Lists whose ``scrape_status`` is ``pending`` (and ``failed`` when
        ``include_failed`` is True).
    """
    query_name = "get_pending_lists_with_failed" if include_failed else "get_pending_lists"
    return [_list_from_row(row) for row in db.fetchall("lists", query_name)]


def get_failed_lists(db: Database) -> list[List]:
    """Fetch lists whose last scrape attempt failed.

    Args:
        db: Database handle.

    Returns:
        Lists whose ``scrape_status`` is ``failed``.
    """
    return [_list_from_row(row) for row in db.fetchall("lists", "get_failed_lists")]


def mark_list_status(db: Database, whakoom_list_id: int, status: str) -> None:
    """Set a list's scrape status.

    Args:
        db: Database handle.
        whakoom_list_id: Whakoom list id.
        status: One of ``pending``, ``completed``, ``failed``.

    Raises:
        ValueError: If the status is not a valid scrape status.
    """
    if status not in SCRAPE_STATUSES:
        raise ValueError(f"Invalid list scrape status: {status}")
    db.execute("lists", "mark_list_status", (status, whakoom_list_id))


def reset_lists_pending(db: Database) -> None:
    """Mark every completed list as pending again.

    Args:
        db: Database handle.
    """
    db.execute("lists", "reset_lists_pending")


def invalidate_lists(db: Database) -> None:
    """Reset every list back to ``pending`` for a full refresh (``--reset``).

    Unlike :func:`reset_lists_pending`, this also flips ``failed`` rows back to
    ``pending`` and clears ``scraped_at`` so the next run re-scrapes everything.

    Args:
        db: Database handle.
    """
    db.execute("lists", "invalidate_lists")


def replace_list_items(db: Database, list_id: int, items: Sequence[ListItem]) -> ReconcileResult:
    """Replace a list's items with the freshly fetched version of that list.

    Per-list reconciliation (V2 §10 Stage 2): the fetched set is the source of
    truth. Stored rows no longer present are deleted, every fetched item is
    inserted, and previously resolved ``series_id`` links are preserved via the
    slug→series map. Cross-list links are reused through a global slug→series
    map so a slug resolved in list A is not re-requested in list B. Because
    inserts run against an empty list, the ``UNIQUE (list_id, position)``
    constraint can no longer collide when items are reordered, shrunk, or
    swapped between runs.

    Args:
        db: Database handle.
        list_id: Surrogate list row id.
        items: ListItem domain objects for the whole list, after all pages.

    Returns:
        A ReconcileResult describing the before/after counts and removed slugs.
    """
    previous = {
        row["volume_slug"]: row["series_id"] for row in db.fetchall("list_items", "get_list_item_series_map", (list_id,))
    }
    global_map = get_global_slug_series_map(db)
    db.execute("list_items", "delete_list_items_for_list", (list_id,))
    rows: list[tuple[object, ...]] = []
    for item in items:
        series_id = item.series_id or previous.get(item.volume_slug) or global_map.get(item.volume_slug)
        rows.append(
            (
                list_id,
                item.position,
                item.volume_slug,
                item.whakoom_publication_id,
                item.volume_url,
                item.volume_number,
                item.publisher,
                series_id,
            )
        )
    db.executemany("list_items", "insert_list_item", rows)
    new_slugs = {item.volume_slug for item in items}
    removed_slugs = tuple(sorted(previous.keys() - new_slugs))
    return ReconcileResult(
        previous_count=len(previous),
        new_count=len(items),
        written=len(rows),
        removed=len(removed_slugs),
        removed_slugs=removed_slugs,
    )


def get_global_slug_series_map(db: Database) -> dict[str, int]:
    """Build a global volume-slug → series-id map across every list.

    Used by :func:`replace_list_items` to reuse resolution links across lists
    and avoid re-requesting slugs already resolved elsewhere.

    Args:
        db: Database handle.

    Returns:
        Mapping of volume slug to resolved series row id.
    """
    return {str(row["volume_slug"]): int(row["series_id"]) for row in db.fetchall("list_items", "get_global_slug_series_map")}


def count_items_for_list(db: Database, list_id: int) -> int:
    """Count the items recorded for a list.

    Args:
        db: Database handle.
        list_id: Surrogate list row id.

    Returns:
        Number of items.
    """
    row = db.fetchone("list_items", "count_items_for_list", (list_id,))
    return int(row["n"]) if row else 0


def get_unresolved_slugs(db: Database) -> list[str]:
    """Fetch distinct volume slugs not yet linked to a series.

    Args:
        db: Database handle.

    Returns:
        Slugs in alphabetical order.
    """
    return [str(row["volume_slug"]) for row in db.fetchall("list_items", "get_unresolved_slugs")]


def set_item_series(db: Database, volume_slug: str, series_id: int) -> None:
    """Link a list item to a resolved series.

    Args:
        db: Database handle.
        volume_slug: Volume slug of the list item.
        series_id: Surrogate series row id.
    """
    db.execute("list_items", "set_item_series", (series_id, volume_slug))


def upsert_publisher(db: Database, publisher: Publisher) -> int:
    """Insert or update a publisher by name.

    Args:
        db: Database handle.
        publisher: Publisher domain object.

    Returns:
        The surrogate row id.

    Raises:
        RecordMissingError: If the post-upsert lookup cannot find the row.
    """
    db.execute(
        "series",
        "upsert_publisher",
        (publisher.whakoom_id, publisher.name, publisher.url),
    )
    row = db.fetchone("series", "get_publisher_id_by_name", (publisher.name,))
    if row is None:
        raise RecordMissingError(f"upsert_publisher: publisher name={publisher.name!r} vanished after upsert")
    return int(row["id"])


def get_publisher_by_name(db: Database, name: str) -> Publisher | None:
    """Fetch a publisher by name.

    Args:
        db: Database handle.
        name: Publisher name.

    Returns:
        The publisher, or ``None`` if absent.
    """
    row = db.fetchone("series", "get_publisher_by_name", (name,))
    return _publisher_from_row(row) if row else None


def upsert_author(db: Database, author: Author) -> int:
    """Insert or update an author, deduplicating by Whakoom id then name.

    Args:
        db: Database handle.
        author: Author domain object.

    Returns:
        The surrogate row id.

    Raises:
        RecordMissingError: If the post-upsert lookup cannot find the row.
    """
    if author.whakoom_id is not None:
        db.execute(
            "series",
            "upsert_author",
            (author.whakoom_id, author.name, author.url),
        )
        row = db.fetchone("series", "get_author_id_by_whakoom_id", (author.whakoom_id,))
        if row is None:
            raise RecordMissingError(f"upsert_author: author whakoom_id={author.whakoom_id} vanished after upsert")
        return int(row["id"])
    existing = db.fetchone("series", "get_author_id_by_name", (author.name,))
    if existing is not None:
        return int(existing["id"])
    db.execute("series", "upsert_author", (None, author.name, author.url))
    row = db.fetchone("series", "get_author_id_by_name", (author.name,))
    if row is None:
        raise RecordMissingError(f"upsert_author: author name={author.name!r} vanished after upsert")
    return int(row["id"])


def get_author_by_name(db: Database, name: str) -> Author | None:
    """Fetch an author by name.

    Args:
        db: Database handle.
        name: Author name.

    Returns:
        The author, or ``None`` if absent.
    """
    row = db.fetchone("series", "get_author_by_name", (name,))
    return _author_from_row(row) if row else None


def link_series_author(db: Database, series_id: int, author_id: int, role: str) -> None:
    """Link a series to an author with a role, if not already linked.

    Args:
        db: Database handle.
        series_id: Surrogate series row id.
        author_id: Surrogate author row id.
        role: Role text (e.g. ``guion``, ``dibujo``, ``author``).
    """
    db.execute("series", "link_series_author", (series_id, author_id, role))


def stub_series(db: Database, ref: SeriesRef) -> int:
    """Create a minimal series row if the Whakoom series id is unknown.

    The name is optional and may be ``None``: the pure redirect fallback yields
    no series name without a second request, and one request per unique slug is
    a hard constraint (V2 §11). Stage 4 fills the name later.

    Args:
        db: Database handle.
        ref: SeriesRef with at least id, slug, url and optionally a name.

    Returns:
        The surrogate row id.

    Raises:
        RecordMissingError: If the post-stub lookup cannot find the row.
    """
    db.execute(
        "series",
        "stub_series",
        (ref.whakoom_series_id, ref.slug, ref.url, ref.name),
    )
    row = db.fetchone("series", "get_series_id", (ref.whakoom_series_id,))
    if row is None:
        raise RecordMissingError(f"stub_series: series whakoom_id={ref.whakoom_series_id} vanished after stub")
    return int(row["id"])


def get_series(db: Database, whakoom_series_id: int) -> Series | None:
    """Fetch a series by its Whakoom id.

    Args:
        db: Database handle.
        whakoom_series_id: Whakoom series id.

    Returns:
        The series, or ``None`` if absent.
    """
    row = db.fetchone("series", "get_series", (whakoom_series_id,))
    return _series_from_row(row) if row else None


def get_pending_series(db: Database, *, include_failed: bool = False) -> list[Series]:
    """Fetch series whose full details have not been scraped.

    Args:
        db: Database handle.
        include_failed: When True, also include series marked ``failed`` so a
            ``--force`` retry can pick them up; the default excludes them.

    Returns:
        Series whose ``scrape_status`` is ``pending`` (and ``failed`` when
        ``include_failed`` is True).
    """
    query_name = "get_pending_series_with_failed" if include_failed else "get_pending_series"
    return [_series_from_row(row) for row in db.fetchall("series", query_name)]


def get_failed_series(db: Database) -> list[Series]:
    """Fetch series whose last scrape attempt failed.

    Args:
        db: Database handle.

    Returns:
        Series whose ``scrape_status`` is ``failed``.
    """
    return [_series_from_row(row) for row in db.fetchall("series", "get_failed_series")]


def upsert_series(db: Database, series: Series, publisher_id: int | None) -> int:
    """Insert or update a fully scraped series, marking it completed.

    Args:
        db: Database handle.
        series: Series domain object with all scraped fields.
        publisher_id: Surrogate publisher row id, or ``None``.

    Returns:
        The surrogate row id.

    Raises:
        RecordMissingError: If the post-upsert lookup cannot find the row.
    """
    db.execute(
        "series",
        "upsert_series",
        (
            series.whakoom_series_id,
            series.slug,
            series.url,
            series.name,
            series.original_title,
            publisher_id,
            series.status,
            series.format,
            series.language,
            series.volumes_count,
            series.rating,
            series.rating_count,
            json.dumps(series.rating_distribution) if series.rating_distribution else None,
            series.ownership_count,
            series.synopsis,
        ),
    )
    row = db.fetchone("series", "get_series_id", (series.whakoom_series_id,))
    if row is None:
        raise RecordMissingError(f"upsert_series: series whakoom_id={series.whakoom_series_id} vanished after upsert")
    return int(row["id"])


def set_series_status(db: Database, series_id: int, status: str) -> None:
    """Set a series' scrape status.

    Args:
        db: Database handle.
        series_id: Surrogate series row id.
        status: One of ``pending``, ``completed``, ``failed``.

    Raises:
        ValueError: If the status is not a valid scrape status.
    """
    if status not in SCRAPE_STATUSES:
        raise ValueError(f"Invalid series scrape status: {status}")
    db.execute("series", "set_series_status", (status, series_id))


def upsert_volumes(db: Database, volumes: Sequence[Volume]) -> int:
    """Insert or update volume rows in bulk.

    Args:
        db: Database handle.
        volumes: Volume domain objects.

    Returns:
        The number of rows affected.
    """
    rows: list[tuple[object, ...]] = []
    for volume in volumes:
        if volume.series_id is None:
            raise ValueError(f"Volume '{volume.volume_slug}' has no series_id")
        rows.append(
            (
                volume.volume_slug,
                volume.series_id,
                volume.number,
                volume.title,
                volume.publisher,
                volume.cover_url,
            )
        )
    return int(db.executemany("volumes", "upsert_volume", rows).rowcount)


def insert_observation(db: Database, observation: Observation) -> None:
    """Record a per-run popularity snapshot for a series.

    Args:
        db: Database handle.
        observation: Observation domain object.
    """
    db.execute(
        "observations",
        "insert_observation",
        (
            observation.series_id,
            observation.run_id,
            observation.rating,
            observation.rating_count,
            json.dumps(observation.rating_distribution) if observation.rating_distribution else None,
            observation.ownership_count,
            observation.volumes_count,
            observation.status,
        ),
    )


def create_run(db: Database, stage: str) -> int:
    """Open a new scrape run.

    Args:
        db: Database handle.
        stage: Stage name that owns the run.

    Returns:
        The new run's surrogate row id.
    """
    cursor = db.execute("runs", "create_run", (stage,))
    rowid = cursor.lastrowid
    if rowid is None:
        raise RuntimeError("No run row id returned after INSERT")
    return int(rowid)


def close_run(
    db: Database,
    run_id: int,
    status: str,
    items_processed: int,
    items_failed: int,
    notes: str | None = None,
) -> None:
    """Close a scrape run with its outcome counters.

    Args:
        db: Database handle.
        run_id: Surrogate run row id.
        status: One of ``completed``, ``failed``, ``aborted``.
        items_processed: Number of items processed successfully.
        items_failed: Number of items that failed.
        notes: Free-form notes, or ``None``.

    Raises:
        ValueError: If the status is not a valid run status.
    """
    if status not in RUN_STATUSES:
        raise ValueError(f"Invalid run status: {status}")
    db.execute(
        "runs",
        "close_run",
        (status, items_processed, items_failed, notes, run_id),
    )
