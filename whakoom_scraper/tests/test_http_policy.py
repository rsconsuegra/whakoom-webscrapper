"""Tests for :mod:`whakoom_scraper.http.policy`."""

from __future__ import annotations

import httpx

from whakoom_scraper.http.policy import RobotsPolicy

ROBOTS = "User-agent: *\nDisallow: /comics/\n"


def test_public_paths_allowed() -> None:
    """Public, robots-allowed paths are permitted."""
    policy = RobotsPolicy(ROBOTS, user_agent="wk", allow_gated=False)
    assert policy.is_allowed("/deirdre/lists/")
    assert policy.is_allowed("/ediciones/123/foo")
    assert policy.is_allowed("/publisher/1/bar")


def test_comics_denied_without_flag() -> None:
    """/comics/ is denied when the gated flag is off."""
    policy = RobotsPolicy(ROBOTS, user_agent="wk", allow_gated=False)
    assert not policy.is_allowed("/comics/token/slug/1")


def test_comics_allowed_with_flag() -> None:
    """/comics/ is permitted when the gated flag is on."""
    policy = RobotsPolicy(ROBOTS, user_agent="wk", allow_gated=True)
    assert policy.is_allowed("/comics/token/slug/1")


def test_from_client_fetches_and_parses_robots() -> None:
    """from_client fetches /robots.txt and parses the rules."""
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record and serve the robots.txt body."""
        fetched.append(request.url.path)
        return httpx.Response(200, text=ROBOTS)

    client = httpx.Client(
        base_url="https://www.whakoom.com",
        transport=httpx.MockTransport(handler),
    )
    policy = RobotsPolicy.from_client(client, user_agent="wk", allow_gated=False)
    assert fetched == ["/robots.txt"]
    assert policy.is_allowed("/deirdre/lists/")
    assert not policy.is_allowed("/comics/x")
    client.close()
