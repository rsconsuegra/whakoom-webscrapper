"""Tests for :mod:`whakoom_scraper.http.archive`."""

from __future__ import annotations

import datetime
import gzip
from pathlib import Path

from whakoom_scraper.http.archive import save_raw


def test_save_raw_writes_one_gzip(tmp_path: Path) -> None:
    """Exactly one gzip file is written under the dated/stage path."""
    target = save_raw(
        tmp_path,
        "lists",
        "GET",
        "https://www.whakoom.com/deirdre/lists/",
        b"<html>ok</html>",
    )
    assert target.suffixes == [".html", ".gz"]
    assert target.parent.name == "lists"
    assert target.parent.parent.name == datetime.date.today().isoformat()

    files = list(tmp_path.rglob("*.gz"))
    assert len(files) == 1
    with gzip.open(target, "rb") as handle:
        assert handle.read() == b"<html>ok</html>"


def test_deterministic_key_for_same_request(tmp_path: Path) -> None:
    """The same method+url+body yields the same archive filename."""
    first = save_raw(tmp_path / "a", "lists", "GET", "https://www.whakoom.com/x", b"")
    second = save_raw(tmp_path / "b", "lists", "GET", "https://www.whakoom.com/x", b"")
    assert first.name == second.name


def test_distinct_urls_distinct_files(tmp_path: Path) -> None:
    """Distinct URLs yield distinct archive files."""
    first = save_raw(tmp_path, "lists", "GET", "https://www.whakoom.com/a", b"")
    second = save_raw(tmp_path, "lists", "GET", "https://www.whakoom.com/b", b"")
    assert first != second


def test_distinct_methods_to_same_url_are_distinct(tmp_path: Path) -> None:
    """GET vs POST to the same URL produce distinct archive filenames."""
    get_path = save_raw(tmp_path, "lists", "GET", "https://www.whakoom.com/x", b"")
    post_path = save_raw(tmp_path, "lists", "POST", "https://www.whakoom.com/x", b"")
    assert get_path.name != post_path.name


def test_distinct_bodies_to_same_url_are_distinct(tmp_path: Path) -> None:
    """POSTs with different bodies to the same URL produce distinct filenames."""
    first = save_raw(
        tmp_path,
        "lists",
        "POST",
        "https://www.whakoom.com/x",
        b"",
        request_body=b"cid=comicA",
    )
    second = save_raw(
        tmp_path,
        "lists",
        "POST",
        "https://www.whakoom.com/x",
        b"",
        request_body=b"cid=comicB",
    )
    assert first.name != second.name


def test_identical_request_is_idempotent(tmp_path: Path) -> None:
    """Same method+url+body yields the same filename across distinct roots."""
    first = save_raw(
        tmp_path / "a",
        "lists",
        "POST",
        "https://www.whakoom.com/x",
        b"",
        request_body=b"cid=comicA",
    )
    second = save_raw(
        tmp_path / "b",
        "lists",
        "POST",
        "https://www.whakoom.com/x",
        b"",
        request_body=b"cid=comicA",
    )
    assert first.name == second.name
