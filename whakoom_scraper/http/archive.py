"""Raw-response archive: gzip snapshots of fetched pages.

Each response is written to ``raw_dir/{YYYY-MM-DD}/{stage}/{key}.html.gz`` where
``key`` is derived deterministically from the request (method + url + body), so
re-issuing the same request overwrites (rather than duplicates) the snapshot
while distinct methods or POST bodies to the same URL produce distinct files
(B1).
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

_KEY_SAFE = re.compile(r"[^a-z0-9]+")


def save_raw(
    raw_dir: Path,
    stage: str,
    method: str,
    url: str,
    content: bytes,
    request_body: bytes | None = None,
) -> Path:
    """Gzip ``content`` to the dated/stage archive path.

    The archive key is derived from ``method``, ``url``, and ``request_body`` so
    that a GET and a POST to the same path — or two POSTs with different bodies —
    never collide (B1).

    Args:
        raw_dir: Archive root (``WK_RAW_DIR``).
        stage: Pipeline stage name (e.g. ``lists``).
        method: HTTP method (e.g. ``GET``, ``POST``); case-normalized.
        url: Source URL; used to derive a deterministic, collision-safe key.
        content: Raw response bytes.
        request_body: Optional serialized request body bytes; factored into the
            key so body-varying POSTs to one URL do not overwrite each other.

    Returns:
        The path to the written ``.html.gz`` file.
    """
    key = _request_key(method, url, request_body)
    target = raw_dir / datetime.date.today().isoformat() / stage / f"{key}.html.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wb") as handle:
        handle.write(content)
    return target


def _request_key(method: str, url: str, request_body: bytes | None) -> str:
    """Derive a deterministic, filesystem-safe key from a request.

    The digest covers ``url`` and (when present) ``request_body`` so two POSTs to
    the same URL with different bodies produce distinct keys; ``method`` is
    prepended so a GET and a POST to the same path cannot collide.

    Args:
        method: HTTP method (case-normalized to lower).
        url: The source URL.
        request_body: Optional request body bytes included in the digest.

    Returns:
        ``{method}_{sanitized_path[:120]}_{sha256[:8]}`` — collision-safe and
        truncated to fit common filesystems.
    """
    digest = hashlib.sha256(url.encode("utf-8") + (request_body or b"")).hexdigest()[:8]
    path = urlparse(url).path.strip("/").lower()
    safe = _KEY_SAFE.sub("_", path).strip("_") or "root"
    return f"{method.lower()}_{safe[:120]}_{digest}"
