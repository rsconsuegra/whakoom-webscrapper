"""Integration tests for the analyze stage (DuckDB views + CSV exports)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from whakoom_scraper.config import Settings
from whakoom_scraper.domain import List, ListItem, SeriesRef
from whakoom_scraper.pipeline import export
from whakoom_scraper.pipeline.export import run_analyze
from whakoom_scraper.store import repositories as repo
from whakoom_scraper.store.db import Database

EXPORT_FILES = ("lists.csv", "list_items.csv", "series.csv", "volumes.csv", "series_observations.csv")


def _db_settings(database: Database, tmp_path: Path) -> Settings:
    """Point settings' db path at the injected temp database."""
    row = database.connection.execute("PRAGMA database_list").fetchone()
    assert row is not None
    db_file = Path(str(row[2]))
    return Settings(
        db_path=db_file,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        save_raw=False,
        raw_dir=tmp_path / "raw",
    )


def _item(list_id: int, slug: str) -> ListItem:
    return ListItem(
        list_id=list_id,
        position=1,
        volume_slug=slug,
        volume_url=f"https://www.whakoom.com/comics/{slug}/una_obra/1",
        whakoom_publication_id=1,
        volume_number=1,
        publisher="Planeta Cómic",
    )


def _seed(database: Database) -> None:
    """Seed three list archetypes, linked items, and a passing validate run."""
    specs = [
        (1, "Licencias manga en España, 2024"),
        (2, "Mangas publicados en la Nakayoshi"),
        (3, "Seinen imprescindible"),
    ]
    for whakoom_list_id, name in specs:
        list_id = repo.upsert_list(
            database,
            List(
                whakoom_list_id=whakoom_list_id,
                name=name,
                url=f"https://www.whakoom.com/deirdre/lists/lista_{whakoom_list_id}",
                description="desc",
                comic_count=1,
                likes=1,
            ),
        )
        slug = f"slug{whakoom_list_id}"
        repo.replace_list_items(database, list_id, [_item(list_id, slug)])
        series_id = repo.stub_series(
            database,
            SeriesRef(whakoom_series_id=whakoom_list_id, slug=slug, url=f"/ediciones/{whakoom_list_id}/{slug}"),
        )
        repo.set_item_series(database, slug, series_id)
    run_id = repo.create_run(database, "validate")
    repo.close_run(database, run_id, "completed", items_processed=8, items_failed=0)
    database.commit()


def test_analyze_refused_without_completed_validation(database: Database, tmp_path: Path) -> None:
    """With no validate run at all the stage refuses and records nothing."""
    code = run_analyze(_db_settings(database, tmp_path), db=database)

    assert code == 2
    runs = database.connection.execute("SELECT COUNT(*) FROM scrape_runs WHERE stage = 'analyze'").fetchone()
    assert runs is not None and runs[0] == 0


def test_analyze_refused_after_failed_validation_but_force_overrides(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed validate run refuses analyze unless --force is passed."""
    run_id = repo.create_run(database, "validate")
    repo.close_run(database, run_id, "failed", items_processed=8, items_failed=1)
    database.commit()
    settings = _db_settings(database, tmp_path)

    assert run_analyze(settings, db=database) == 2

    monkeypatch.setattr(export, "FLOOR_TITLES_BY_YEAR", 0)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_MAGAZINE", 0)
    _seed(database)
    assert run_analyze(settings, force=True, db=database) == 0


def test_analyze_enriches_builds_views_and_exports(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validated dataset is enriched, exported, and gets DuckDB views."""
    _seed(database)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_YEAR", 0)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_MAGAZINE", 0)
    settings = _db_settings(database, tmp_path)

    code = run_analyze(settings, db=database)

    assert code == 0
    classified = database.connection.execute(
        "SELECT name, list_type, canonical_name FROM lists ORDER BY whakoom_list_id"
    ).fetchall()
    assert [tuple(row) for row in classified] == [
        ("Licencias manga en España, 2024", "year", "Licencias manga en España"),
        ("Mangas publicados en la Nakayoshi", "magazine", "Nakayoshi"),
        ("Seinen imprescindible", "theme", "Seinen imprescindible"),
    ]

    exports_dir = settings.db_path.parent / "exports"
    for filename in EXPORT_FILES:
        assert (exports_dir / filename).is_file(), filename

    duckdb_file = settings.db_path.with_suffix(".duckdb")
    assert duckdb_file.is_file()
    connection = duckdb.connect(str(duckdb_file))
    try:
        connection.execute(f"ATTACH '{settings.db_path.as_posix()}' AS wh (TYPE sqlite, READ_ONLY)")
        year_rows = connection.execute("SELECT COUNT(*) FROM v_titles_by_year").fetchone()
        magazine_rows = connection.execute("SELECT COUNT(*) FROM v_titles_by_magazine").fetchone()
        # Materialize projected columns, not just counts: non-year list names
        # yield an empty year match, and a hard CAST there crashes the view
        # even when COUNT(*) hides it via column pruning.
        year_values = connection.execute("SELECT year FROM v_titles_by_year").fetchall()
        share = connection.execute("SELECT year, publisher, titles FROM v_publisher_share_by_year").fetchall()
    finally:
        connection.close()
    assert year_rows is not None and year_rows[0] == 1
    assert magazine_rows is not None and magazine_rows[0] == 1
    assert [tuple(row) for row in year_values] == [(2024,)]
    assert [tuple(row) for row in share] == [(2024, "Planeta Cómic", 1)]

    status = database.connection.execute(
        "SELECT status FROM scrape_runs WHERE stage = 'analyze' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert status is not None and status[0] == "completed"


def test_analyze_enrichment_is_idempotent(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second run enriches zero lists and still succeeds."""
    _seed(database)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_YEAR", 0)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_MAGAZINE", 0)
    settings = _db_settings(database, tmp_path)
    assert run_analyze(settings, db=database) == 0

    code = run_analyze(settings, db=database)

    assert code == 0
    notes = database.connection.execute(
        "SELECT notes FROM scrape_runs WHERE stage = 'analyze' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert notes is not None and "enriched=0" in str(notes[0])


def test_analyze_floor_failure_fails_the_run(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missed sanity floors fail the run with an explanatory note."""
    _seed(database)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_YEAR", 1000)
    monkeypatch.setattr(export, "FLOOR_TITLES_BY_MAGAZINE", 100)
    settings = _db_settings(database, tmp_path)

    code = run_analyze(settings, db=database)

    assert code == 1
    row = database.connection.execute(
        "SELECT status, notes FROM scrape_runs WHERE stage = 'analyze' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert "floor" in str(row[1])
