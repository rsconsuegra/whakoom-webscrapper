"""Stage 4: scrape full series data from public ``/ediciones/`` pages.

For each pending series the stage fetches the series page, parses it, and in a
single transaction upserts the publisher, series, volumes, authors/junction,
and one ``series_observations`` snapshot, then marks the series ``completed``.

Per-series fail + continue (owner decision, 2026-08-02): a transient error or
parse/store failure marks that series ``failed`` and the stage keeps going.
Only a robots denial aborts the whole stage.

Exit codes:
    * 0 — completed (some series may be ``failed``; see the run notes)
    * 1 — fatal (robots.txt denies ``/ediciones/``)
"""

from __future__ import annotations

import logging

from whakoom_scraper.config import Settings
from whakoom_scraper.constants import BASE_URL
from whakoom_scraper.domain import Observation, Series
from whakoom_scraper.http.archive import save_raw
from whakoom_scraper.http.policy import RobotsPolicy
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline._runtime import STAGE_ERRORS, owned_session_db
from whakoom_scraper.scrapers.series_page import parse_series_page
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    RecordMissingError,
    close_run,
    create_run,
    get_all_series,
    get_pending_series,
    get_series_row_id,
    insert_observation,
    link_series_author,
    set_series_status,
    upsert_author,
    upsert_publisher,
    upsert_series,
    upsert_volumes,
)

log = logging.getLogger(__name__)

SERIES_OK = 0
SERIES_FATAL = 1

#: Stage errors plus the post-upsert lookup miss, both handled as per-series failures.
_SERIES_ERRORS: tuple[type[BaseException], ...] = (*STAGE_ERRORS, RecordMissingError)


def run_series(
    settings: Settings,
    *,
    force: bool = False,
    limit: int | None = None,
    session: WhakoomSession | None = None,
    db: Database | None = None,
) -> int:
    """Run Stage 4: scrape series pages.

    Owns (and closes) a :class:`WhakoomSession` and/or :class:`Database` when
    they are not supplied by the caller, so production CLI use needs no extra
    plumbing while tests inject pre-built instances.

    Args:
        settings: Runtime settings.
        force: When True, re-scrape every series (pending, failed, and
            completed); the default processes only ``pending`` series.
        limit: Optional cap on the number of series processed.
        session: Optional pre-built session (tests); built and closed when None.
        db: Optional injected database (tests); built and closed when None.

    Returns:
        Process exit code (0 completed, 1 fatal).
    """
    with owned_session_db(settings, session, db) as (sess, store):
        return _run_series(settings, force, limit, sess, store)


def _run_series(
    settings: Settings,
    force: bool,
    limit: int | None,
    session: WhakoomSession,
    db: Database,
) -> int:
    """Scrape the selected series, recording the run and per-series outcomes.

    Args:
        settings: Runtime settings.
        force: Whether every series is re-scraped regardless of status.
        limit: Optional cap on the number of series processed.
        session: Live Whakoom session.
        db: Open database handle.

    Returns:
        ``0`` on completion, ``1`` when robots.txt denies the series path.
    """
    if not _ediciones_allowed(session, settings):
        log.error("robots.txt denies /ediciones/ — aborting series stage")
        return SERIES_FATAL

    selection = get_all_series(db) if force else get_pending_series(db)
    if limit is not None:
        selection = selection[:limit]
    if not selection:
        log.warning("series: no series to scrape")
        return SERIES_OK

    log.info("series: %d series to scrape (force=%s)", len(selection), force)
    run_id = create_run(db, "series")
    db.commit()

    processed = 0
    failed = 0
    for stub in selection:
        try:
            _scrape_one(settings, session, db, run_id, stub)
        except _SERIES_ERRORS as exc:
            log.warning("series %s: scrape failed: %s", stub.url, exc)
            _mark_series_failed(db, stub)
            failed += 1
            continue
        processed += 1

    notes = f"{failed} series marked failed; retry with --force" if failed else None
    close_run(db, run_id, "completed", items_processed=processed, items_failed=failed, notes=notes)
    db.commit()
    log.info("series: %d scraped, %d failed", processed, failed)
    return SERIES_OK


def _scrape_one(
    settings: Settings,
    session: WhakoomSession,
    db: Database,
    run_id: int,
    stub: Series,
) -> None:
    """Fetch, parse, and persist one series in a single transaction.

    Args:
        settings: Runtime settings.
        session: Live Whakoom session.
        db: Open database handle.
        run_id: The owning scrape run's surrogate id.
        stub: The pending series stub (identity fields only).

    Raises:
        Exception: Any :data:`STAGE_ERRORS` member or
            :class:`~whakoom_scraper.store.repositories.RecordMissingError`;
            the caller marks the series ``failed`` and continues.
    """
    resp = session.get(stub.url)
    resp.raise_for_status()
    if settings.save_raw:
        save_raw(settings.raw_dir, "series", "GET", str(resp.url), resp.content)
    parsed = parse_series_page(
        resp.text,
        whakoom_series_id=stub.whakoom_series_id,
        slug=stub.slug,
        url=stub.url,
    )
    with db.transaction():
        publisher_id = upsert_publisher(db, parsed.publisher) if parsed.publisher else None
        series_id = upsert_series(db, parsed, publisher_id)
        for volume in parsed.volumes:
            volume.series_id = series_id
        upsert_volumes(db, parsed.volumes)
        for author in parsed.authors:
            author_id = upsert_author(db, author)
            link_series_author(db, series_id, author_id, author.role)
        insert_observation(
            db,
            Observation(
                series_id=series_id,
                run_id=run_id,
                rating=parsed.rating,
                rating_count=parsed.rating_count,
                rating_distribution=parsed.rating_distribution,
                ownership_count=parsed.ownership_count,
                volumes_count=parsed.volumes_count,
                status=parsed.status,
            ),
        )


def _mark_series_failed(db: Database, stub: Series) -> None:
    """Mark a series ``failed`` after its scrape attempt errored.

    Runs outside the failed per-series transaction (already rolled back) and
    commits immediately so the status survives a later stage crash.

    Args:
        db: Open database handle.
        stub: The series stub that failed to scrape.
    """
    row_id = get_series_row_id(db, stub.whakoom_series_id)
    if row_id is None:
        log.error("series %d vanished; cannot mark failed", stub.whakoom_series_id)
        return
    set_series_status(db, row_id, "failed")
    db.commit()


def _ediciones_allowed(session: WhakoomSession, settings: Settings) -> bool:
    """Check whether robots.txt permits the public ``/ediciones/`` path.

    Args:
        session: Live Whakoom session used to fetch robots.txt.
        settings: Runtime settings.

    Returns:
        ``True`` if the series path may be requested.
    """
    policy = RobotsPolicy.from_session(
        session,
        base_url=BASE_URL,
        user_agent=settings.user_agent,
        allow_gated=settings.allow_gated_resolution,
    )
    return policy.is_allowed("/ediciones/")
