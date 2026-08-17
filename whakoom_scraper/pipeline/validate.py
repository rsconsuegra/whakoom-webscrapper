"""Stage 5: read-only validation gate over the collected dataset.

Runs the V2 §12 checks, prints a console report, and records the outcome in a
``validate`` scrape run together with a per-table row-count snapshot so later
runs can flag unexpected drops.

Exit codes:
    * 0 — all checks passed (warnings allowed)
    * 1 — the validation machinery itself failed (e.g. sqlite error)
    * 2 — at least one check failed
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from whakoom_scraper.config import Settings
from whakoom_scraper.pipeline._runtime import owned_db
from whakoom_scraper.store.db import Database
from whakoom_scraper.store.repositories import (
    abort_stale_runs,
    close_run,
    count_foreign_key_violations,
    count_lists_missing_comic_count,
    count_observation_bound_violations,
    count_series_bound_violations,
    count_unresolved_items,
    create_run,
    get_duplicate_item_positions,
    get_duplicate_item_slugs,
    get_last_completed_run_id,
    get_latest_stage_runs,
    get_list_count_mismatches,
    get_snapshots_for_run,
    get_table_row_counts,
    record_snapshots,
)

log = logging.getLogger(__name__)

VALIDATE_OK = 0
VALIDATE_STAGE_ERROR = 1
VALIDATE_FAILED = 2

CHECK_OK = "pass"
CHECK_WARN = "warn"
CHECK_FAIL = "fail"

#: Maximum tolerated parse-failure rate per stage (V2 §12 check 7).
PARSE_FAILURE_RATE_LIMIT = 0.05

_STATUS_STYLE = {CHECK_OK: "green", CHECK_WARN: "yellow", CHECK_FAIL: "red"}


@dataclass(kw_only=True, frozen=True)
class CheckResult:
    """Outcome of a single validation check."""

    name: str
    status: str
    detail: str


def run_validate(settings: Settings, *, db: Database | None = None) -> int:
    """Run Stage 5: the read-only validation gate.

    Owns (and closes) a :class:`Database` when one is not supplied by the
    caller, so production CLI use needs no extra plumbing while tests inject
    a pre-built instance.

    Args:
        settings: Runtime settings (the db path is used when ``db`` is None).
        db: Optional pre-opened database (tests); opened and closed when None.

    Returns:
        Process exit code (0 passed, 1 machinery error, 2 check failure).
    """
    with owned_db(settings, db) as store:
        return _run_validate(store)


def _run_validate(db: Database) -> int:
    """Execute every check and record the outcome.

    Args:
        db: Open database handle.

    Returns:
        Process exit code (0 passed, 1 machinery error, 2 check failure).
    """
    run_id = create_run(db, "validate")
    db.commit()
    try:
        stale_aborted = abort_stale_runs(db, run_id)
        db.commit()
        checks = [
            _check_list_counts(db),
            _check_foreign_keys(db),
            _check_duplicate_keys(db),
            _check_unresolved_items(db),
            _check_bounds(db),
            _check_row_count_deltas(db, run_id),
            _check_parse_failure_rate(db),
            _check_stale_runs(stale_aborted),
        ]
    except (sqlite3.Error, ValueError) as exc:
        close_run(db, run_id, "failed", items_processed=0, items_failed=0, notes=f"validation error: {exc}")
        db.commit()
        log.error("validate stage failed: %s", exc)
        return VALIDATE_STAGE_ERROR

    failed = sum(1 for check in checks if check.status == CHECK_FAIL)
    warned = sum(1 for check in checks if check.status == CHECK_WARN)
    status = "failed" if failed else "completed"
    notes = _build_notes(checks, failed, warned)

    with db.transaction():
        record_snapshots(db, run_id, get_table_row_counts(db))
        close_run(db, run_id, status, items_processed=len(checks), items_failed=failed, notes=notes)

    _render_report(checks)
    log.info("validate: %d checks, %d warnings, %d failures", len(checks), warned, failed)
    return VALIDATE_FAILED if failed else VALIDATE_OK


def _check_list_counts(db: Database) -> CheckResult:
    """Check parsed item counts against each list's advertised comic_count.

    Args:
        db: Open database handle.

    Returns:
        The check outcome (tolerance 0; null comic_count lists are a warning).
    """
    mismatches = get_list_count_mismatches(db)
    missing = count_lists_missing_comic_count(db)
    for whakoom_list_id, name, comic_count, parsed in mismatches:
        log.warning(
            "list %d (%s): advertised comic_count=%d but parsed %d items",
            whakoom_list_id,
            name,
            comic_count,
            parsed,
        )
    if mismatches:
        first = mismatches[0]
        return CheckResult(
            name="list counts",
            status=CHECK_FAIL,
            detail=f"{len(mismatches)} lists mismatch (e.g. {first[1]}: advertised {first[2]}, parsed {first[3]})",
        )
    detail = f"all lists reconcile with comic_count ({missing} without advertised count)"
    status = CHECK_WARN if missing else CHECK_OK
    return CheckResult(name="list counts", status=status, detail=detail)


def _check_foreign_keys(db: Database) -> CheckResult:
    """Check ``PRAGMA foreign_key_check`` returns zero violations.

    Args:
        db: Open database handle.

    Returns:
        The check outcome.
    """
    violations = count_foreign_key_violations(db)
    if violations:
        return CheckResult(name="foreign keys", status=CHECK_FAIL, detail=f"{violations} foreign key violations")
    return CheckResult(name="foreign keys", status=CHECK_OK, detail="0 foreign key violations")


def _check_duplicate_keys(db: Database) -> CheckResult:
    """Check no duplicate (list, position) or (list, slug) natural keys exist.

    Args:
        db: Open database handle.

    Returns:
        The check outcome.
    """
    positions = get_duplicate_item_positions(db)
    slugs = get_duplicate_item_slugs(db)
    total = len(positions) + len(slugs)
    if total:
        return CheckResult(
            name="duplicate keys",
            status=CHECK_FAIL,
            detail=f"{len(positions)} duplicate positions, {len(slugs)} duplicate slugs",
        )
    return CheckResult(name="duplicate keys", status=CHECK_OK, detail="no duplicate natural keys")


def _check_unresolved_items(db: Database) -> CheckResult:
    """Count unresolved list items (warning, never a failure — V2 §12.4).

    Args:
        db: Open database handle.

    Returns:
        The check outcome.
    """
    unresolved = count_unresolved_items(db)
    if unresolved:
        return CheckResult(
            name="unresolved items",
            status=CHECK_WARN,
            detail=f"{unresolved} items without series link (see data/review_unresolved.csv)",
        )
    return CheckResult(name="unresolved items", status=CHECK_OK, detail="every item links to a series")


def _check_bounds(db: Database) -> CheckResult:
    """Check rating/count bounds on series and observation rows.

    Args:
        db: Open database handle.

    Returns:
        The check outcome.
    """
    series_violations = count_series_bound_violations(db)
    observation_violations = count_observation_bound_violations(db)
    total = series_violations + observation_violations
    if total:
        return CheckResult(
            name="value bounds",
            status=CHECK_FAIL,
            detail=f"{series_violations} series, {observation_violations} observation rows out of bounds",
        )
    return CheckResult(name="value bounds", status=CHECK_OK, detail="ratings in [0,5], counts >= 0")


def _check_row_count_deltas(db: Database, run_id: int) -> CheckResult:
    """Compare table row counts against the previous successful validate run.

    Args:
        db: Open database handle.
        run_id: The current validate run id (excluded from the baseline).

    Returns:
        The check outcome (any drop is a failure; growth or new tables pass).
    """
    previous_run = get_last_completed_run_id(db, "validate", exclude_id=run_id)
    current = get_table_row_counts(db)
    if previous_run is None:
        return CheckResult(name="row deltas", status=CHECK_WARN, detail="no previous baseline; recording first snapshot")
    baseline = get_snapshots_for_run(db, previous_run)
    drops = [
        f"{table}: {baseline[table]} -> {current.get(table, 0)}"
        for table in sorted(baseline)
        if current.get(table, 0) < baseline[table]
    ]
    if drops:
        return CheckResult(name="row deltas", status=CHECK_FAIL, detail="unexpected drops: " + ", ".join(drops))
    return CheckResult(name="row deltas", status=CHECK_OK, detail="no drops vs previous successful run")


def _check_parse_failure_rate(db: Database) -> CheckResult:
    """Check each stage's latest completed run stayed under the failure limit.

    Args:
        db: Open database handle.

    Returns:
        The check outcome.
    """
    offenders: list[str] = []
    for stage, processed, failed in get_latest_stage_runs(db):
        total = processed + failed
        if total == 0:
            continue
        rate = failed / total
        if rate >= PARSE_FAILURE_RATE_LIMIT:
            offenders.append(f"{stage}: {failed}/{total} failed ({rate:.1%})")
    if offenders:
        return CheckResult(
            name="parse failure rate",
            status=CHECK_FAIL,
            detail="stages at or above 5%: " + ", ".join(offenders),
        )
    return CheckResult(name="parse failure rate", status=CHECK_OK, detail="every stage below 5%")


def _check_stale_runs(stale_aborted: int) -> CheckResult:
    """Report stale ``running`` runs closed as ``aborted`` by this validate run.

    Args:
        stale_aborted: Number of stale runs aborted just before the checks.

    Returns:
        The check outcome (warning only; bookkeeping, not corruption).
    """
    if stale_aborted:
        return CheckResult(name="stale runs", status=CHECK_WARN, detail=f"{stale_aborted} stale running runs marked aborted")
    return CheckResult(name="stale runs", status=CHECK_OK, detail="no stale running runs")


def _build_notes(checks: list[CheckResult], failed: int, warned: int) -> str:
    """Build the scrape run notes summarizing the check outcomes.

    Args:
        checks: Every check result.
        failed: Number of failed checks.
        warned: Number of warnings.

    Returns:
        A compact single-line summary.
    """
    parts = [f"{len(checks)} checks: {len(checks) - failed - warned} pass / {warned} warn / {failed} fail"]
    parts += [f"{c.name}: {c.detail}" for c in checks if c.status != CHECK_OK]
    return "; ".join(parts)


def _render_report(checks: list[CheckResult]) -> None:
    """Print the validation report as a rich table.

    Args:
        checks: Every check result.
    """
    table = Table(title="wk validate — dataset report")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for check in checks:
        table.add_row(check.name, f"[{_STATUS_STYLE[check.status]}]{check.status.upper()}[/]", check.detail)
    Console().print(table)
