"""Command-line entry point for the Whakoom V2 scraper.

Defines the ``wk`` console script. Each subcommand maps to a pipeline stage;
stages are implemented in later phases and are stubbed here.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Annotated

import typer

from whakoom_scraper.config import load_settings
from whakoom_scraper.pipeline.stage_list_detail import run_list_detail
from whakoom_scraper.pipeline.stage_lists import run_lists
from whakoom_scraper.pipeline.stage_resolve import run_resolve
from whakoom_scraper.pipeline.stage_series import run_series

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


def _not_implemented(command: str, **flags: object) -> None:
    """Report that a stage is not yet implemented, echoing any set flags.

    Exits nonzero so a stub is never mistaken for a completed stage (I1).

    Args:
        command: The name of the requested stage.
        **flags: Option values passed to the stage; truthy ones are echoed so the
            caller can confirm the CLI parsed them correctly.

    Raises:
        typer.Exit: Always, with exit code ``1``.
    """
    parts = [f"[{command}] stage not implemented yet (Phase 0 skeleton)"]
    parts += [f"{name}={value}" for name, value in flags.items() if value]
    typer.echo(" ".join(parts))
    raise typer.Exit(code=1)


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
    _not_implemented("validate")


@app.command()
def analyze(
    force: Annotated[bool, typer.Option(help="Skip the validation gate.")] = False,
) -> None:
    """Stage 6: build DuckDB views and exports."""
    _not_implemented("analyze", force=force)


@app.command("run-all")
def run_all() -> None:
    """Run stages 1-5 in order, stop before analyze on failure."""
    _not_implemented("run-all")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested ``wk`` subcommand.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: ``0`` success, ``1`` stage failure.
    """
    args = list(argv) if argv is not None else None
    try:
        app(args=args, standalone_mode=False)
    except typer.Exit as exc:
        return exc.exit_code
    except SystemExit as exc:  # pragma: no cover - Typer help/usage edge case
        return int(exc.code) if isinstance(exc.code, int) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
