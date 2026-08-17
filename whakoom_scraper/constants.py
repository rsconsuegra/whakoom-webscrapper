"""Single source of truth for Whakoom site URL anatomy and endpoints.

Centralizing these avoids drift across the HTTP layer, parsers, and (future)
pipeline stages: a change to the site's URL scheme lands here once. This module
depends only on the standard library, so pure parsers (e.g.
:mod:`whakoom_scraper.scrapers.resolve`) may import from it without pulling in
``httpx`` or :class:`whakoom_scraper.http.session.WhakoomSession`.
"""

from __future__ import annotations

import re

#: Origin of the Whakoom site.
BASE_URL = "https://www.whakoom.com"

#: robots-disallowed path family touched only by the gated resolve step.
GATED_PREFIX = "/comics/"

#: Path the site redirects to when the cookie session has expired.
LOGIN_PATH = "/login"

#: Location of the site's crawl-policy document.
ROBOTS_PATH = "/robots.txt"

#: QuickView endpoint used to resolve a volume slug to its parent series.
QUICKVIEW_URL = "/pwkws.asmx/QuickView"

#: SeriesPage endpoint used to paginate list contents beyond the first page.
LISTDETAIL_PAGE_URL = "/lists/listdetail.aspx/SeriesPage"

#: Shape of a series (``/ediciones/``) URL: captures ``{id}`` and ``{slug}``.
EDICIONES_PATTERN = re.compile(r"/ediciones/(\d+)/([^/?#\"']+)")
