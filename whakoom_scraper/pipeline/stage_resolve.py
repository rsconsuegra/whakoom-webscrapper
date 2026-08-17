"""Stage 3: resolve volume slugs to their parent series (authenticated).

Per unique unresolved ``list_items.volume_slug`` this stage calls the gated
``/pwkws.asmx/QuickView`` (primary) or ``/comics/{slug}/`` (fallback) to obtain
the parent series id, links the item, and stubs the series row. It is the only
stage that touches robots-disallowed, login-gated paths, so it is gated behind
``WK_ALLOW_GATED_RESOLUTION`` and a valid cookie session.

Exit codes:
    * 0 — completed (some slugs may be unresolved; see data/review_unresolved.csv)
    * 1 — fatal (robots/config denied the gated path, or nothing to resolve)
    * 3 — session expired (re-export cookies and re-run; nothing is lost)
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Sequence

from whakoom_scraper.config import PROJECT_ROOT, Settings
from whakoom_scraper.http.resolve import SessionExpiredError, resolve_series_id
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline._runtime import (
    STAGE_ERRORS,
    gated_resolution_allowed,
    owned_session_db,
)
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    close_run,
    create_run,
    get_unresolved_slugs,
    set_item_series,
    stub_series,
)

log = logging.getLogger(__name__)

REVIEW_CSV = PROJECT_ROOT / "data" / "review_unresolved.csv"

RESOLVE_OK = 0
RESOLVE_FATAL = 1
RESOLVE_SESSION_EXPIRED = 3


def run_resolve(
    settings: Settings,
    *,
    limit: int | None = None,
    session: WhakoomSession | None = None,
    db: Database | None = None,
) -> int:
    """Run the resolve stage.

    Args:
        settings: Runtime settings.
        limit: Optional cap on the number of slugs to process.
        session: Optional injected session (tests); built and closed when None.
        db: Optional injected database (tests); built and closed when None.

    Returns:
        Process exit code (0 completed, 1 fatal, 3 session expired).
    """
    with owned_session_db(settings, session, db) as (sess, store):
        return _run_resolve(settings, limit, sess, store)


def _run_resolve(
    settings: Settings,
    limit: int | None,
    session: WhakoomSession,
    db: Database,
) -> int:
    """Resolve slugs to series, recording the run and writing the review file."""
    if not gated_resolution_allowed(session, settings):
        log.error(
            "resolve aborted: /comics/ is robots-disallowed; set WK_ALLOW_GATED_RESOLUTION=1 and provide a valid cookie session"
        )
        return RESOLVE_FATAL

    slugs = get_unresolved_slugs(db)
    if limit is not None:
        slugs = slugs[:limit]
    if not slugs:
        log.warning("resolve: no unresolved slugs to process")
        return RESOLVE_OK

    log.info("resolve: %d unique slug(s) to resolve", len(slugs))
    run_id = create_run(db, "resolve")
    db.commit()

    resolved = 0
    unresolved: list[str] = []
    try:
        for slug in slugs:
            try:
                ref = resolve_series_id(session, slug)
                if ref is None:
                    log.warning("resolve slug %r: no parent series found", slug)
                    unresolved.append(slug)
                    continue
                with db.transaction():
                    series_id = stub_series(db, ref)
                    set_item_series(db, slug, series_id)
            except STAGE_ERRORS as exc:
                log.error("resolve slug %r failed: %s", slug, exc)
                unresolved.append(slug)
                continue
            resolved += 1
    except SessionExpiredError as exc:
        log.error("session expired at %s — re-export cookies and re-run", exc.url)
        close_run(
            db,
            run_id,
            "aborted",
            items_processed=resolved,
            items_failed=len(slugs) - resolved,
            notes=f"session expired: {exc.url}",
        )
        db.commit()
        _write_review(unresolved)
        return RESOLVE_SESSION_EXPIRED

    notes = f"{len(unresolved)} unresolved; see {REVIEW_CSV}" if unresolved else None
    close_run(
        db,
        run_id,
        "completed",
        items_processed=resolved,
        items_failed=len(unresolved),
        notes=notes,
    )
    db.commit()
    _write_review(unresolved)
    log.info("resolve: %d resolved, %d unresolved", resolved, len(unresolved))
    return RESOLVE_OK


def _write_review(unresolved: Sequence[str]) -> None:
    """Write unresolved slugs to the review CSV, or clear a stale file.

    On a clean run (no unresolved slugs) any pre-existing review CSV is removed
    so it cannot misrepresent the current state.

    Args:
        unresolved: Slugs that could not be resolved this run.
    """
    if not unresolved:
        if REVIEW_CSV.exists():
            REVIEW_CSV.unlink()
            log.info("resolve: cleared stale review file %s", REVIEW_CSV)
        return
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["volume_slug"])
        for slug in unresolved:
            writer.writerow([slug])
    log.warning("resolve: %d unresolved slug(s) written to %s", len(unresolved), REVIEW_CSV)
