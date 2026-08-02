"""Shared text-extraction helpers for the pure parsers.

These helpers are parsing-only utilities with no I/O and no project imports,
so they preserve the ``scrapers/`` purity contract (no httpx / WhakoomSession).
"""

from __future__ import annotations

import re

_LEADING_INT = re.compile(r"\d+")


def text_or_none(value: str | None) -> str | None:
    """Return a stripped, non-empty string or ``None``.

    Args:
        value: A raw text node, possibly ``None`` or whitespace.

    Returns:
        The stripped text, or ``None`` when empty.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def leading_int(value: str | None) -> int | None:
    """Extract the first integer found in a text node.

    Args:
        value: A raw text node such as ``"10 Cómics"`` or ``"16 votos"``.

    Returns:
        The leading integer, or ``None`` when no digit is present.
    """
    if value is None:
        return None
    match = _LEADING_INT.search(value)
    return int(match.group()) if match else None


def parse_decimal(value: str | None, *, dot: bool = False) -> float | None:
    """Parse a decimal value, handling European comma notation.

    Args:
        value: A raw text node such as ``"4,3"`` (European) or ``"4.3"``.
        dot: When ``True``, ``value`` is already dot-decimal and is parsed as-is.

    Returns:
        The float value, or ``None`` when unparseable.
    """
    if value is None:
        return None
    if dot:
        cleaned = value.strip()
    else:
        cleaned = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None
