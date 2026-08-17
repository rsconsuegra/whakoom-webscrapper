"""Config settings tests: defaults, env overrides, and H1 validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from whakoom_scraper.config import PROJECT_ROOT, Settings, load_settings


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
