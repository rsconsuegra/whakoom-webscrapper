"""Tests for the validation/analytics repository functions and queries."""

from __future__ import annotations

from whakoom_scraper.domain import Observation, Series, SeriesRef
from whakoom_scraper.store import repositories as repo
from whakoom_scraper.store.db import Database
from whakoom_scraper.tests.factories import make_item as _item
from whakoom_scraper.tests.factories import make_list as _list


def test_list_count_mismatches(database: Database) -> None:
    """Mismatches are reported; matching and null-count lists are not."""
    matched = repo.upsert_list(database, _list(whakoom_list_id=1, comic_count=2))
    mismatched = repo.upsert_list(database, _list(whakoom_list_id=2, comic_count=5))
    unknown = repo.upsert_list(database, _list(whakoom_list_id=3, comic_count=None))
    repo.replace_list_items(database, matched, [_item(matched, 1), _item(matched, 2, slug="xyz78")])
    repo.replace_list_items(database, mismatched, [_item(mismatched, 1)])
    repo.replace_list_items(database, unknown, [_item(unknown, 1)])
    database.commit()

    mismatches = repo.get_list_count_mismatches(database)

    assert mismatches == [(2, "Manga 2000", 5, 1)]
    assert repo.count_lists_missing_comic_count(database) == 1


def test_foreign_key_violations_detected(database: Database) -> None:
    """Rows inserted with enforcement off are counted by the pragma check."""
    database.connection.execute("PRAGMA foreign_keys=OFF")
    database.connection.execute(
        "INSERT INTO list_items (list_id, position, volume_slug, volume_url) VALUES (999, 1, 'orphan', 'u')"
    )
    database.connection.execute("PRAGMA foreign_keys=ON")
    database.commit()

    assert repo.count_foreign_key_violations(database) == 1


def test_duplicate_key_checks_empty_on_valid_data(database: Database) -> None:
    """A cleanly replaced list produces no duplicate natural keys."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(database, list_id, [_item(list_id, 1), _item(list_id, 2, slug="xyz78")])
    repo.replace_list_items(database, list_id, [_item(list_id, 1), _item(list_id, 2, slug="xyz78")])
    database.commit()

    assert repo.get_duplicate_item_positions(database) == []
    assert repo.get_duplicate_item_slugs(database) == []


def test_unresolved_items(database: Database) -> None:
    """Items count as unresolved until their slug links to a series."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(database, list_id, [_item(list_id, 1)])
    database.commit()
    assert repo.count_unresolved_items(database) == 1

    series_id = repo.stub_series(database, SeriesRef(whakoom_series_id=673392, slug="abc12", url="/ediciones/673392/abc12"))
    repo.set_item_series(database, "abc12", series_id)
    database.commit()
    assert repo.count_unresolved_items(database) == 0


def test_bound_violations_zero_for_valid_series(database: Database) -> None:
    """In-bounds series and observations produce no violations."""
    ref = SeriesRef(whakoom_series_id=673392, slug="abc12", url="/ediciones/673392/abc12")
    series_id = repo.stub_series(database, ref)
    database.commit()
    series = Series(
        whakoom_series_id=ref.whakoom_series_id,
        slug=ref.slug,
        url=ref.url,
        name="Ok series",
        status="En curso",
        volumes_count=3,
        rating=4.5,
        rating_count=10,
        ownership_count=7,
    )
    series_id = repo.upsert_series(database, series, publisher_id=None)
    run_id = repo.create_run(database, "series")
    repo.insert_observation(
        database,
        Observation(series_id=series_id, run_id=run_id, rating=4.5, rating_count=10, ownership_count=7, volumes_count=3),
    )
    database.commit()

    assert repo.count_series_bound_violations(database) == 0
    assert repo.count_observation_bound_violations(database) == 0


def test_snapshot_roundtrip(database: Database) -> None:
    """Recorded snapshots read back per run and uniquify per table."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(database, list_id, [_item(list_id, 1)])
    database.commit()
    counts = repo.get_table_row_counts(database)

    assert set(counts) == {
        "lists",
        "list_items",
        "publishers",
        "authors",
        "series",
        "volumes",
        "series_observations",
    }
    assert counts["lists"] == 1
    assert counts["list_items"] == 1

    run_id = repo.create_run(database, "validate")
    repo.record_snapshots(database, run_id, counts)
    database.commit()
    assert repo.get_snapshots_for_run(database, run_id) == counts


def test_latest_stage_runs_returns_last_completed_per_stage(database: Database) -> None:
    """Only the latest completed run of each stage is reported."""
    first = repo.create_run(database, "series")
    repo.close_run(database, first, "completed", items_processed=1, items_failed=1)
    second = repo.create_run(database, "series")
    repo.close_run(database, second, "completed", items_processed=10, items_failed=0)
    lists_run = repo.create_run(database, "lists")
    repo.close_run(database, lists_run, "completed", items_processed=61, items_failed=0)
    database.commit()

    assert repo.get_latest_stage_runs(database) == [("lists", 61, 0), ("series", 10, 0)]


def test_abort_stale_runs_excludes_own(database: Database) -> None:
    """Stale running runs abort; the caller's own run survives."""
    stale_one = repo.create_run(database, "lists")
    stale_two = repo.create_run(database, "series")
    own = repo.create_run(database, "validate")
    database.commit()

    aborted = repo.abort_stale_runs(database, own)

    assert aborted == 2
    assert repo.get_last_run_status(database, "lists") == "aborted"
    assert repo.get_last_run_status(database, "series") == "aborted"
    assert repo.get_last_run_status(database, "validate") == "running"
    assert own not in {stale_one, stale_two}


def test_last_completed_run_id_skips_failures_and_own(database: Database) -> None:
    """Only completed runs qualify, and the excluded id is skipped."""
    failed = repo.create_run(database, "validate")
    repo.close_run(database, failed, "failed", items_processed=0, items_failed=1)
    completed = repo.create_run(database, "validate")
    repo.close_run(database, completed, "completed", items_processed=8, items_failed=0)
    own = repo.create_run(database, "validate")
    database.commit()

    assert repo.get_last_completed_run_id(database, "validate", exclude_id=own) == completed
    assert repo.get_last_completed_run_id(database, "validate", exclude_id=completed) is None


def test_unclassified_lists_and_classification_roundtrip(database: Database) -> None:
    """Classification persists and shrinks the unclassified selection."""
    year_list = repo.upsert_list(database, _list(whakoom_list_id=1, name="Licencias manga en España, 2024"))
    magazine_list = repo.upsert_list(database, _list(whakoom_list_id=2, name="Mangas publicados en la Nakayoshi"))
    database.commit()

    unclassified = repo.get_unclassified_lists(database)
    assert [row_id for row_id, _name in unclassified] == [year_list, magazine_list]

    repo.set_list_classification(database, year_list, "year", "Licencias manga en España")
    database.commit()
    assert repo.get_unclassified_lists(database) == [(magazine_list, "Mangas publicados en la Nakayoshi")]

    stored = database.connection.execute(
        "SELECT list_type, canonical_name FROM lists WHERE id = ?",
        (year_list,),
    ).fetchone()
    assert tuple(stored) == ("year", "Licencias manga en España")
