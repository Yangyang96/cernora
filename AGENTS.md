# Repository Guidelines

## Scope and contracts

- Cernora evaluates completed agent exports deterministically and offline. Keep
  agent execution and runtime orchestration outside this package.
- Preserve strict public-contract validation: unknown fields, identities, versions
  and digest mismatches must not be silently accepted. Missing or unverifiable
  evidence is inconclusive, never pass. Do not weaken fixtures or thresholds to pass tests.
- For public-contract changes, consult [CONTRIBUTING.md](CONTRIBUTING.md) and the
  [compatibility matrix](docs/public/compatibility-matrix.md). Update `CHANGELOG.md`
  and migration notes for Preview or Supported Preview changes.

## Code and references

- Code lives in `src/cernora/`: `core/` owns domain types and validation,
  `ingestion/` and `evaluation/` import evidence, `composition/` scores and gates,
  and `cli/` provides commands. Keep JSON resources beside their owning modules.
- Tests are grouped by contract in `tests/public/`, `tests/public_sdk/` and
  `tests/public_profiles/`. Keep fixtures neutral, reproducible and offline.
- Use CPython 3.12 or 3.13 with `uv sync --all-groups`. Follow `pyproject.toml`
  for formatting, lint and typing; use explicit type annotations.
- Use `docs/public/` for architecture, compatibility and release details relevant
  to the task. Reuse `.agent/` for local task state; completed Pilot records do
  not activate work or restrict separately authorized new tasks.

## Verification and delivery

- Run focused pytest modules for affected behavior. Package checks are
  `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` and
  `uv run mypy`; check packaging with `uv run python -m build` when relevant.
- For release preparation, use `uv run python scripts/release.py preflight` and
  the [release checklist](docs/public/local-release-checklist.md).
- Use English Conventional Commits with a lowercase imperative subject of at most
  72 characters; add a concise body explaining non-trivial changes and validation.
- Follow current task authorization for commit and ordinary push; do not add
  repeated approval steps. Do not create a PR unless requested. Publishing is a
  separate action; never force-push or rewrite published history.
- Stage only task-related changes. Exclude secrets, private evidence, raw transcripts,
  personal paths, local agent state, generated artifacts and unrelated user changes.
