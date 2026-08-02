"""Application settings, loaded from environment variables.

All paths resolve relative to the package root, never to the current working
directory. See `.env.example` for the full variable list. ``Settings.from_env``
validates every env value and raises ``ValueError`` (naming the offending
variable) on anything unrecognized or out of bounds, so a misconfigured run
fails fast instead of degrading silently (H1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_TRUTHY = {"1", "true", "yes"}
_FALSY = {"0", "false", "no"}


def _env_bool(value: str, name: str) -> bool:
    """Parse a strict boolean env literal.

    Args:
        value: The raw env value.
        name: The env variable name, used in the error message.

    Returns:
        The parsed boolean.

    Raises:
        ValueError: If ``value`` is not one of ``1/true/yes/0/false/no``
            (case-insensitive, surrounding whitespace ignored).
    """
    lowered = value.strip().lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ValueError(f"{name} must be one of 1/true/yes/0/false/no (got {value!r})")


@dataclass(kw_only=True, frozen=True)
class Settings:
    """Runtime configuration for a scraping run."""

    profile: str = "deirdre"
    cookie_file: str | None = None
    allow_gated_resolution: bool = False
    db_path: Path = PROJECT_ROOT / "data" / "whakoom.db"
    delay_seconds: float = 1.5
    jitter_seconds: float = 0.5
    max_retries: int = 3
    save_raw: bool = True
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    user_agent: str = "whakoom-scraper/2.0 (personal research)"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        """Build settings from environment variables, validating each value.

        Args:
            environ: Mapping of environment variables; defaults to ``os.environ``.

        Returns:
            A populated ``Settings`` instance.

        Raises:
            ValueError: If any env value is not a recognized boolean literal, is
                out of its numeric bounds (``delay``/``jitter`` < 0,
                ``max_retries`` < 1), or ``WHAKOOM_COOKIE_FILE`` points at a
                non-existent file.
        """
        env = os.environ if environ is None else environ

        def _path(value: str) -> Path:
            path = Path(value)
            return path if path.is_absolute() else PROJECT_ROOT / path

        delay = float(env.get("WK_DELAY_SECONDS", "1.5"))
        if delay < 0:
            raise ValueError(f"WK_DELAY_SECONDS must be >= 0 (got {delay})")
        jitter = float(env.get("WK_JITTER_SECONDS", "0.5"))
        if jitter < 0:
            raise ValueError(f"WK_JITTER_SECONDS must be >= 0 (got {jitter})")
        retries = int(env.get("WK_MAX_RETRIES", "3"))
        if retries < 1:
            raise ValueError(f"WK_MAX_RETRIES must be >= 1 (got {retries})")

        cookie_value = env.get("WHAKOOM_COOKIE_FILE") or None
        cookie_file: str | None = None
        if cookie_value is not None:
            cookie_path = _path(cookie_value)
            if not cookie_path.is_file():
                raise ValueError(
                    f"WHAKOOM_COOKIE_FILE points to {cookie_value!r}, which is not an existing file (resolved: {cookie_path})",
                )
            cookie_file = str(cookie_path)

        return cls(
            profile=env.get("WHAKOOM_PROFILE", "deirdre"),
            cookie_file=cookie_file,
            allow_gated_resolution=_env_bool(
                env.get("WK_ALLOW_GATED_RESOLUTION", "0"),
                "WK_ALLOW_GATED_RESOLUTION",
            ),
            db_path=_path(env.get("WK_DB_PATH", "data/whakoom.db")),
            delay_seconds=delay,
            jitter_seconds=jitter,
            max_retries=retries,
            save_raw=_env_bool(env.get("WK_SAVE_RAW", "1"), "WK_SAVE_RAW"),
            raw_dir=_path(env.get("WK_RAW_DIR", "data/raw")),
            user_agent=env.get("WK_USER_AGENT", "whakoom-scraper/2.0 (personal research)"),
        )


def load_settings() -> Settings:
    """Load settings, honoring a project-local ``.env`` file when present.

    Returns:
        The parsed ``Settings`` instance.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings.from_env()
