# ADR-0004 — Python 3.13 runtime + uv for all command execution

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)

## Context

The V2 plan targets Python 3.12+. The repo mandates `uv` for dependency management and command
execution (AGENTS.md). The exact interpreter was not pinned before implementation.

## Decision

- Pin the runtime to **Python 3.13** (`.python-version` = `3.13`; venv resolved by `uv`).
  `requires-python` in `pyproject.toml` stays `>=3.12`, so the package remains installable on 3.12+.
- **All** commands run via `uv run` (never bare `pip`/`scrapy`/`ruff`/`pylint`/etc.); `uv sync` is the
  only way to install dependencies.
- Tooling pins (`ruff`, `mypy`, `pylint`, `bandit`, `pre-commit`) live in `[dependency-groups.dev]`
  and `uv.lock`; `pyproject.toml` configures them (`[tool.ruff]`, `[tool.mypy]`, `[tool.pylint.*]`,
  `[tool.bandit]`), including `[tool.mypy] exclude = ["^whakoom_webscrapper/"]` because the frozen
  legacy package cannot import its removed deps.

## Consequences

**Positive:** one interpreter source of truth; reproducible environments via `uv.lock`; quality tools
run on the exact installed versions; mypy targets 3.13 and legacy is excluded cleanly.

**Negative:** contributors must use `uv` (no global tools); running `pre-commit` outside the venv will
fail lint hooks that rely on venv-installed tools (see ADR-0005).

## Alternatives considered

- **Stay on 3.12 as the run interpreter** — rejected: 3.13 is current, `requires-python` remains
  `>=3.12` so compatibility is preserved.
- **Allow bare global tool calls** — rejected: explicit `uv run` is a hard AGENTS.md rule.
