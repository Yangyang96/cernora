# Contributing to Cernora

Thank you for helping improve Cernora. Contributions should preserve its narrow purpose:
deterministic, offline evaluation of already completed agent exports.

## Before you start

- Keep the evaluator independent of agent execution. It must not launch, credential,
  supervise, sandbox or clean an agent process.
- Keep Agent Runtime and Experiment Harness implementations outside this package. Cernora may
  accept a pure completed-export Adapter, but it must not absorb execution or orchestration.
- Do not add a Profile registry, automatic discovery, marketplace, hosted service or
  runtime-provider abstraction.
- Do not include secrets, private evidence, real endpoint details, personal paths, raw
  transcripts or customer data in code, fixtures, documentation or commit messages.
- Discuss compatibility-sensitive changes before implementation when the repository's
  issue tracker is available.

See the [architecture](docs/public/architecture.md),
[compatibility matrix](docs/public/compatibility-matrix.md), and
[evidence policy](docs/public/evidence-publication-and-rebuild.md) before changing a public
contract.

## Development setup

Cernora supports Python 3.12 and 3.13. Install `uv`, clone the repository, and create the
locked development environment:

```sh
uv sync --all-groups
```

Run focused tests while developing. Before submitting a change, run the complete local
gate from the repository root:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m build
git diff --check
```

For a release candidate, one command runs those gates, builds into a fresh temporary directory,
verifies the exact wheel and source archive, installs the wheel offline, and exercises the
complete Profile authoring loop:

```sh
uv run python scripts/release.py preflight
```

After publishing, `uv run python scripts/release.py verify --version <version>` verifies the
production-PyPI files and clean Python 3.12/3.13 installed flows. See the
[local release checklist](docs/public/local-release-checklist.md) for the review boundary.

## Change requirements

Pull requests should:

1. explain the user-visible behavior and compatibility tier affected;
2. include deterministic tests for success, behavioral failure and malformed or
   incompatible input where applicable;
3. preserve strict unknown-field, version, identity, digest and authority checks;
4. classify missing, corrupt or unverifiable evidence as inconclusive rather than pass;
5. keep fixtures small, neutral, reproducible and free of credentials or machine-specific
   data; and
6. update `CHANGELOG.md` and migration notes for any Preview or Supported Preview change.

Do not weaken a fixture, expected observation, score, threshold or gate to make a test pass.
Fix the implementation or explain why the contract itself needs a reviewed versioned
change.

## Compatibility policy

Supported Preview interfaces remain compatible throughout `0.1.x`. A breaking change to
those interfaces requires `0.2.0` and migration notes. Profile and Adapter authoring APIs
are Preview: they may evolve within `0.1.x`, but breaking changes require a changelog entry,
migration notes and deprecation first where feasible. Internal modules carry no
compatibility promise.

EvidenceBundle v2 and import v2 are the only public input formats in `0.1.x`. Evidence,
Score and GateDecision retain their v1 wire identifiers; do not relabel or reinterpret
those bytes.

## Documentation and provenance

Use relative links, runnable commands and public names only. Generated evidence should be
rebuildable by a documented deterministic command. Digests establish content integrity;
they do not prove who produced content, malicious-producer resistance or immutable
history.

Contributions are accepted under the Apache License 2.0 as described in `LICENSE`.
