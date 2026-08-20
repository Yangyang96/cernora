# Changelog

All notable changes to Cernora are documented here. The project follows semantic versioning
while pre-1.0 compatibility is further defined by the documented compatibility tiers.

## Unreleased

## 0.1.1 - 2026-08-20

### Added

- Preview `ResultRecord` v1 and `EvaluationReport` v1 contracts, public schemas and strict
  manifest-bound persistence for Profiles that opt in to structured results.
- The separately versioned `builtin:tool-workflow` Profile with a frozen 18-case
  synthetic acceptance matrix covering pass, behavioral fail, inconclusive and corrupt
  input outcomes.
- The separately versioned `builtin:coding-evaluation` Profile with Candidate Tree
  v1 reconstruction, Profile-owned frozen execution capsules, F2P/P2P diagnostics, derived
  diff and tamper policy, and a 20-row deterministic acceptance matrix. The existing
  `builtin:coding-task` Profile is unchanged.
- One release-maintainer command for complete local preflight and one for production-PyPI
  artifact, clean-install and acceptance-flow verification on Python 3.12/3.13.

### Changed

- `ProfileAssessment` now has an additive optional `result_records=()` field. Existing
  Profiles retain their prior Score/Gate behavior and do not emit an evaluation report
  unless they supply records.
- CI, artifact inspection, Trusted Publishing and the release runbook now derive artifact
  names from the declared version instead of hard-coding `0.1.0`.

## 0.1.0 - 2026-08-14

Initial public release.

### Added

- Offline completed-export evaluation through EvidenceBundle v2, canonical import and
  strict reload.
- Evaluator-owned Evidence v1, Score v1 and GateDecision v1 composition with fail-closed
  outcomes.
- Explicit built-in offline-workflow and coding-task Profiles.
- Preview Profile and Adapter authoring protocols plus conformance helpers.
- Private-by-default project-local Profile scaffolding and explicit trusted local loading.
- Wheel-packaged workflow and coding examples that perform adapt, import, evaluate and strict
  result reload without repository assets.
- A sanitized V1/V2 representative acceptance rebuild with deterministic three-run results
  and corrupt, missing, authority-mismatch and traversal fail-closed checks.
- Apache-2.0 governance, compatibility, evidence-publication and local release guidance.

### Documentation

- Clarified that Cernora is the independent evaluation core in a composed system. Packaged
  examples start from synthetic completed exports and do not claim Agent-runtime, sandbox,
  runtime-receipt capture or Experiment Harness acceptance.

### Changed

- No product-code or wire-contract change was made after final candidate acceptance;
  release-day changes are limited to publication metadata and documentation.

### Compatibility

- Python 3.12 and 3.13 are the supported language targets; operating-system support is
  narrower and follows the documented native-evidence matrix.
- EvidenceBundle v2 and import v2 are the only accepted public input formats.
- Supported Preview surfaces are preserved within `0.1.x`; authoring APIs are Preview and
  may evolve with changelog and migration notes.
