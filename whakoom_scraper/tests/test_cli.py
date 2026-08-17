"""CLI tests: help rendering and stage dispatch semantics."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from whakoom_scraper.cli import app, main

runner = CliRunner()


def test_cli_help_exits_zero() -> None:
    """The CLI help renders and exits 0."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_cli_series_dispatches_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """`wk series` forwards --force/--limit to run_series and propagates its exit code.

    Args:
        monkeypatch: pytest fixture used to stub the stage entry point.
    """
    captured: dict[str, Any] = {}

    def fake_run_series(_settings: object, *, force: bool = False, limit: int | None = None) -> int:
        """Record the dispatched flags and return a distinctive exit code."""
        captured["force"] = force
        captured["limit"] = limit
        return 7

    monkeypatch.setattr("whakoom_scraper.cli.run_series", fake_run_series)
    result = runner.invoke(app, ["series", "--force", "--limit", "2"])

    assert result.exit_code == 7
    assert captured == {"force": True, "limit": 2}


def test_cli_series_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """`wk series` without flags dispatches force=False and limit=None.

    Args:
        monkeypatch: pytest fixture used to stub the stage entry point.
    """
    captured: dict[str, Any] = {}

    def fake_run_series(_settings: object, *, force: bool = False, limit: int | None = None) -> int:
        """Record the dispatched flags and return 0."""
        captured["force"] = force
        captured["limit"] = limit
        return 0

    monkeypatch.setattr("whakoom_scraper.cli.run_series", fake_run_series)
    result = runner.invoke(app, ["series"])

    assert result.exit_code == 0
    assert captured == {"force": False, "limit": None}


def test_cli_validate_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """`wk validate` propagates the stage's exit code.

    Args:
        monkeypatch: pytest fixture used to stub the stage entry point.
    """

    def fake_run_validate(_settings: object) -> int:
        """Return a distinctive exit code."""
        return 5

    monkeypatch.setattr("whakoom_scraper.cli.run_validate", fake_run_validate)
    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 5


def test_cli_analyze_forwards_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """`wk analyze --force` forwards the flag and propagates the exit code.

    Args:
        monkeypatch: pytest fixture used to stub the stage entry point.
    """
    captured: dict[str, Any] = {}

    def fake_run_analyze(_settings: object, *, force: bool = False) -> int:
        """Record the dispatched flag and return 0."""
        captured["force"] = force
        return 0

    monkeypatch.setattr("whakoom_scraper.cli.run_analyze", fake_run_analyze)
    result = runner.invoke(app, ["analyze", "--force"])

    assert result.exit_code == 0
    assert captured == {"force": True}


def test_cli_run_all_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """`wk run-all` calls the orchestrator and propagates its exit code.

    Args:
        monkeypatch: pytest fixture used to stub the orchestrator.
    """
    captured: dict[str, Any] = {}

    def fake_run_all(_settings: object) -> int:
        """Record the invocation and return a distinctive exit code."""
        captured["called"] = True
        return 4

    monkeypatch.setattr("whakoom_scraper.cli.run_all_pipeline", fake_run_all)
    result = runner.invoke(app, ["run-all"])

    assert result.exit_code == 4
    assert captured == {"called": True}


def test_main_propagates_nonzero_stage_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns the stage's nonzero exit code (typer non-standalone mode).

    Args:
        monkeypatch: pytest fixture used to stub the stage entry point.
    """

    def fake_run_validate(_settings: object) -> int:
        """Return a distinctive failure code."""
        return 5

    monkeypatch.setattr("whakoom_scraper.cli.run_validate", fake_run_validate)

    assert main(["validate"]) == 5
