"""Pure classification of list names into ``list_type`` / canonical names.

Used by the analyze stage's enrichment step (V2 §14): before the DuckDB views
are built, every list with a null ``list_type`` gets one of:

* ``year`` — license lists scoped to a calendar year
  (``"Licencias manga en España, 2026"`` → canonical
  ``"Licencias manga en España"``);
* ``magazine`` — titles published in a given magazine
  (``"Mangas publicados en la Nakayoshi"`` → canonical ``"Nakayoshi"``);
* ``event`` — licenses announced at an event
  (``"Licencias manga del 31º Manga Bcn"`` → canonical ``"Manga Bcn"``);
* ``theme`` — curated topic lists (canonical name is the list name).
"""

from __future__ import annotations

import re

YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")
MAGAZINE_PATTERN = re.compile(r"\ben la\s+(?P<magazine>.+)$", re.IGNORECASE)
EVENT_PATTERN = re.compile(r"manga\s*bcn|manga\s*barcelona", re.IGNORECASE)

#: Magazine-looking tails that are actually country/language scopes.
_NON_MAGAZINE_TARGETS = frozenset({"españa", "inglés", "inglés.", "japonés", "japonés."})

EVENT_CANONICAL_NAME = "Manga Bcn"

YEAR = "year"
MAGAZINE = "magazine"
EVENT = "event"
THEME = "theme"


def classify_list_name(name: str) -> tuple[str, str]:
    """Classify a list name into its type and canonical aggregation name.

    Args:
        name: The raw list name from Whakoom.

    Returns:
        A ``(list_type, canonical_name)`` pair where ``list_type`` is one of
        ``year``, ``magazine``, ``event``, ``theme``.
    """
    year_match = YEAR_PATTERN.search(name)
    if year_match:
        canonical = name.replace(year_match.group(0), "", 1).strip(" ,-–")
        return YEAR, canonical

    if EVENT_PATTERN.search(name):
        return EVENT, EVENT_CANONICAL_NAME

    magazine_match = MAGAZINE_PATTERN.search(name)
    if magazine_match and magazine_match.group("magazine").strip().lower() not in _NON_MAGAZINE_TARGETS:
        return MAGAZINE, magazine_match.group("magazine").strip()

    return THEME, name
