# Changelog

All notable changes to Cernora are documented here. The project follows semantic versioning
while pre-1.0 compatibility is further defined by the documented compatibility tiers.

## Unreleased

### Added

- `ComparisonInput v1` Primary Outcomes may now select one declared split. The derived Primary
  rates, delta and case-clustered interval use only Cases in that split, allowing held-out-only
  confirmatory conclusions without excluding development or regression evidence from the Batch.

### Compatibility

- Existing `scope: "all"` Primary Outcomes retain their semantics and exact canonical wire shape;
  they do not gain a serialized `split_id`. Split-scoped producers must provide a known
  `split_id`. Guardrails and diagnostic outputs retain their independently declared scopes.

## 0.1.4 - 2026-08-27

### Added

- Preview `Treatment` v1, `ComparisonInput` v1 and `ComparisonSummary` v1 contracts for exactly
  two configurations in one complete Batch Input, with exhaustive controlled-invariant checks.
- Fixed case-clustered paired bootstrap/v1, Reliable Success Rate, qualified pass@k/pass^k,
  hard Guardrails, paired outcome transitions and evidence-bound failure-code migration.
- Canonical comparison publication and strict reload, public schemas, package-root APIs,
  `cernora comparison validate`/`summarize`, and offline wheel-only acceptance.

### Compatibility

- Comparison surfaces are additive Preview APIs in the local `0.1.4` release candidate. Existing
  evidence, Profile, evaluation and M2 Batch contracts are unchanged; M2 callers need no migration.
  Comparison producers must use versioned schemas and may not submit authored statistics or claims.

## 0.1.3 - 2026-08-27

### Added

- Preview `BatchInput` v1 and `BatchSummary` v1 contracts for complete, content-identified
  experiment matrices with embedded, manifest-bound Evaluation Packages or normalized lifecycle
  records.
- Validity-first aggregation with four closed Trial outcomes, exact overall and grouped rates,
  retry and Attempt diagnostics, canonical JSON, deterministic Markdown, atomic publication and
  strict reload.
- Package-root batch models and functions plus `cernora batch validate` and
  `cernora batch summarize`. Valid summaries use exit `0` regardless of behavioral quality;
  malformed or unverifiable inputs use exit `3`.

### Compatibility

- Batch surfaces are additive Preview APIs in the local `0.1.3` release candidate. Existing
  evidence, Profile, import and evaluation contracts are unchanged. Batch callers must use the
  versioned schemas and cannot submit caller-calculated rates or naked pass/fail JSON.

## 0.1.2 - 2026-08-21

### Added

- A guided `cernora profile init` scaffold with one implementable assessment, annotated
  fixtures, a packaged synthetic EvidenceBundle v2 negative fixture set, local tests and a
  fail-closed default that never passes completed evidence before `assess()` is implemented.
- A `cernora profile test` command that runs static conformance plus real import, evaluation
  and strict reload for every declared `cases/*.json` row, requires byte-identical repeated
  results, and reports a distinct exit code on behavioral mismatch.
- A wheel-only `scripts/profile_authoring_wheel_check.py` acceptance that authors a Profile
  from an installed wheel and reaches `pass`, `fail`, `inconclusive` and `import_rejection`.

### Changed

- Profile behavior tests now bind every declared Case to the Profile authority and fixture,
  retain specific import-rejection diagnostics, and reject missing observations, scorer
  mismatches and unbound Evidence references before a GateDecision can pass.
- The release preflight installs its freshly built wheel offline and runs the complete Profile
  authoring acceptance; CI repeats that wheel-only flow on Python 3.12 and 3.13.

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
