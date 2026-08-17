# Repository Guidelines

## Project Structure & Module Organization

Core package code lives under `src/cernora/`. Domain types and validation are in `core/`, import logic in `ingestion/` and `evaluation/`, scoring and gating in `composition/`, and command-line entry points in `cli/`. Built-in profiles, schemas, and packaged examples keep their JSON resources beside the Python modules that load them. Public tests are grouped by contract boundary in `tests/public/`, `tests/public_sdk/`, and `tests/public_profiles/`. User-facing architecture, compatibility, and release documentation lives in `docs/public/`; maintenance utilities are in `scripts/`.

## Build, Test, and Development Commands

Use CPython 3.12 or 3.13 and run commands from the repository root.

```sh
uv sync --all-groups          # create the locked development environment
uv run pytest -q              # run the complete test suite
uv run pytest -q tests/public/test_core_contracts.py  # run one test module
uv run ruff check .           # lint imports, correctness, and style
uv run ruff format --check .  # verify formatting
uv run mypy                   # run strict package type checking
uv run python -m build        # build wheel and source distribution
```

Before release work, run `uv run python scripts/release.py preflight` to execute and verify the full release gate.

## Coding Style & Naming Conventions

Follow Ruff's Python 3.12 rules and 100-character line limit from `pyproject.toml`. Use four-space indentation, explicit type annotations, `snake_case` for modules/functions/variables, and `PascalCase` for classes. Keep public contracts versioned and validation strict: do not silently accept unknown fields, identities, versions, or digest mismatches. Store package data with the owning module and use neutral, reproducible fixture names such as `backend-v1.json`.

## Testing Guidelines

Tests use pytest and should be deterministic, offline, and named `test_*.py`. Apply the configured `unit`, `integration`, or `adversarial` marker when classification adds value. Cover successful behavior, behavioral failure, and malformed or incompatible input. Missing or unverifiable evidence must remain inconclusive, never pass. Do not weaken fixtures, thresholds, or expected observations merely to satisfy a test.

## Commit & Pull Request Guidelines

Recent history uses concise, imperative, sentence-case subjects (for example, `Generalize the release workflow (#2)`). Keep commits focused and avoid secrets, customer data, raw transcripts, personal paths, or real endpoints. Pull requests should explain user-visible behavior and compatibility impact, link relevant issues, include deterministic tests, and update `CHANGELOG.md` plus migration notes for Preview or Supported Preview changes. Consult `CONTRIBUTING.md` and `docs/public/compatibility-matrix.md` before changing a public contract.
