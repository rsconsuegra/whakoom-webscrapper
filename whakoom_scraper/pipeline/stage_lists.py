"""Stage 1: scrape the profile lists index and upsert every list card.

Fetches ``/{profile}/lists/`` and records each discovered list card via
:func:`~whakoom_scraper.store.repositories.upsert_list`. No contents are
scraped here — that is Stage 2's job.
"""

from __future__ import annotations

import logging

from whakoom_scraper.config import Settings
from whakoom_scraper.http.archive import save_raw
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline._runtime import (
    STAGE_ERRORS,
    lists_index_allowed,
    owned_session_db,
)
from whakoom_scraper.scrapers.lists_index import parse_lists_index
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    close_run,
    create_run,
    invalidate_lists,
    upsert_list,
)

log = logging.getLogger(__name__)


def run_lists(
    settings: Settings,
    *,
    reset: bool = False,
    session: WhakoomSession | None = None,
    db: Database | None = None,
) -> int:
    """Run Stage 1: scrape the profile lists index.

    Owns (and closes) a :class:`WhakoomSession` and/or :class:`Database` when
    they are not supplied by the caller, so production CLI use needs no extra
    plumbing while tests inject pre-built instances.

    Args:
        settings: Runtime settings.
        reset: When True, re-mark every list as ``pending`` (and clear
            ``scraped_at``) before fetching the index, forcing a full refresh.
        session: Optional pre-built session; when ``None`` one is built and
            owned by this call.
        db: Optional pre-opened database; when ``None`` one is opened and owned
            by this call.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    with owned_session_db(settings, session, db) as (sess, store):
        return _run_lists(settings, reset, sess, store)


def _run_lists(settings: Settings, reset: bool, session: WhakoomSession, db: Database) -> int:
    """Fetch the lists index, upsert cards, and record a scrape run.

    Args:
        settings: Runtime settings.
        reset: Whether to invalidate existing lists before fetching.
        session: Live Whakoom session.
        db: Open database handle.

    Returns:
        ``0`` on success, ``1`` on failure.
    """
    if reset:
        invalidate_lists(db)
        db.commit()

    if not lists_index_allowed(session, settings):
        log.error("robots.txt denies /%s/lists/ — aborting lists stage", settings.profile)
        return 1

    run_id = create_run(db, "lists")
    db.commit()

    try:
        resp = session.get(f"/{settings.profile}/lists/")
        if settings.save_raw:
            save_raw(settings.raw_dir, "lists", "GET", str(resp.url), resp.content)
        lists_ = parse_lists_index(resp.text)
        for list_ in lists_:
            upsert_list(db, list_)
        db.commit()
        close_run(db, run_id, "completed", items_processed=len(lists_), items_failed=0)
        db.commit()
        log.info("lists: upserted %d list cards", len(lists_))
        return 0
    except STAGE_ERRORS as exc:
        close_run(db, run_id, "failed", items_processed=0, items_failed=0, notes=str(exc))
        db.commit()
        log.error("lists stage failed: %s", exc)
        return 1
