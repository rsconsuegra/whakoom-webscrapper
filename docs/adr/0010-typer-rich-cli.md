# ADR-0010 — Typer + Rich CLI (replaces the V2.md argparse wording)

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** the CLI wording in `V2.md` §16 (not an ADR; this is the first ADR on the CLI tool)
- **Related:** ADR-0004 (Python 3.13 + uv toolchain that this CLI runs under)

## Context

`V2.md` §16 specified **stdlib `argparse`** for the `wk` console script, with no
third-party CLI library in the dependency list. During Phase 0 scaffolding the
owner chose to implement the CLI with [`typer`](https://typer.tiangolo.com/)
(>=0.12) on top of [`rich`](https://rich.readthedocs.io/) (>=13) instead.

Drives for the choice:

- **UX/DX:** `rich`-rendered help, colored error output, and `--help` tables are
  materially better than argparse's plain text for a 7-command staged CLI that the
  owner runs interactively several times a day.
- **Typed options without boilerplate:** `Annotated[bool, typer.Option(...)]` lets
  each flag carry its help string inline, keeping `cli.py` short and self-documenting
  (mypy-checked, no `dest=`/`add_argument` ceremony).
- **Subcommand isolation:** each stage is its own function; the stage→command
  mapping is the same as the stage→pipeline-module mapping in V2 §5, so adding a
  stage later is one decorated function.

The implementation already exists at `whakoom_scraper/cli.py` and is covered by
`whakoom_scraper/tests/test_phase0_smoke.py` (Typer `CliRunner`). This ADR records
the decision so `V2.md` and the code stop contradicting each other.

## Decision

The `wk` CLI is built with **typer + rich** and is the single CLI for the project:

```python
app = typer.Typer(
    name="wk",
    help="Whakoom V2 scraper — staged manga/comic list collection and analysis.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
```

Surface area (the 7 commands mandated by V2 §16 / AGENTS.md §3):

| Command | Stage | Flags |
|---|---|---|
| `wk lists` | 1 | `--reset` |
| `wk list-detail` | 2 | `--list-id N`, `--all` |
| `wk resolve` | 3 | `--limit N` |
| `wk series` | 4 | `--force`, `--limit N` |
| `wk validate` | 5 | — |
| `wk analyze` | 6 | `--force` |
| `wk run-all` | 1→5 | — |

Conventions fixed by this ADR:

- `rich_markup_mode="rich"` so help strings can use rich tags (`[bold]...[/]`).
- Options are declared `Annotated[T, typer.Option(help="...")]`; grouping via
  typer's option ordering, not argparse argument groups.
- `main(argv: Sequence[str] | None = None) -> int` returns the exit code; help/usage
  flows through `typer.Exit` / `SystemExit` so exit codes match V2 §16
  (`0` success, `1` stage failure, `2` validation failure, `3` session expired).
- Tests use `typer.testing.CliRunner` against `app`, never a subprocess.
- The V2 §16 wording "`Stdlib argparse`" is **retired** (see V2.md §16 update
  pointing here); the command set, flags, and exit codes in V2 §16 stay authoritative.

## Consequences

**Positive:** one consistent, typed, colorized CLI; help text lives next to each
option; adding a stage is one function; rich error output makes stage failures easy
to scan in long runs; `CliRunner` keeps CLI tests fast and offline.

**Negative:** two extra runtime dependencies (`typer`, `rich`) — both already pinned
in `pyproject.toml`, maintained by the same author, and well within the project's
"explicit, small dep set" budget. Typer carries `click` transitively; that cost is
accepted. Any contributor expecting argparse will be surprised — this ADR plus the
V2.md pointer is the mitigation.

## Alternatives considered

- **Stay on stdlib `argparse`** (the original V2 §16 wording). Rejected: the owner
  runs this CLI interactively every working session and the DX gap is real; argparse
  help formatting is bland and option grouping is verbose. The dependency cost of
  typer+rich is negligible against the daily benefit.
- **Use `click` directly.** Rejected: typer gives the same engine with typed
  `Annotated` options and richer help out of the box, with strictly less boilerplate.
- **Use `defopt` / `defarg` style "function signature is the CLI".** Rejected:
  smaller ecosystems, weaker help rendering, less active maintenance.
