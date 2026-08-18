# Cernora documentation

- [Architecture](architecture.md): complete-system composition, evaluator boundaries, data
  flow and authority.
- [Product roadmap](../../ROADMAP.md): outcome-ordered growth without absorbing Agent Runtime
  or Experiment Harness ownership.
- [Profile authoring](profile-authoring.md): create, implement and validate a local
  Profile.
- [Adapter conformance](adapter-conformance.md): normalize a completed export into a
  closed EvidenceBundle v2 tree.
- [Evidence publication and rebuild](evidence-publication-and-rebuild.md): what may be
  published and how generated evidence is reproduced.
- [Public evaluation-core and deterministic metric acceptance](acceptance.md): synthetic
  completed-export replay, frozen tool/coding matrices, scope limits and exact rebuild command.
- [Compatibility matrix](compatibility-matrix.md): `0.1.x` stability tiers and versioned
  contracts.
- [Local release checklist](local-release-checklist.md): source, artifact and wheel-only
  checks before a release candidate is handed off.
- [Release-day runbook](release-day-runbook.md): repository settings, immutable release
  actions, Trusted Publishing and post-release verification.

Release maintainers use `uv run python scripts/release.py preflight` before publication and
`uv run python scripts/release.py verify --version <version>` after production publication.

Start with the project [README](../../README.md) for installation and a runnable offline
example.
