"""Tests for the typed repository functions and their round-trips."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import pytest

from whakoom_scraper.domain import (
    Author,
    Observation,
    Publisher,
    Series,
    SeriesRef,
    Volume,
)
from whakoom_scraper.store import repositories as repo
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import RecordMissingError
from whakoom_scraper.tests.factories import make_item as _item
from whakoom_scraper.tests.factories import make_list as _list


def _series(whakoom_series_id: int = 673392, slug: str = "el_gran_gaea-tima") -> Series:
    return Series(
        whakoom_series_id=whakoom_series_id,
        slug=slug,
        url=f"https://www.whakoom.com/ediciones/{whakoom_series_id}/{slug}",
        name="El gran Gaea-tima",
        status="En curso",
        format="Rústica",
        language="Castellano",
        volumes_count=5,
        rating=4.3,
        rating_count=16,
        rating_distribution={"5": 56, "4": 19, "3": 19, "2": 6, "1": 0},
        ownership_count=3,
        synopsis="Un universo de aventuras.",
    )


def _series_ref(whakoom_series_id: int = 673392, slug: str = "el_gran_gaea-tima") -> SeriesRef:
    return SeriesRef(
        whakoom_series_id=whakoom_series_id,
        slug=slug,
        url=f"https://www.whakoom.com/ediciones/{whakoom_series_id}/{slug}",
        name="El gran Gaea-tima",
    )


def test_list_roundtrip_and_pending(database: Database) -> None:
    """A list upserts, reads back, and appears as pending."""
    list_id = repo.upsert_list(database, _list())
    database.commit()
    assert list_id > 0
    fetched = repo.get_list(database, 1)
    assert fetched is not None
    assert fetched.name == "Manga 2000"
    assert fetched.comic_count == 120
    assert fetched.likes == 45
    assert [row.whakoom_list_id for row in repo.get_pending_lists(database)] == [1]


def test_upsert_list_is_idempotent(database: Database) -> None:
    """Re-upserting the same list yields one row, updated in place."""
    repo.upsert_list(database, _list())
    repo.upsert_list(database, _list(name="Manga 2001"))
    database.commit()
    assert len(repo.get_lists(database)) == 1
    fetched = repo.get_list(database, 1)
    assert fetched is not None
    assert fetched.name == "Manga 2001"


def test_mark_list_status_validates(database: Database) -> None:
    """Invalid statuses are rejected; valid ones persist."""
    repo.upsert_list(database, _list())
    with pytest.raises(ValueError):
        repo.mark_list_status(database, 1, "bogus")
    repo.mark_list_status(database, 1, "completed")
    database.commit()
    assert repo.get_pending_lists(database) == []
    repo.reset_lists_pending(database)
    database.commit()
    assert repo.get_pending_lists(database) != []


def test_list_items_roundtrip_and_idempotent(database: Database) -> None:
    """Replacing the same items twice yields no duplicates and no errors."""
    list_id = repo.upsert_list(database, _list())
    items = [_item(list_id, 1), _item(list_id, 2, slug="xyz78")]
    result = repo.replace_list_items(database, list_id, items)
    database.commit()
    assert repo.count_items_for_list(database, list_id) == 2
    assert result.previous_count == 0
    assert result.written == 2
    assert result.removed == 0

    result = repo.replace_list_items(database, list_id, items)
    database.commit()
    assert repo.count_items_for_list(database, list_id) == 2
    assert result.previous_count == 2
    assert result.written == 2
    assert result.removed == 0
    assert not result.removed_slugs


def test_reconcile_removes_stale_items(database: Database) -> None:
    """Items dropped from the list between runs are removed and reported."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(
        database,
        list_id,
        [_item(list_id, 1, slug="abc12"), _item(list_id, 2, slug="xyz78")],
    )
    database.commit()

    result = repo.replace_list_items(database, list_id, [_item(list_id, 1, slug="abc12")])
    database.commit()
    assert repo.count_items_for_list(database, list_id) == 1
    assert result.removed == 1
    assert result.removed_slugs == ("xyz78",)
    assert result.new_count == 1


def test_reconcile_position_swap_is_safe(database: Database) -> None:
    """Swapping two items' positions between runs never hits the UNIQUE key."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(
        database,
        list_id,
        [_item(list_id, 1, slug="abc12"), _item(list_id, 2, slug="xyz78")],
    )
    database.commit()

    repo.replace_list_items(
        database,
        list_id,
        [_item(list_id, 1, slug="xyz78"), _item(list_id, 2, slug="abc12")],
    )
    database.commit()
    assert repo.count_items_for_list(database, list_id) == 2


def test_reconcile_preserves_series_links(database: Database) -> None:
    """A resolved slug keeps its series_id when the list is re-scraped."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(database, list_id, [_item(list_id, 1, slug="abc12")])
    series_id = repo.stub_series(database, _series_ref())
    database.commit()
    repo.set_item_series(database, "abc12", series_id)
    database.commit()

    repo.replace_list_items(database, list_id, [_item(list_id, 1, slug="abc12")])
    database.commit()
    row = database.connection.execute(
        "SELECT series_id FROM list_items WHERE list_id = ?",
        (list_id,),
    ).fetchone()
    assert row is not None
    assert row["series_id"] == series_id


def test_unresolved_slugs_and_set_series(database: Database) -> None:
    """Unresolved slugs surface and link once resolved."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(
        database,
        list_id,
        [_item(list_id, 1, slug="abc12"), _item(list_id, 2, slug="xyz78")],
    )
    database.commit()
    assert set(repo.get_unresolved_slugs(database)) == {"abc12", "xyz78"}

    series_id = repo.stub_series(database, _series_ref())
    database.commit()
    repo.set_item_series(database, "abc12", series_id)
    database.commit()
    assert repo.get_unresolved_slugs(database) == ["xyz78"]


def test_publisher_and_author_dedup(database: Database) -> None:
    """Publishers dedup by name, authors by Whakoom id then name."""
    first = repo.upsert_publisher(database, Publisher(name="Planeta Cómic", whakoom_id=10, url="p1"))
    second = repo.upsert_publisher(database, Publisher(name="Planeta Cómic", whakoom_id=10, url="p1"))
    assert first == second
    assert repo.get_publisher_by_name(database, "Planeta Cómic") is not None

    a1 = repo.upsert_author(database, Author(name="Junji Ito", whakoom_id=7))
    a2 = repo.upsert_author(database, Author(name="Junji Ito", whakoom_id=7))
    assert a1 == a2
    unnamed = repo.upsert_author(database, Author(name="Sin id"))
    unnamed_again = repo.upsert_author(database, Author(name="Sin id"))
    assert unnamed == unnamed_again
    database.commit()


def test_series_upsert_volumes_observation(database: Database) -> None:
    """Full series pipeline: publisher, series, volumes, observation."""
    publisher_id = repo.upsert_publisher(database, Publisher(name="Planeta Cómic"))
    series = _series()
    series_id = repo.upsert_series(database, series, publisher_id)
    database.commit()
    assert series_id > 0
    fetched = repo.get_series(database, 673392)
    assert fetched is not None
    assert fetched.name == "El gran Gaea-tima"

    volumes = [
        Volume(volume_slug="v1", series_id=series_id, number=1, title="El despertar"),
        Volume(volume_slug="v2", series_id=series_id, number=2, title="La caída"),
    ]
    repo.upsert_volumes(database, volumes)
    database.commit()
    assert repo.get_pending_series(database) == []

    run_id = repo.create_run(database, "series")
    obs = Observation(series_id=series_id, run_id=run_id, rating=4.3, rating_count=16)
    repo.insert_observation(database, obs)
    repo.insert_observation(database, obs)
    database.commit()
    rows = database.connection.execute("SELECT COUNT(*) AS n FROM series_observations").fetchone()
    assert rows["n"] == 1
    repo.close_run(database, run_id, "completed", items_processed=1, items_failed=0)
    database.commit()


def test_stub_then_full_upsert_shares_id(database: Database) -> None:
    """Stubbing then fully scraping a series keeps a single row."""
    stub_id = repo.stub_series(database, _series_ref())
    full_id = repo.upsert_series(database, _series(), publisher_id=None)
    database.commit()
    assert stub_id == full_id
    count = database.connection.execute("SELECT COUNT(*) AS n FROM series").fetchone()["n"]
    assert count == 1


def test_volume_without_series_raises(database: Database) -> None:
    """Upserting a volume with no series_id raises ValueError."""
    with pytest.raises(ValueError):
        repo.upsert_volumes(database, [Volume(volume_slug="v0")])


def test_series_status_validation(database: Database) -> None:
    """Invalid series statuses are rejected."""
    with pytest.raises(ValueError):
        repo.set_series_status(database, 1, "nope")


def test_run_lifecycle(database: Database) -> None:
    """Runs open and close with counters."""
    run_id = repo.create_run(database, "lists")
    assert run_id > 0
    repo.close_run(database, run_id, "failed", items_processed=3, items_failed=1, notes="timeout")
    database.commit()
    row = database.connection.execute("SELECT status, notes FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["notes"] == "timeout"
    with pytest.raises(ValueError):
        repo.close_run(database, run_id, "bogus", items_processed=0, items_failed=0)


def test_foreign_key_check_is_clean(database: Database) -> None:
    """After valid writes there are no FK violations."""
    list_id = repo.upsert_list(database, _list())
    repo.replace_list_items(database, list_id, [_item(list_id, 1)])
    publisher_id = repo.upsert_publisher(database, Publisher(name="Planeta Cómic"))
    series_id = repo.upsert_series(database, _series(), publisher_id)
    repo.upsert_volumes(database, [Volume(volume_slug="v1", series_id=series_id)])
    author_id = repo.upsert_author(database, Author(name="Junji Ito"))
    repo.link_series_author(database, series_id, author_id, "dibujo")
    run_id = repo.create_run(database, "series")
    repo.insert_observation(database, Observation(series_id=series_id, run_id=run_id))
    database.commit()
    violations = database.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == []


def _patch_fetchone_to_none(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    query_file: str,
    query_name: str,
) -> None:
    """Patch ``database.fetchone`` so one named query returns None.

    Used to force the post-upsert lookup to miss, exercising the
    ``RecordMissingError`` paths without dropping real rows.
    """
    real = database.fetchone

    def fake(qf: str, qn: str, params: Sequence[object] = ()) -> sqlite3.Row | None:
        """Return None for the patched query; pass through otherwise."""
        if (qf, qn) == (query_file, query_name):
            return None
        return real(qf, qn, params)

    monkeypatch.setattr(database, "fetchone", fake)


def test_upsert_list_raises_when_lookup_missing(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """A None post-upsert row surfaces as RecordMissingError, not id 0."""
    _patch_fetchone_to_none(database, monkeypatch, "lists", "get_list")
    with pytest.raises(RecordMissingError, match="upsert_list"):
        repo.upsert_list(database, _list())


def test_upsert_publisher_raises_when_lookup_missing(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """A None publisher post-upsert row surfaces as RecordMissingError."""
    _patch_fetchone_to_none(database, monkeypatch, "series", "get_publisher_id_by_name")
    with pytest.raises(RecordMissingError, match="upsert_publisher"):
        repo.upsert_publisher(database, Publisher(name="Planeta Cómic"))


def test_upsert_author_raises_when_lookup_missing_whakoom_id(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whakoom_id branch raises RecordMissingError when the lookup misses."""
    _patch_fetchone_to_none(database, monkeypatch, "series", "get_author_id_by_whakoom_id")
    with pytest.raises(RecordMissingError, match="upsert_author"):
        repo.upsert_author(database, Author(name="Junji Ito", whakoom_id=7))


def test_upsert_author_raises_when_lookup_missing_name(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """The name-only branch raises RecordMissingError when the lookup misses."""
    _patch_fetchone_to_none(database, monkeypatch, "series", "get_author_id_by_name")
    with pytest.raises(RecordMissingError, match="upsert_author"):
        repo.upsert_author(database, Author(name="Sin id"))


def test_stub_series_raises_when_lookup_missing(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """A None post-stub lookup surfaces as RecordMissingError."""
    _patch_fetchone_to_none(database, monkeypatch, "series", "get_series_id")
    with pytest.raises(RecordMissingError, match="stub_series"):
        repo.stub_series(database, _series_ref())


def test_upsert_series_raises_when_lookup_missing(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """A None series post-upsert surfaces as RecordMissingError."""
    _patch_fetchone_to_none(database, monkeypatch, "series", "get_series_id")
    with pytest.raises(RecordMissingError, match="upsert_series"):
        repo.upsert_series(database, _series(), publisher_id=None)


def test_get_pending_lists_excludes_failed(database: Database) -> None:
    """Failed lists are not returned by default; get_failed_lists returns them."""
    repo.upsert_list(database, _list(whakoom_list_id=1, name="L1"))
    repo.mark_list_status(database, 1, "failed")
    database.commit()
    assert [row.whakoom_list_id for row in repo.get_pending_lists(database)] == []
    assert [row.whakoom_list_id for row in repo.get_failed_lists(database)] == [1]


def test_get_pending_lists_includes_failed_when_requested(database: Database) -> None:
    """include_failed=True returns both pending and failed lists."""
    repo.upsert_list(database, _list(whakoom_list_id=1, name="pending"))
    repo.upsert_list(database, _list(whakoom_list_id=2, name="failed"))
    repo.mark_list_status(database, 2, "failed")
    database.commit()
    default_ids = [row.whakoom_list_id for row in repo.get_pending_lists(database)]
    forced_ids = [row.whakoom_list_id for row in repo.get_pending_lists(database, include_failed=True)]
    assert default_ids == [1]
    assert forced_ids == [1, 2]


def test_get_pending_series_excludes_failed(database: Database) -> None:
    """Failed series are not returned by default; get_failed_series returns them."""
    repo.stub_series(database, _series_ref(whakoom_series_id=1, slug="s1"))
    repo.stub_series(database, _series_ref(whakoom_series_id=2, slug="s2"))
    row = database.connection.execute("SELECT id FROM series WHERE whakoom_series_id = ?", (1,)).fetchone()
    assert row is not None
    repo.set_series_status(database, int(row["id"]), "failed")
    database.commit()
    assert [s.whakoom_series_id for s in repo.get_pending_series(database)] == [2]
    assert [s.whakoom_series_id for s in repo.get_failed_series(database)] == [1]


def test_get_pending_series_includes_failed_when_requested(database: Database) -> None:
    """include_failed=True returns both pending and failed series."""
    repo.stub_series(database, _series_ref(whakoom_series_id=1, slug="s1"))
    repo.stub_series(database, _series_ref(whakoom_series_id=2, slug="s2"))
    row = database.connection.execute("SELECT id FROM series WHERE whakoom_series_id = ?", (1,)).fetchone()
    assert row is not None
    repo.set_series_status(database, int(row["id"]), "failed")
    database.commit()
    default_ids = [s.whakoom_series_id for s in repo.get_pending_series(database)]
    forced_ids = [s.whakoom_series_id for s in repo.get_pending_series(database, include_failed=True)]
    assert default_ids == [2]
    assert forced_ids == [1, 2]


def test_invalidate_lists_marks_completed_pending(database: Database) -> None:
    """invalidate_lists flips completed lists back to pending for a refresh."""
    repo.upsert_list(database, _list())
    repo.mark_list_status(database, 1, "completed")
    database.commit()
    assert repo.get_pending_lists(database) == []
    repo.invalidate_lists(database)
    database.commit()
    assert [row.whakoom_list_id for row in repo.get_pending_lists(database)] == [1]


def test_invalidate_lists_flips_failed_pending(database: Database) -> None:
    """invalidate_lists also resets failed lists so --reset retries them."""
    repo.upsert_list(database, _list())
    repo.mark_list_status(database, 1, "failed")
    database.commit()
    assert repo.get_failed_lists(database) != []
    repo.invalidate_lists(database)
    database.commit()
    assert repo.get_failed_lists(database) == []
    assert [row.whakoom_list_id for row in repo.get_pending_lists(database)] == [1]


def test_reconcile_reuses_cross_list_series_link(database: Database) -> None:
    """A slug resolved in list A is reused when the same slug appears in list B."""
    list_a = repo.upsert_list(database, _list(whakoom_list_id=1, name="A"))
    list_b = repo.upsert_list(database, _list(whakoom_list_id=2, name="B"))
    repo.replace_list_items(database, list_a, [_item(list_a, 1, slug="abc12")])
    series_id = repo.stub_series(database, _series_ref())
    database.commit()
    repo.set_item_series(database, "abc12", series_id)
    database.commit()

    repo.replace_list_items(database, list_b, [_item(list_b, 1, slug="abc12")])
    database.commit()
    row = database.connection.execute("SELECT series_id FROM list_items WHERE list_id = ?", (list_b,)).fetchone()
    assert row is not None
    assert row["series_id"] == series_id


def test_get_global_slug_series_map_returns_distinct(database: Database) -> None:
    """The global map dedupes slug→series across lists and ignores nulls."""
    list_a = repo.upsert_list(database, _list(whakoom_list_id=1, name="A"))
    list_b = repo.upsert_list(database, _list(whakoom_list_id=2, name="B"))
    series_id = repo.stub_series(database, _series_ref())
    repo.replace_list_items(
        database,
        list_a,
        [_item(list_a, 1, slug="abc12"), _item(list_a, 2, slug="xyz78")],
    )
    repo.replace_list_items(database, list_b, [_item(list_b, 1, slug="abc12")])
    database.commit()
    repo.set_item_series(database, "abc12", series_id)
    database.commit()
    slug_map = repo.get_global_slug_series_map(database)
    assert slug_map == {"abc12": series_id}


def test_stub_series_allows_duplicate_slug_for_different_ids(database: Database) -> None:
    """Whakoom CJK titles collapse to shared underscore slugs; slug is not unique."""
    first = repo.stub_series(database, _series_ref(whakoom_series_id=1, slug="duplicated"))
    second = repo.stub_series(database, _series_ref(whakoom_series_id=2, slug="duplicated"))
    database.commit()
    assert first != second
    rows = database.connection.execute(
        "SELECT whakoom_series_id FROM series WHERE slug = ? ORDER BY whakoom_series_id",
        ("duplicated",),
    ).fetchall()
    assert [int(row["whakoom_series_id"]) for row in rows] == [1, 2]
