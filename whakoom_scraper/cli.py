"""Command-line entry point for the Whakoom V2 scraper.

Defines the ``wk`` console script. Each subcommand maps to a pipeline stage
implemented in :mod:`whakoom_scraper.pipeline` (``run-all`` orchestrates the
full sequence).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Annotated

import typer

from whakoom_scraper.config import load_settings
from whakoom_scraper.pipeline.export import run_analyze
from whakoom_scraper.pipeline.run_all import run_all as run_all_pipeline
from whakoom_scraper.pipeline.stage_list_detail import run_list_detail
from whakoom_scraper.pipeline.stage_lists import run_lists
from whakoom_scraper.pipeline.stage_resolve import run_resolve
from whakoom_scraper.pipeline.stage_series import run_series
from whakoom_scraper.pipeline.validate import run_validate

app = typer.Typer(
    name="wk",
    help="Whakoom V2 scraper — staged manga/comic list collection and analysis.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def _bootstrap() -> None:
    """Load settings once before any subcommand runs."""
    load_settings()


@app.command()
def lists(
    reset: Annotated[bool, typer.Option(help="Re-mark all lists as pending.")] = False,
) -> None:
    """Stage 1: scrape the profile lists index."""
    raise typer.Exit(code=run_lists(load_settings(), reset=reset))


@app.command("list-detail")
def list_detail(
    list_id: Annotated[int | None, typer.Option("--list-id", help="Scrape a single list by whakoom_list_id.")] = None,
    scrape_all: Annotated[bool, typer.Option("--all", help="Scrape every pending list.")] = False,
) -> None:
    """Stage 2: scrape list contents with pagination."""
    raise typer.Exit(code=run_list_detail(load_settings(), list_id=list_id, scrape_all=scrape_all))


@app.command()
def resolve(
    limit: Annotated[int | None, typer.Option(help="Cap the number of slugs resolved.")] = None,
) -> None:
    """Stage 3: resolve volume slugs to series (login-gated)."""
    raise typer.Exit(code=run_resolve(load_settings(), limit=limit))


@app.command()
def series(
    force: Annotated[bool, typer.Option(help="Re-scrape completed series.")] = False,
    limit: Annotated[int | None, typer.Option(help="Cap the number of series scraped.")] = None,
) -> None:
    """Stage 4: scrape series pages."""
    raise typer.Exit(code=run_series(load_settings(), force=force, limit=limit))


@app.command()
def validate() -> None:
    """Stage 5: run the read-only validation gate."""
    raise typer.Exit(code=run_validate(load_settings()))


@app.command()
def analyze(
    force: Annotated[bool, typer.Option(help="Skip the validation gate.")] = False,
) -> None:
    """Stage 6: build DuckDB views and exports."""
    raise typer.Exit(code=run_analyze(load_settings(), force=force))


@app.command("run-all")
def run_all_command() -> None:
    """Run stages 1-6 in order, stop before analyze on failure."""
    raise typer.Exit(code=run_all_pipeline(load_settings()))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested ``wk`` subcommand.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: the invoked stage's exit code, or 0 on success.
    """
    args = list(argv) if argv is not None else None
    try:
        code = app(args=args, standalone_mode=False)
    except SystemExit as exc:  # pragma: no cover - Typer help/usage edge case
        return int(exc.code) if isinstance(exc.code, int) else 0
    return code if isinstance(code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
