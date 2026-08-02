"""Application settings, loaded from environment variables.

All paths resolve relative to the package root, never to the current working
directory. See `.env.example` for the full variable list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
        """Build settings from environment variables.

        Args:
            environ: Mapping of environment variables; defaults to ``os.environ``.

        Returns:
            A populated ``Settings`` instance.
        """
        env = os.environ if environ is None else environ

        def _path(value: str) -> Path:
            path = Path(value)
            return path if path.is_absolute() else PROJECT_ROOT / path

        return cls(
            profile=env.get("WHAKOOM_PROFILE", "deirdre"),
            cookie_file=env.get("WHAKOOM_COOKIE_FILE") or None,
            allow_gated_resolution=env.get("WK_ALLOW_GATED_RESOLUTION", "0") == "1",
            db_path=_path(env.get("WK_DB_PATH", "data/whakoom.db")),
            delay_seconds=float(env.get("WK_DELAY_SECONDS", "1.5")),
            jitter_seconds=float(env.get("WK_JITTER_SECONDS", "0.5")),
            max_retries=int(env.get("WK_MAX_RETRIES", "3")),
            save_raw=env.get("WK_SAVE_RAW", "1") == "1",
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
