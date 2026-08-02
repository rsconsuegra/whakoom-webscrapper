# ADR-0005 — Pre-commit lint hooks run with `language: system` against the uv venv

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** (none)

## Context

pre-commit hooks normally run in per-hook isolated virtualenvs. That created a dependency-mirroring
problem: tools and their importable deps (e.g. pylint resolving `httpx`, `python-dotenv`, `pytest`,
`parsel`, `tenacity`, `duckdb`) had to be listed as `additional_dependencies` in
`.pre-commit-config.yaml`, duplicating `pyproject.toml` and risking drift. This project mandates that
all commands run through the single `uv` venv (ADR-0004), so every lint tool is already installed
there as a `dev` dependency.

## Decision

Run the lint hooks with `language: system` so they execute the exact binaries from the uv venv:

- Hooks switched to `system`: `flake8`, `isort`, `pyupgrade`, `ruff-check`, `ruff-format`, `pylint`,
  `mypy`, `pydocstyle`, `sqlfluff-lint`, `sqlfluff-fix`.
- The tools were added to `[dependency-groups.dev]` (flake8, isort, pyupgrade, pylint, pydocstyle,
  sqlfluff; ruff/mypy were already present). Versions are pinned once in `uv.lock`.
- pylint's `additional_dependencies` block was removed; import resolution is handled natively by the
  venv.
- `language: system` is set **per-hook**, not at the repo level: pre-commit warns and ignores a
  repo-level `language` key.
- `pre-commit-hooks` (end-of-file-fixer, trailing-whitespace, etc.) still use their own env — they are
  not Python tooling and stay as-is.

## Consequences

**Positive:** a single source of truth for tool versions (`pyproject.toml` + `uv.lock`); no manual
dependency mirroring in the pre-commit config; pylint resolves all imports natively; faster hook
startup (no per-hook env creation).

**Negative:** hooks only work when run through the venv (`uv run pre-commit`); the config `rev` pins
become advisory for these hooks (real versions come from `uv.lock`); contributors who run a global
`pre-commit` will get failures or wrong tool versions.

## Alternatives considered

- **Keep `language: python` + `additional_dependencies`** — rejected: two sources of truth to keep in
  sync manually.
- **`language: script` / custom wrappers** — rejected: adds indirection with no benefit over
  `language: system` given the uv mandate.
