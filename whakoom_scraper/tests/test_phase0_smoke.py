"""Smoke tests for the Phase 0 skeleton plus config validation (H1) and the
nonzero-exit stub behavior (I1).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from whakoom_scraper.cli import app
from whakoom_scraper.config import PROJECT_ROOT, Settings, load_settings

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


def test_cli_series_stub_exits_nonzero() -> None:
    """An unimplemented stage exits nonzero so it cannot mask as success (I1)."""
    result = runner.invoke(app, ["series"])
    assert result.exit_code == 1
    assert "not implemented" in result.output


# --- H1: config validation -------------------------------------------------


def test_invalid_save_raw_bool_raises() -> None:
    """An unrecognized WK_SAVE_RAW literal is rejected."""
    with pytest.raises(ValueError, match="WK_SAVE_RAW"):
        Settings.from_env({"WK_SAVE_RAW": "maybe"})


def test_invalid_gated_bool_raises() -> None:
    """An unrecognized WK_ALLOW_GATED_RESOLUTION literal is rejected."""
    with pytest.raises(ValueError, match="WK_ALLOW_GATED_RESOLUTION"):
        Settings.from_env({"WK_ALLOW_GATED_RESOLUTION": "yep"})


def test_negative_delay_raises() -> None:
    """A negative WK_DELAY_SECONDS is rejected."""
    with pytest.raises(ValueError, match="WK_DELAY_SECONDS"):
        Settings.from_env({"WK_DELAY_SECONDS": "-1"})


def test_negative_jitter_raises() -> None:
    """A negative WK_JITTER_SECONDS is rejected."""
    with pytest.raises(ValueError, match="WK_JITTER_SECONDS"):
        Settings.from_env({"WK_JITTER_SECONDS": "-0.5"})


def test_zero_max_retries_raises() -> None:
    """WK_MAX_RETRIES below 1 is rejected."""
    with pytest.raises(ValueError, match="WK_MAX_RETRIES"):
        Settings.from_env({"WK_MAX_RETRIES": "0"})


def test_missing_cookie_file_raises(tmp_path: Path) -> None:
    """WHAKOOM_COOKIE_FILE pointing at a non-existent file is rejected."""
    missing = tmp_path / "nope.txt"
    with pytest.raises(ValueError, match="WHAKOOM_COOKIE_FILE"):
        Settings.from_env({"WHAKOOM_COOKIE_FILE": str(missing)})


def test_existing_absolute_cookie_file_is_accepted(tmp_path: Path) -> None:
    """An existing absolute cookie file is accepted and stored absolute."""
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    settings = Settings.from_env({"WHAKOOM_COOKIE_FILE": str(cookie)})
    assert settings.cookie_file == str(cookie)


def test_relative_cookie_file_resolves_to_project_root() -> None:
    """A relative WHAKOOM_COOKIE_FILE resolves under PROJECT_ROOT when present."""
    rel = Path("data/raw/_test_cookies.tmp")
    absolute = PROJECT_ROOT / rel
    try:
        absolute.write_text("# test cookie file\n", encoding="utf-8")
        settings = Settings.from_env({"WHAKOOM_COOKIE_FILE": str(rel)})
    finally:
        absolute.unlink(missing_ok=True)
    assert Path(settings.cookie_file or "") == absolute
