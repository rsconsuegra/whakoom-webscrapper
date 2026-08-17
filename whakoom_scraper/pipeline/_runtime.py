"""Shared runtime seams for pipeline stages.

Centralizes two patterns every stage repeats so the stage modules stay focused
on their own logic:

* owning (and closing) a :class:`WhakoomSession` / :class:`Database` when the
  caller (the CLI) does not inject them, while letting tests inject both;
* asserting the profile lists path is robots-allowed before any stage request.

It also publishes :data:`STAGE_ERRORS`, the closed set of exception types a
stage treats as an expected runtime failure (network, parse, DB) and records
via the run/lifecycle machinery instead of letting it crash the process.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Generator

import httpx

from whakoom_scraper.config import Settings
from whakoom_scraper.constants import BASE_URL, GATED_PREFIX
from whakoom_scraper.http.policy import RobotsPolicy
from whakoom_scraper.http.session import TransientRequestError, WhakoomSession
from whakoom_scraper.store.db import Database

#: Closed set of exception types treated as expected stage failures.
STAGE_ERRORS: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    TransientRequestError,
    ValueError,
    KeyError,
    IndexError,
    sqlite3.Error,
)


@contextlib.contextmanager
def owned_session_db(
    settings: Settings,
    session: WhakoomSession | None,
    db: Database | None,
) -> Generator[tuple[WhakoomSession, Database]]:
    """Yield a session and database, owning and closing those not supplied.

    Production callers pass ``None`` for both and this helper builds/closes
    them; tests inject pre-built instances so they survive past the call.

    Args:
        settings: Runtime settings used to build defaults.
        session: Optional pre-built session; built and closed when ``None``.
        db: Optional pre-opened database; opened and closed when ``None``.

    Yields:
        A ``(session, database)`` pair, both guaranteed non-``None``.
    """
    with contextlib.ExitStack() as stack:
        if session is None:
            session = stack.enter_context(WhakoomSession(settings))
        if db is None:
            db = Database(settings.db_path)
            stack.callback(db.close)
        yield session, db


@contextlib.contextmanager
def owned_db(settings: Settings, db: Database | None) -> Generator[Database]:
    """Yield a database, owning (and closing) one when not supplied.

    Production callers pass ``None`` and this helper opens the configured
    database and closes it on exit; tests inject a pre-opened instance so it
    survives past the call.

    Args:
        settings: Runtime settings used to build the default.
        db: Optional pre-opened database; opened and closed when ``None``.

    Yields:
        A non-``None`` database handle.
    """
    with contextlib.ExitStack() as stack:
        store = db if db is not None else Database(settings.db_path)
        if db is None:
            stack.callback(store.close)
        yield store


def build_robots_policy(session: WhakoomSession, settings: Settings) -> RobotsPolicy:
    """Build the robots policy shared by every stage pre-flight check.

    Args:
        session: Live Whakoom session used to fetch robots.txt.
        settings: Runtime settings.

    Returns:
        The ``RobotsPolicy`` for the configured user agent.
    """
    return RobotsPolicy.from_session(
        session,
        base_url=BASE_URL,
        user_agent=settings.user_agent,
        allow_gated=settings.allow_gated_resolution,
    )


def lists_index_allowed(session: WhakoomSession, settings: Settings) -> bool:
    """Check whether robots.txt permits the profile lists path.

    Fetches ``robots.txt`` through ``session`` so the policy check travels the
    same polite, retried path as every other request.

    Args:
        session: Live Whakoom session used to fetch robots.txt.
        settings: Runtime settings.

    Returns:
        ``True`` if the ``/{profile}/lists/`` path may be requested.
    """
    policy = build_robots_policy(session, settings)
    return policy.is_allowed(f"/{settings.profile}/lists/")


def gated_resolution_allowed(session: WhakoomSession, settings: Settings) -> bool:
    """Check whether robots.txt + config permit the gated ``/comics/`` path.

    ``RobotsPolicy.is_allowed("/comics/")`` returns ``allow_gated``, so this
    gates on **both** robots.txt (the path is disallowed) and the explicit
    ``WK_ALLOW_GATED_RESOLUTION`` opt-in.

    Args:
        session: Live Whakoom session used to fetch robots.txt.
        settings: Runtime settings.

    Returns:
        ``True`` only when the gated path may be requested.
    """
    policy = build_robots_policy(session, settings)
    return policy.is_allowed(GATED_PREFIX)
