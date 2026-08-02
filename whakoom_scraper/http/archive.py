"""Raw-response archive: gzip snapshots of fetched pages.

Each response is written to ``raw_dir/{YYYY-MM-DD}/{stage}/{key}.html.gz`` where
``key`` is derived deterministically from the source URL, so re-fetching the
same URL overwrites (rather than duplicates) the snapshot.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

_KEY_SAFE = re.compile(r"[^a-z0-9]+")


def save_raw(raw_dir: Path, stage: str, url: str, content: bytes) -> Path:
    """Gzip ``content`` to the dated/stage archive path.

    Args:
        raw_dir: Archive root (``WK_RAW_DIR``).
        stage: Pipeline stage name (e.g. ``lists``).
        url: Source URL; used to derive a deterministic, collision-safe key.
        content: Raw response bytes.

    Returns:
        The path to the written ``.html.gz`` file.
    """
    target = raw_dir / datetime.date.today().isoformat() / stage / f"{_url_to_key(url)}.html.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wb") as handle:
        handle.write(content)
    return target


def _url_to_key(url: str) -> str:
    """Derive a deterministic, filesystem-safe key from ``url``.

    Args:
        url: The source URL.

    Returns:
        ``{sanitized_path}_{sha256[:8]}``, truncated to fit common filesystems.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    path = urlparse(url).path.strip("/").lower()
    safe = _KEY_SAFE.sub("_", path).strip("_") or "root"
    return f"{safe[:120]}_{digest}"
