"""Integration tests for the series stage (Stage 4, public /ediciones/ pages)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from whakoom_scraper.domain import SeriesRef
from whakoom_scraper.http.session import WhakoomSession
from whakoom_scraper.pipeline.stage_series import run_series
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import get_series, stub_series
from whakoom_scraper.tests.conftest import ROBOTS_ALLOW_ALL, fast_settings, load_fixture

ROSEN_BLOOD = SeriesRef(
    whakoom_series_id=673392,
    slug="rosen_blood",
    url="/ediciones/673392/rosen_blood",
)


def _seed(database: Database, *refs: SeriesRef) -> None:
    """Insert series stubs and commit so the stage can select them."""
    for ref in refs:
        stub_series(database, ref)
    database.commit()


def _handler(html: str | None = None) -> Callable[[httpx.Request], httpx.Response]:
    """Build a request handler serving robots and the Rosen Blood page."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots plus the configured series page; 404 otherwise."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        if request.url.path == ROSEN_BLOOD.url:
            return httpx.Response(200, text=html if html is not None else load_fixture("series_page_rosen_blood.html"))
        return httpx.Response(404)

    return handler


def _latest_run(database: Database) -> tuple[str, str, int, int]:
    """Return (stage, status, items_processed, items_failed) of the latest run row."""
    row = database.connection.execute(
        "SELECT stage, status, items_processed, items_failed FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), int(row[2]), int(row[3])


def _scalar(database: Database, sql: str, params: tuple[object, ...] = ()) -> object:
    """Run a scalar read query against the raw connection."""
    row = database.connection.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


def test_happy_path_persists_full_series(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """A pending stub is scraped and all related rows land in one run."""
    _seed(database, ROSEN_BLOOD)

    code = run_series(fast_settings(), session=make_session(_handler()), db=database)

    assert code == 0
    assert _latest_run(database) == ("series", "completed", 1, 0)

    series = get_series(database, ROSEN_BLOOD.whakoom_series_id)
    assert series is not None
    assert series.name == "Rosen Blood"
    assert series.scrape_status == "completed"
    assert series.rating == 4.3
    assert series.volumes_count == 5

    publisher = _scalar(
        database,
        "SELECT p.name FROM series s JOIN publishers p ON p.id = s.publisher_id WHERE s.whakoom_series_id = ?",
        (ROSEN_BLOOD.whakoom_series_id,),
    )
    assert publisher == "Panini Comics España"

    numbers = database.connection.execute(
        "SELECT number FROM volumes WHERE series_id = (SELECT id FROM series WHERE whakoom_series_id = ?) ORDER BY number",
        (ROSEN_BLOOD.whakoom_series_id,),
    ).fetchall()
    assert [row[0] for row in numbers] == [1, 2, 3, 4, 5]

    author = database.connection.execute(
        "SELECT a.name, sa.role FROM series_authors sa"
        " JOIN authors a ON a.id = sa.author_id"
        " JOIN series s ON s.id = sa.series_id WHERE s.whakoom_series_id = ?",
        (ROSEN_BLOOD.whakoom_series_id,),
    ).fetchone()
    assert tuple(author) == ("Kachiru Ishizue", "author")

    observation = database.connection.execute(
        "SELECT rating, rating_count, rating_distribution FROM series_observations"
        " WHERE series_id = (SELECT id FROM series WHERE whakoom_series_id = ?)",
        (ROSEN_BLOOD.whakoom_series_id,),
    ).fetchone()
    assert observation is not None
    rating, rating_count, distribution_json = observation
    assert rating == 4.3
    assert rating_count == 16
    assert json.loads(str(distribution_json)) == {"5": 56, "4": 19, "3": 25, "2": 0, "1": 0}


def test_transient_error_marks_series_failed_and_continues(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """A persistently failing page marks only that series failed; the run completes."""
    _seed(database, ROSEN_BLOOD)

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots and a 500 series page (retries then TransientRequestError)."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(500)

    code = run_series(fast_settings(), session=make_session(handler), db=database)

    assert code == 0
    stage, status, processed, failed = _latest_run(database)
    assert (stage, status) == ("series", "completed")
    assert processed == 0
    assert failed == 1
    series = get_series(database, ROSEN_BLOOD.whakoom_series_id)
    assert series is not None
    assert series.scrape_status == "failed"

    notes = _scalar(
        database,
        "SELECT notes FROM scrape_runs ORDER BY id DESC LIMIT 1",
    )
    assert notes is not None


def test_failed_series_skipped_by_default(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """A series left failed is not retried by a subsequent default run."""
    _seed(database, ROSEN_BLOOD)

    def failing(request: httpx.Request) -> httpx.Response:
        """Serve robots and a 500 series page."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(500)

    run_series(fast_settings(), session=make_session(failing), db=database)

    page_hits = {"n": 0}

    def healthy(request: httpx.Request) -> httpx.Response:
        """Serve robots and a healthy series page; count page hits."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        page_hits["n"] += 1
        return httpx.Response(200, text=load_fixture("series_page_rosen_blood.html"))

    code = run_series(fast_settings(), session=make_session(healthy), db=database)

    assert code == 0
    assert page_hits["n"] == 0
    series = get_series(database, ROSEN_BLOOD.whakoom_series_id)
    assert series is not None
    assert series.scrape_status == "failed"


def test_force_rescrapes_completed_series_without_duplicates(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """--force re-scrapes a completed series and adds exactly one new observation."""
    _seed(database, ROSEN_BLOOD)
    page_hits = {"n": 0}
    base_handler = _handler()

    def counting(request: httpx.Request) -> httpx.Response:
        """Serve robots and the Rosen Blood page, counting page hits."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        page_hits["n"] += 1
        return base_handler(request)

    assert run_series(fast_settings(), session=make_session(counting), db=database) == 0
    assert run_series(fast_settings(), session=make_session(counting), db=database, force=True) == 0
    assert page_hits["n"] == 2

    counts = database.connection.execute(
        "SELECT"
        " (SELECT COUNT(*) FROM series) AS series,"
        " (SELECT COUNT(*) FROM series_observations) AS observations,"
        " (SELECT COUNT(*) FROM volumes) AS volumes,"
        " (SELECT COUNT(*) FROM authors) AS authors,"
        " (SELECT COUNT(*) FROM publishers) AS publishers"
    ).fetchone()
    assert tuple(counts) == (1, 2, 5, 1, 1)


def test_completed_series_skipped_by_default(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """A completed series is not re-scraped by a subsequent default run."""
    _seed(database, ROSEN_BLOOD)
    assert run_series(fast_settings(), session=make_session(_handler()), db=database) == 0

    runs_before = _scalar(database, "SELECT COUNT(*) FROM scrape_runs")
    page_hits = {"n": 0}

    def counting(request: httpx.Request) -> httpx.Response:
        """Serve robots and the Rosen Blood page, counting page hits."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        page_hits["n"] += 1
        return httpx.Response(200, text=load_fixture("series_page_rosen_blood.html"))

    code = run_series(fast_settings(), session=make_session(counting), db=database)

    assert code == 0
    assert page_hits["n"] == 0
    assert _scalar(database, "SELECT COUNT(*) FROM scrape_runs") == runs_before


def test_limit_caps_series(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """--limit caps the number of series scraped, leaving the rest pending."""
    refs = tuple(
        SeriesRef(whakoom_series_id=1000 + i, slug=f"series_{i}", url=f"/ediciones/{1000 + i}/series_{i}") for i in range(3)
    )
    _seed(database, *refs)
    page_hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots and the Rosen Blood HTML for any ediciones page."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        page_hits["n"] += 1
        return httpx.Response(200, text=load_fixture("series_page_rosen_blood.html"))

    code = run_series(fast_settings(), session=make_session(handler), db=database, limit=2)

    assert code == 0
    assert page_hits["n"] == 2
    statuses = database.connection.execute(
        "SELECT scrape_status, COUNT(*) FROM series GROUP BY scrape_status ORDER BY scrape_status"
    ).fetchall()
    assert [tuple(row) for row in statuses] == [("completed", 2), ("pending", 1)]


def test_robots_denied_exits_fatal_without_scraping(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """A robots.txt disallowing /ediciones/ aborts with 1 before any run is created."""
    _seed(database, ROSEN_BLOOD)
    page_hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots that disallow /ediciones/; count any page hit."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /ediciones/\n")
        page_hits["n"] += 1
        return httpx.Response(404)

    code = run_series(fast_settings(), session=make_session(handler), db=database)

    assert code == 1
    assert page_hits["n"] == 0
    assert _scalar(database, "SELECT COUNT(*) FROM scrape_runs") == 0


def test_empty_selection_is_clean_noop(
    database: Database,
    make_session: Callable[..., WhakoomSession],
) -> None:
    """With no series stubs the stage exits 0 without creating a run row."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve robots only."""
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL)
        return httpx.Response(404)

    code = run_series(fast_settings(), session=make_session(handler), db=database)

    assert code == 0
    assert _scalar(database, "SELECT COUNT(*) FROM scrape_runs") == 0


def test_save_raw_archives_page(
    database: Database,
    make_session: Callable[..., WhakoomSession],
    tmp_path: Path,
) -> None:
    """With save_raw enabled the fetched series page is archived under raw_dir."""
    _seed(database, ROSEN_BLOOD)
    raw_dir = tmp_path / "raw"
    settings = fast_settings(save_raw=True, raw_dir=raw_dir)

    code = run_series(settings, session=make_session(_handler()), db=database)

    assert code == 0
    archived = [path for path in raw_dir.rglob("*") if path.is_file()]
    assert archived
