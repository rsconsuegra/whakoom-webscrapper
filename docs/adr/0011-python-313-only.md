# ADR-0011 — Python 3.13-only runtime

- **Status:** Accepted
- **Date:** 2026-08-02
- **Supersedes:** ADR-0004 — **on the `requires-python = ">=3.12"` point only**.
  ADR-0004's uv / `uv run` / toolchain-pin content remains valid and in force.

## Context

ADR-0004 pinned the **interpreter** to Python 3.13 (`.python-version` = `3.13`, venv
rebuilt by `uv`) but left `requires-python = ">=3.12"` so the package stayed
installable on 3.12. That hedge was inherited from `V2.md` §4.1, written before any
code existed.

Two seasons of Phases 0–2 and the PRE_PHASE3 stabilization have shown:

- **No 3.12 user exists.** This is a single-owner hobby project; the only machine
  that runs it has 3.13.x installed via `uv`. No CI matrix, no published wheel
  consumed by a third party.
- **Every tool already assumes 3.13.** `.python-version` pins 3.13; `[tool.ruff]
  target-version = "py313"`; `[tool.mypy] python_version = "3.13"`;
  `pyrightconfig.json` `"pythonVersion": "3.13"`. The `>=3.12` floor is the only
  place that still claims 3.12 compatibility — and the code freely uses
  3.13-era stdlib behavior.
- **The hedge invites drift.** A future contributor reading `>=3.12` could assume
  3.12 is tested; it is not. Carrying an untested floor is dishonest and costs more
  than it saves (see "No slope" in AGENTS.md §1).
- **PRE_PHASE3 owner decision (2026-08-02):** Python 3.13 only; other interpreters
  are **out of scope** for this project (see `PRE_PHASE3_PLAN.md` S1.3.I3).

## Decision

The project is **Python 3.13-only**:

1. `pyproject.toml`: `requires-python = ">=3.13"`.
2. Classifiers: `Programming Language :: Python :: 3.13` only; the
   `Python :: 3.12` classifier is removed.
3. Tool config (`[tool.ruff] target-version`, `[tool.mypy] python_version`,
   `pyrightconfig.json`) already targets 3.13 — left as-is.
4. Supporting other Python versions (3.12, 3.14, pypy, etc.) is explicitly **out of
   scope**. A future change of interpreter is a new ADR that supersedes this one.

## Consequences

**Positive:** one source of truth for the runtime; `requires-python` matches the
venv, the tools, and `.python-version`; no untested compatibility claim to maintain;
mypy/ruff can assume 3.13 stdlib unconditionally.

**Negative:** the package will refuse to install on 3.12. That is acceptable — there
is no 3.12 install path today and none is planned. Anyone needing 3.12 support must
write a new ADR and re-validate the whole stack on that interpreter.

**Scope note:** ADR-0004's `uv` / `uv run` / `[dependency-groups.dev]` /
`exclude = ["^whakoom_webscrapper/"]` content is unaffected and remains in force.
Only the `requires-python` claim is superseded.

## Alternatives considered

- **Keep `>=3.12`.** Rejected: untested, dishonest, and the project never runs on
  3.12. See Context.
- **Bump to `>=3.14`.** Rejected: 3.14 is not yet the venv interpreter; bumping the
  floor above the actual runtime would re-create the same drift this ADR removes.
- **Add a 3.12 CI matrix to back the claim.** Rejected: out of scope for a
  single-owner project; the matrix would be unrun and rot.
