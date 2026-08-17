"""Integration tests for the validate stage (Stage 5, read-only checks)."""

from __future__ import annotations

from whakoom_scraper.domain import List, SeriesRef
from whakoom_scraper.pipeline.validate import run_validate
from whakoom_scraper.store import repositories as repo
from whakoom_scraper.store.db import Database
from whakoom_scraper.tests.conftest import fast_settings
from whakoom_scraper.tests.factories import make_item as _item
from whakoom_scraper.tests.factories import make_list


def _list(whakoom_list_id: int, name: str, comic_count: int | None) -> List:
    """Build a minimal list card (short description, single like)."""
    return make_list(whakoom_list_id, name, comic_count, description="desc", likes=1)


def _seed_consistent(database: Database) -> None:
    """Seed one list whose items, series link, and run history all reconcile."""
    list_id = repo.upsert_list(database, _list(1, "Licencias 2024", comic_count=1))
    repo.replace_list_items(database, list_id, [_item(list_id, 1, "abc12")])
    series_id = repo.stub_series(
        database,
        SeriesRef(whakoom_series_id=673392, slug="abc12", url="/ediciones/673392/abc12"),
    )
    repo.set_item_series(database, "abc12", series_id)
    run_id = repo.create_run(database, "series")
    repo.close_run(database, run_id, "completed", items_processed=1, items_failed=0)
    database.commit()


def _latest_validate(database: Database) -> tuple[str, str, str]:
    """Return (stage, status, notes) of the latest validate run row."""
    row = database.connection.execute(
        "SELECT stage, status, notes FROM scrape_runs WHERE stage = 'validate' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), str(row[2] or "")


def test_validate_passes_on_consistent_dataset(database: Database) -> None:
    """A reconciling dataset exits 0 and records a completed run + snapshot."""
    _seed_consistent(database)

    code = run_validate(fast_settings(), db=database)

    assert code == 0
    stage, status, notes = _latest_validate(database)
    assert stage == "validate"
    assert status == "completed"
    assert "8 checks" in notes
    assert "fail / 0 fail" not in notes
    snapshots = database.connection.execute(
        "SELECT COUNT(*) FROM validation_snapshots vs JOIN scrape_runs r ON r.id = vs.run_id WHERE r.stage = 'validate'"
    ).fetchone()
    assert snapshots is not None and snapshots[0] == 7


def test_validate_fails_on_count_mismatch(database: Database) -> None:
    """An advertised count that disagrees with parsed items fails the gate."""
    list_id = repo.upsert_list(database, _list(1, "Licencias 2024", comic_count=5))
    repo.replace_list_items(database, list_id, [_item(list_id, 1, "abc12")])
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 2
    _, status, notes = _latest_validate(database)
    assert status == "failed"
    assert "list counts" in notes


def test_validate_aborts_stale_runs_as_warning(database: Database) -> None:
    """Stale running runs are aborted and only warn, never fail."""
    _seed_consistent(database)
    stale = repo.create_run(database, "series")
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 0
    stale_status = database.connection.execute("SELECT status FROM scrape_runs WHERE id = ?", (stale,)).fetchone()
    assert stale_status is not None and stale_status[0] == "aborted"
    _, status, notes = _latest_validate(database)
    assert status == "completed"
    assert "stale runs" in notes


def test_validate_fails_on_row_drop_vs_baseline(database: Database) -> None:
    """A second validate run flags rows that disappeared since the baseline."""
    _seed_consistent(database)
    assert run_validate(fast_settings(), db=database) == 0
    database.connection.execute("DELETE FROM list_items")
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 2
    _, status, notes = _latest_validate(database)
    assert status == "failed"
    assert "row deltas" in notes
    assert "list_items: 1 -> 0" in notes


def test_validate_passes_on_growth_vs_baseline(database: Database) -> None:
    """Growth since the baseline is accepted without warnings or failures."""
    _seed_consistent(database)
    assert run_validate(fast_settings(), db=database) == 0
    grown = repo.upsert_list(database, _list(2, "Licencias 2025", comic_count=1))
    repo.replace_list_items(database, grown, [_item(grown, 1, "xyz78")])
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 0


def test_validate_fails_on_parse_failure_rate(database: Database) -> None:
    """A latest completed stage run at or above 5% failures fails the gate."""
    _seed_consistent(database)
    run_id = repo.create_run(database, "series")
    repo.close_run(database, run_id, "completed", items_processed=9, items_failed=1)
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 2
    _, status, notes = _latest_validate(database)
    assert status == "failed"
    assert "parse failure rate" in notes


def test_validate_warns_on_unresolved_items(database: Database) -> None:
    """Items without a series link warn but do not fail the gate."""
    list_id = repo.upsert_list(database, _list(1, "Licencias 2024", comic_count=1))
    repo.replace_list_items(database, list_id, [_item(list_id, 1, "abc12")])
    run_id = repo.create_run(database, "series")
    repo.close_run(database, run_id, "completed", items_processed=1, items_failed=0)
    database.commit()

    code = run_validate(fast_settings(), db=database)

    assert code == 0
    _, status, notes = _latest_validate(database)
    assert status == "completed"
    assert "unresolved items" in notes
