"""Tests for :mod:`whakoom_scraper.pipeline.stage_list_detail`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from whakoom_scraper.config import Settings
from whakoom_scraper.domain import List
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline.stage_list_detail import run_list_detail
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    count_items_for_list,
    get_list,
    upsert_list,
)
from whakoom_scraper.tests.conftest import ROBOTS_ALLOW_ALL, fast_settings, load_fixture

WINGS_URL = "/deirdre/lists/wings_116046"
SYNTH_URL = "/deirdre/lists/synthetic_999"


def _route_handler(
    *,
    get_html: str,
    post_payload: dict[str, object],
    get_path: str | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a handler routing robots, the GET page, and the POST SeriesPage.

    Args:
        get_html: HTML body returned for the list-detail GET.
        post_payload: JSON object returned for every SeriesPage POST.
        get_path: Optional path to match for the GET; when None, any non-robots
            GET returns ``get_html``.

    Returns:
        A MockTransport handler.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Route by path/method to canned responses."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.method == "POST":
            return httpx.Response(200, json=post_payload)
        if get_path is None or request.url.path == get_path:
            return httpx.Response(200, text=get_html)
        return httpx.Response(404, text=f"not found: {request.url.path}")

    return handler


def _status_of(db: Database, whakoom_list_id: int) -> str:
    """Read a list's scrape_status straight from the DB (test-only read).

    Args:
        db: Open database handle.
        whakoom_list_id: Whakoom list id.

    Returns:
        The list's ``scrape_status`` value.
    """
    row = db.connection.execute(
        "SELECT scrape_status FROM lists WHERE whakoom_list_id = ?",
        (whakoom_list_id,),
    ).fetchone()
    assert row is not None
    return str(row["scrape_status"])


def _latest_run_notes(db: Database) -> str | None:
    """Read the most recent scrape_run's notes (test-only read).

    Args:
        db: Open database handle.

    Returns:
        The notes text, or ``None``.
    """
    row = db.connection.execute(
        "SELECT notes FROM scrape_runs ORDER BY id DESC LIMIT 1",
    ).fetchone()
    return None if row is None else (row["notes"] if row["notes"] is None else str(row["notes"]))


def _seed_list(db: Database, list_: List) -> int:
    """Upsert a list and return its surrogate id.

    Args:
        db: Open database handle.
        list_: List to seed.

    Returns:
        The surrogate row id of the list.
    """
    db_list_id = upsert_list(db, list_)
    db.commit()
    return db_list_id


def test_single_page_wings_completes(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Single-page list: 10 items, status completed, first item fields correct."""
    db_list_id = _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=10,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), list_id=116046, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert count_items_for_list(database, db_list_id) == 10
    assert _status_of(database, 116046) == "completed"

    first = database.connection.execute(
        "SELECT volume_slug, publisher FROM list_items WHERE list_id = ? AND position = 1",
        (db_list_id,),
    ).fetchone()
    assert first is not None
    assert first["volume_slug"] == "81wm6"
    assert first["publisher"] == "Norma Editorial"


def test_multipage_accumulates_positions(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Multi-page: page-1 (2 items) + page-2 (1 item) → positions 1, 2, 3."""
    page1 = (
        "<html><body><h1><span>Synthetic</span> <small>3 Cómics</small></h1>"
        "<ul>"
        '<li data-item-id="100"><span class="title">'
        '<a href="/comics/AAA1/slug1/1">One</a></span>'
        '<span class="desc">Vol. 1, Pub A</span></li>'
        '<li data-item-id="101"><span class="title">'
        '<a href="/comics/AAA2/slug2/1">Two</a></span>'
        '<span class="desc">Vol. 2, Pub B</span></li>'
        "</ul></body></html>"
    )
    page2_html = (
        '<li data-item-id="102"><span class="title">'
        '<a href="/comics/AAA3/slug3/1">Three</a></span>'
        '<span class="desc">Vol. 3, Pub C</span></li>'
    )
    db_list_id = _seed_list(
        database,
        List(whakoom_list_id=999, name="Synthetic", url=SYNTH_URL, comic_count=3),
    )
    handler = _route_handler(
        get_html=page1,
        post_payload={"Html": page2_html, "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), list_id=999, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert count_items_for_list(database, db_list_id) == 3
    positions = [
        r["position"]
        for r in database.connection.execute(
            "SELECT position FROM list_items WHERE list_id = ? ORDER BY position",
            (db_list_id,),
        ).fetchall()
    ]
    assert positions == [1, 2, 3]
    assert _status_of(database, 999) == "completed"


def test_count_mismatch_leaves_pending_and_notes(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Parsed count != comic_count leaves the list pending and records a note."""
    _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=99,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), list_id=116046, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert _status_of(database, 116046) == "pending"
    notes = _latest_run_notes(database)
    assert notes is not None
    assert "116046" in notes
    assert "comic_count" in notes


def test_scrape_all_targets_every_list(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """``scrape_all=True`` scrapes every list regardless of status."""
    _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=10,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), scrape_all=True, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert _status_of(database, 116046) == "completed"


def test_pending_default_targets_pending_only(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """Default (no flags) scrapes only pending lists; completed ones are skipped."""
    db_list_id = _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=10,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert count_items_for_list(database, db_list_id) == 10


def test_unknown_list_id_is_noop(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """A list_id with no matching row returns 0 without scraping."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Fail loudly if any request beyond robots is made."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        raise AssertionError(f"unexpected request: {request.url.path}")

    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), list_id=404404, session=session, db=database)
    finally:
        session.close()

    assert code == 0


def test_robots_denied_returns_1(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """A robots.txt disallowing the lists path aborts the stage with code 1."""
    robots_deny = "User-agent: *\nDisallow: /deirdre/lists/\n"
    _seed_list(
        database,
        List(whakoom_list_id=116046, name="Wings", url=WINGS_URL, comic_count=10),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve the denying robots.txt and refuse everything else."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots_deny)
        return httpx.Response(200, text=load_fixture("list_detail_wings.html"))

    session = make_session(handler)
    try:
        code = run_list_detail(fast_settings(), list_id=116046, session=session, db=database)
    finally:
        session.close()

    assert code == 1


def test_per_list_failure_does_not_abort_stage(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """A 500 on the list GET marks that list failed but the stage still returns 0."""
    _seed_list(
        database,
        List(whakoom_list_id=116046, name="Wings", url=WINGS_URL, comic_count=10),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots, then 503 forever so retries exhaust and the list fails."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(503)

    # max_retries lowered so the per-list failure is reached quickly.
    session = make_session(handler, settings=Settings(delay_seconds=0.0, jitter_seconds=0.0, max_retries=2))
    try:
        code = run_list_detail(fast_settings(), list_id=116046, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    assert _status_of(database, 116046) == "failed"


def test_save_raw_archives_get_and_post(
    make_session: Callable[..., WhakoomSession],
    database: Database,
    tmp_path: Path,
) -> None:
    """With save_raw on, both the GET and POST snapshots are archived."""
    _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=10,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    settings = fast_settings(save_raw=True, raw_dir=tmp_path / "raw")
    session = make_session(handler)
    try:
        code = run_list_detail(settings, list_id=116046, session=session, db=database)
    finally:
        session.close()

    assert code == 0
    archives = list((tmp_path / "raw").rglob("*.html.gz"))
    # One GET snapshot + one POST snapshot.
    assert len(archives) == 2


def test_get_list_roundtrip_after_scrape(
    make_session: Callable[..., WhakoomSession],
    database: Database,
) -> None:
    """The scraped list is still retrievable via get_list after the stage runs."""
    _seed_list(
        database,
        List(
            whakoom_list_id=116046,
            name="Mangas publicados en la Wings",
            url=WINGS_URL,
            comic_count=10,
        ),
    )
    handler = _route_handler(
        get_html=load_fixture("list_detail_wings.html"),
        post_payload={"Html": "", "ExtraInfo": "0"},
    )
    session = make_session(handler)
    try:
        run_list_detail(fast_settings(), list_id=116046, session=session, db=database)
    finally:
        session.close()

    fetched = get_list(database, 116046)
    assert fetched is not None
    assert fetched.name == "Mangas publicados en la Wings"
