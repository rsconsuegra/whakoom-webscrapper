# Architecture Decision Records

Numbered records of significant technical decisions for the Whakoom scraper (V2).

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](0001-rewrite-as-httpx-pipeline.md) | Rewrite V2 as a plain-Python httpx pipeline | Accepted |
| [ADR-0002](0002-cookie-backed-series-resolution.md) | Cookie-backed (login) resolution for list → series | Accepted |
| [ADR-0003](0003-external-enrichment.md) | External enrichment (MAL/AniList/MangaUpdates) from day one | Accepted |
| [ADR-0004](0004-python-313-and-uv.md) | Python 3.13 runtime + uv for all command execution | Superseded by 0011 (version-floor point only) |
| [ADR-0005](0005-precommit-system-language.md) | Pre-commit lint hooks run with `language: system` against the uv venv | Accepted |
| [ADR-0006](0006-http-retry-and-transient-error-contract.md) | HTTP retry and transient-error contract | Accepted |
| [ADR-0007](0007-bandit-safe-randomness-and-hashing.md) | Bandit-safe randomness and hashing (project-wide precedent) | Accepted |
| [ADR-0008](0008-name-aware-resolution-nullable-series-name.md) | Name-aware resolution with nullable `series.name` | Accepted |
| [ADR-0009](0009-per-list-reconciliation.md) | Per-list reconciliation instead of item upsert | Accepted |
| [ADR-0010](0010-typer-rich-cli.md) | Typer + Rich CLI (replaces the V2.md argparse wording) | Accepted |
| [ADR-0011](0011-python-313-only.md) | Python 3.13-only runtime | Accepted |

New ADRs get the next free `NNNN` number. Superseded ADRs are never edited in place — write a new
ADR that supersedes them and update the table above.
