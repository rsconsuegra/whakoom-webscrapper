"""Stage 2: scrape list contents (server page + paginated JSON).

For each target list: GET its detail page (first ~50 server-rendered items),
then POST the ``SeriesPage`` endpoint for pages 2, 3, … until the server
signals the end (``ExtraInfo == "0"`` or empty ``Html``). Persist the full set
in one transaction and reconcile the parsed count against the list's advertised
``comic_count``.
"""

from __future__ import annotations

import json
import logging

from whakoom_scraper.config import Settings
from whakoom_scraper.constants import BASE_URL, LISTDETAIL_PAGE_URL
from whakoom_scraper.domain import List
from whakoom_scraper.http.archive import save_raw
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline._runtime import (
    STAGE_ERRORS,
    lists_index_allowed,
    owned_session_db,
)
from whakoom_scraper.scrapers.list_detail import parse_list_page, parse_series_page_json
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    close_run,
    create_run,
    get_list,
    get_lists,
    get_pending_lists,
    mark_list_status,
    replace_list_items,
    upsert_list,
)

log = logging.getLogger(__name__)


def run_list_detail(
    settings: Settings,
    *,
    list_id: int | None = None,
    scrape_all: bool = False,
    session: WhakoomSession | None = None,
    db: Database | None = None,
) -> int:
    """Run Stage 2: scrape list contents with pagination.

    Owns (and closes) a :class:`WhakoomSession` and/or :class:`Database` when
    they are not supplied by the caller.

    Args:
        settings: Runtime settings.
        list_id: When set, scrape only the list with this Whakoom id.
        scrape_all: When True (and ``list_id`` is None), scrape every known
            list; otherwise scrape only pending lists.
        session: Optional pre-built session; when ``None`` one is built and
            owned by this call.
        db: Optional pre-opened database; when ``None`` one is opened and owned
            by this call.

    Returns:
        ``0`` when the stage completes (per-list failures are recorded, not
        fatal); ``1`` only on a fatal setup error (e.g. robots-denied).
    """
    with owned_session_db(settings, session, db) as (sess, store):
        return _run_list_detail(settings, list_id, scrape_all, sess, store)


def _resolve_targets(db: Database, list_id: int | None, scrape_all: bool) -> list[List]:
    """Resolve the lists to scrape based on the selection flags.

    Args:
        db: Open database handle.
        list_id: Optional single Whakoom list id.
        scrape_all: Whether to scrape every known list when no id is given.

    Returns:
        The target lists (possibly empty).
    """
    if list_id is not None:
        single = get_list(db, list_id)
        return [single] if single is not None else []
    if scrape_all:
        return get_lists(db)
    return get_pending_lists(db)


def _scrape_one_list(
    settings: Settings,
    session: WhakoomSession,
    db: Database,
    list_: List,
) -> tuple[int, str | None]:
    """Scrape one list: fetch, paginate, persist, reconcile, mark status.

    Args:
        settings: Runtime settings.
        session: Live Whakoom session.
        db: Open database handle.
        list_: The list to scrape.

    Returns:
        A tuple of the number of parsed items and an optional mismatch note
        (present only when parsed count differs from the advertised
        ``comic_count``).
    """
    db_list_id = upsert_list(db, list_)
    db.commit()

    resp = session.get(list_.url)
    if settings.save_raw:
        save_raw(settings.raw_dir, "list-detail", "GET", str(resp.url), resp.content)

    _, page1_items = parse_list_page(resp.text, list_id=list_.whakoom_list_id)
    all_items = list(page1_items)

    next_page: int | None = 2
    while next_page is not None:
        payload = {"id": list_.whakoom_list_id, "f": 0, "p": next_page}
        resp = session.post(LISTDETAIL_PAGE_URL, json=payload)
        if settings.save_raw:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            save_raw(
                settings.raw_dir,
                "list-detail",
                "POST",
                BASE_URL + LISTDETAIL_PAGE_URL,
                resp.content,
                request_body=body,
            )
        page_items, next_page = parse_series_page_json(
            resp.json(),
            list_id=list_.whakoom_list_id,
            start_position=len(all_items) + 1,
        )
        all_items.extend(page_items)

    note: str | None = None
    with db.transaction():
        replace_list_items(db, db_list_id, all_items)
        parsed = len(all_items)
        advertised = list_.comic_count
        if advertised is not None and parsed != advertised:
            mark_list_status(db, list_.whakoom_list_id, "pending")
            note = f"list {list_.whakoom_list_id}: parsed {parsed} != comic_count {advertised}"
            log.warning("list %s: parsed %d != comic_count %s", list_.whakoom_list_id, parsed, advertised)
        else:
            mark_list_status(db, list_.whakoom_list_id, "completed")

    return parsed, note


def _run_list_detail(
    settings: Settings,
    list_id: int | None,
    scrape_all: bool,
    session: WhakoomSession,
    db: Database,
) -> int:
    """Run the list-detail stage against resolved targets.

    Args:
        settings: Runtime settings.
        list_id: Optional single Whakoom list id.
        scrape_all: Whether to scrape every known list.
        session: Live Whakoom session.
        db: Open database handle.

    Returns:
        ``0`` on stage completion, ``1`` on fatal setup error.
    """
    if not lists_index_allowed(session, settings):
        log.error("robots.txt denies /%s/lists/ — aborting list-detail stage", settings.profile)
        return 1

    targets = _resolve_targets(db, list_id, scrape_all)
    if not targets:
        log.warning("list-detail: no target lists to scrape")
        return 0

    run_id = create_run(db, "list-detail")
    db.commit()

    items_processed = 0
    items_failed = 0
    notes_parts: list[str] = []
    for list_ in targets:
        try:
            parsed, note = _scrape_one_list(settings, session, db, list_)
        except STAGE_ERRORS as exc:
            items_failed += 1
            log.error("list %s failed: %s", list_.whakoom_list_id, exc)
            try:
                mark_list_status(db, list_.whakoom_list_id, "failed")
                db.commit()
            except STAGE_ERRORS:
                log.error("could not mark list %s as failed", list_.whakoom_list_id)
            continue
        items_processed += parsed
        if note is not None:
            notes_parts.append(note)

    close_run(
        db,
        run_id,
        "completed",
        items_processed=items_processed,
        items_failed=items_failed,
        notes="; ".join(notes_parts) if notes_parts else None,
    )
    db.commit()
    log.info(
        "list-detail: processed %d items across %d list(s), %d failed",
        items_processed,
        len(targets),
        items_failed,
    )
    return 0
