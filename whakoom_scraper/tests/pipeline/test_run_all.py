"""Tests for the run-all orchestrator (stage ordering and failure stops)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from whakoom_scraper.config import Settings
from whakoom_scraper.pipeline import run_all as run_all_module
from whakoom_scraper.tests.conftest import fast_settings

STAGE_ORDER = ["lists", "list-detail", "resolve", "series", "validate", "analyze"]


def _fake(calls: list[str], name: str, exit_code: int) -> Callable[..., int]:
    """Build a stage stub that records its name and returns an exit code."""

    def fake(_settings: Settings, **_kwargs: bool) -> int:
        """Record the invocation and return the configured exit code."""
        calls.append(name)
        return exit_code

    return fake


def test_run_all_executes_every_stage_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """All six stages run in sequence and a clean pass returns 0."""
    calls: list[str] = []
    for name, attribute in zip(
        STAGE_ORDER,
        ["run_lists", "run_list_detail", "run_resolve", "run_series", "run_validate", "run_analyze"],
        strict=True,
    ):
        monkeypatch.setattr(run_all_module, attribute, _fake(calls, name, 0))

    assert run_all_module.run_all(fast_settings()) == 0
    assert calls == STAGE_ORDER


def test_run_all_stops_and_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing stage aborts the sequence and its exit code wins."""
    calls: list[str] = []
    monkeypatch.setattr(run_all_module, "run_lists", _fake(calls, "lists", 0))
    monkeypatch.setattr(run_all_module, "run_list_detail", _fake(calls, "list-detail", 0))
    monkeypatch.setattr(run_all_module, "run_resolve", _fake(calls, "resolve", 3))

    assert run_all_module.run_all(fast_settings()) == 3
    assert calls == ["lists", "list-detail", "resolve"]


def test_run_all_skips_analyze_when_validate_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A validate exit 2 stops before analyze without masking the code."""
    calls: list[str] = []
    for name, attribute, code in [
        ("lists", "run_lists", 0),
        ("list-detail", "run_list_detail", 0),
        ("resolve", "run_resolve", 0),
        ("series", "run_series", 0),
        ("validate", "run_validate", 2),
        ("analyze", "run_analyze", 0),
    ]:
        monkeypatch.setattr(run_all_module, attribute, _fake(calls, name, code))

    assert run_all_module.run_all(fast_settings()) == 2
    assert calls == STAGE_ORDER[:5]
