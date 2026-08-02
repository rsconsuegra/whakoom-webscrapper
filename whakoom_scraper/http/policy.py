"""robots.txt fetch/cache and allow/deny policy for Whakoom.

Public stages assert every path is allowed before requesting it. The single
robots-disallowed path family we touch is ``/comics/`` (Stage 3 resolution),
which is an explicit, config-gated exception: it is only considered allowed
when ``WK_ALLOW_GATED_RESOLUTION=1`` (V2 §11, §19).
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

import httpx

from whakoom_scraper.http.session import BASE_URL

GATED_PREFIX = "/comics/"


class RobotsPolicy:
    """Cached robots.txt policy with a config-gated ``/comics/`` exception."""

    def __init__(
        self,
        robots_text: str,
        *,
        base_url: str = BASE_URL,
        user_agent: str,
        allow_gated: bool,
    ) -> None:
        """Initialize the policy from robots.txt text.

        Args:
            robots_text: Raw ``robots.txt`` body.
            base_url: Site origin URL.
            user_agent: User-agent string to evaluate rules against.
            allow_gated: Whether the ``/comics/`` exception is enabled.
        """
        self._parser = RobotFileParser()
        self._parser.parse(robots_text.splitlines())
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._allow_gated = allow_gated

    @classmethod
    def from_client(
        cls,
        client: httpx.Client,
        *,
        base_url: str = BASE_URL,
        user_agent: str,
        allow_gated: bool,
    ) -> RobotsPolicy:
        """Fetch ``robots.txt`` over ``client`` and build a policy.

        Args:
            client: An httpx client (real or mock) with the Whakoom base URL set.
            base_url: Site origin URL.
            user_agent: User-agent string to evaluate rules against.
            allow_gated: Whether the ``/comics/`` exception is enabled.

        Returns:
            A populated ``RobotsPolicy``.
        """
        response = client.get("/robots.txt")
        response.raise_for_status()
        return cls(
            response.text,
            base_url=base_url,
            user_agent=user_agent,
            allow_gated=allow_gated,
        )

    def is_allowed(self, path: str) -> bool:
        """Decide whether ``path`` may be requested.

        The ``/comics/`` family is the documented gated exception and is allowed
        only when ``allow_gated`` is set. All other paths follow robots.txt.

        Args:
            path: A site-relative path beginning with ``/``.

        Returns:
            ``True`` if the path may be requested, ``False`` otherwise.
        """
        if path.startswith(GATED_PREFIX):
            return self._allow_gated
        return self._parser.can_fetch(self._user_agent, self._base_url + path)
