"""Orchestration: run every stage in order, stopping at the first failure.

Implements ``wk run-all`` (V2 §16): stages 1-4 scrape, stage 5 validates, and
stage 6 (analyze) only runs when validation passed. The first nonzero exit
code stops the sequence and is returned to the caller unchanged, preserving
each stage's exit-code semantics (0 ok, 1 failure, 2 validation, 3 session).

The series stage runs in its default pending-only mode (owner decision,
2026-08-16): a settled ``run-all`` is a pure data no-op, and observation
history grows only through explicit ``wk series --force`` runs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from whakoom_scraper.config import Settings
from whakoom_scraper.pipeline.export import run_analyze
from whakoom_scraper.pipeline.stage_list_detail import run_list_detail
from whakoom_scraper.pipeline.stage_lists import run_lists
from whakoom_scraper.pipeline.stage_resolve import run_resolve
from whakoom_scraper.pipeline.stage_series import run_series
from whakoom_scraper.pipeline.validate import run_validate

log = logging.getLogger(__name__)


def run_all(settings: Settings) -> int:
    """Run stages 1-6 in order, stopping before analyze on any failure.

    Args:
        settings: Runtime settings shared by every stage.

    Returns:
        The first failing stage's exit code, or 0 when everything succeeded.
    """
    stages: list[tuple[str, Callable[[], int]]] = [
        ("lists", lambda: run_lists(settings)),
        ("list-detail", lambda: run_list_detail(settings, scrape_all=True)),
        ("resolve", lambda: run_resolve(settings)),
        ("series", lambda: run_series(settings)),
        ("validate", lambda: run_validate(settings)),
        ("analyze", lambda: run_analyze(settings)),
    ]
    for name, stage in stages:
        code = stage()
        if code != 0:
            log.error("run-all stopped at stage '%s' (exit %d)", name, code)
            return code
        log.info("run-all: stage '%s' completed", name)
    return 0
