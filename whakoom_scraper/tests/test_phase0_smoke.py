"""Smoke tests for the Phase 0 skeleton."""

from __future__ import annotations

from typer.testing import CliRunner

from whakoom_scraper.cli import app
from whakoom_scraper.config import Settings, load_settings

runner = CliRunner()


def test_settings_defaults() -> None:
    """Default settings resolve paths relative to the package root."""
    settings = Settings.from_env({})
    assert settings.profile == "deirdre"
    assert settings.allow_gated_resolution is False
    assert settings.db_path.is_absolute()
    assert settings.db_path.name == "whakoom.db"


def test_settings_from_env() -> None:
    """Environment variables override settings defaults."""
    settings = Settings.from_env({"WHAKOOM_PROFILE": "other", "WK_ALLOW_GATED_RESOLUTION": "1"})
    assert settings.profile == "other"
    assert settings.allow_gated_resolution is True


def test_load_settings() -> None:
    """load_settings returns a Settings instance without raising."""
    assert isinstance(load_settings(), Settings)


def test_cli_help_exits_zero() -> None:
    """The CLI help renders and exits 0."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_cli_lists_stub_runs() -> None:
    """A stub subcommand is dispatched by Typer and exits 0."""
    result = runner.invoke(app, ["lists"])
    assert result.exit_code == 0
    assert "not implemented" in result.output
