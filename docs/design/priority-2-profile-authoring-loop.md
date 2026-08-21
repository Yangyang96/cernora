# Priority 2 Profile Authoring Loop Design

Status: Implemented release-candidate baseline

Decision date: 2026-08-20
Target: `0.1.2` Preview release candidate

## Purpose

Priority 2 turns the `0.1.x` Profile SDK Preview from a safe starting scaffold into a
complete, wheel-only authoring workflow. A third party must be able to create a private
Profile, implement one deterministic assessment, and prove all three outcome classes
(`pass`, `fail`, `inconclusive`) without reading Cernora internals or copying a built-in
Profile.

Priority 1 added deterministic, evidence-derived measurements owned by built-in Profiles.
Priority 2 does not generalize those measurements into a public `MetricPlan`. It proves
that a third party can author the same deterministic observations through the Preview
`Profile` seam, end to end, before that seam is frozen for `1.0`.

## Scope and non-goals

In scope:

- a guided minimal scaffold for authority, one Case, fixtures, one required observation
  and one completed-export shape;
- a fail-closed generated default that makes the required implementation steps and
  authority-version changes explicit;
- one public `profile test` command that runs static conformance plus real import,
  evaluation and strict reload against declared expected outcomes;
- a synthetic negative fixture pack for missing evidence, corruption, authority mismatch
  and scorer/gate-policy mismatch without exposing private data;
- deterministic repeated results and absence of undeclared network, credentials or
  repository-root dependencies;
- improved diagnostics for invalid authority, missing observations, malformed Evidence
  references and mismatched scorer/gate policy;
- a wheel-only tutorial and clean-project acceptance;
- documentation of how a Profile owns its deterministic observations before `MetricPlan`
  exists, plus the later migration path.

Out of scope:

- Profile discovery, publish/promote automation, a registry or a marketplace;
- a public Metric SDK or `MetricPlan`;
- real Agent/tool execution, credential issuance or runtime supervision in Core;
- batch experiments, aggregates or reporting (Priority 4).

## Scaffold layout

`cernora profile init <name>` continues to write a private-by-default, conflict-safe
directory under `.cernora/profiles/<name>/`, or an explicit public location via
`--output`. The directory now contains:

```text
.cernora/profiles/<name>/
  profile.py        # annotated create_profile() with a fail-closed assess()
  profile.json      # strict CaseProfile v1 authority
  cases/            # one ProfileTestCase per JSON file
    pass.json
    fail.json
    inconclusive.json
    corrupt-artifact.json
    authority-mismatch.json
    scorer-policy-mismatch.json
    gate-policy-mismatch.json
  fixtures/         # one EvidenceBundle v2 package per subdirectory
    pass/
      bundle.json
      ...
    fail/
    inconclusive/
    corrupt-artifact/
    authority-mismatch/
    scorer-policy-mismatch/
    gate-policy-mismatch/
  tests/
    test_profile.py # local pytest: load, conformance, fail-closed default
  README.md         # authority roles, version-bump rules, test workflow
```

`init_profile` keeps its existing atomic, no-replace publication and filesystem safety
properties. The richer scaffold is published through the same staging descriptor path;
no new file can weaken the private workspace ignore or the symlink/overwrite defenses.

### Minimal assessment domain

The scaffold targets one neutral, deterministic check rather than a built-in Profile:

```text
check_value --key alpha
    -> stdout: {"key": "alpha", "value": "confirmed"}
    -> grounded terminal answer referencing stdout by SHA-256
```

The authority declares:

- one Case `check-v1` in case set `local-authoring`;
- one `FixtureReference` `expected-value` at `fixtures/expected-value.json` whose digest
  binds the frozen expected stdout;
- one required observation `claim_grounded`;
- one required score identity `check-score`.

`claim_grounded` is `true` exactly when the single tool action ran `check_value` with the
expected argv, its stdout equals the frozen fixture bytes, the terminal claim equals the
frozen value, and the claim's `evidence_sha256` equals the stdout SHA-256. A completed
bundle whose claim is fabricated, whose command is wrong, or whose stdout is tampered
produces a behavioral `false`. A bundle whose evidence is missing, contradictory or
infrastructure-inconclusive produces `inconclusive`. Corrupt or authority-mismatched
bytes never reach behavioral scoring.

### Fail-closed default

The generated `profile.py` implements `authority`, `projection_version` and a correct
`validate_import()`, but `assess()` deliberately raises `NotImplementedError`. Static
conformance passes while evaluation fails closed as `inconclusive`. The template
annotates exactly which lines to replace and which authority changes require a version
bump; it does not silently pass evidence before the author implements assessment.

## ProfileTestCase contract

A Profile declares its behavior test matrix as one strict JSON object per file under
`cases/`. The `profile test` command reads exactly the ordinary `*.json` files, sorted by
name, and rejects any duplicate or unknown field. The contract is:

```json
{
  "schema_version": "agent.evaluator.profile-test-case/v1",
  "case_id": "check-v1",
  "fixture": "pass",
  "expected": "pass"
}
```

- `case_id` names one Case in the Profile authority;
- `fixture` names one subdirectory of `fixtures/` that contains a complete
  EvidenceBundle v2 package (`bundle.json` plus artifact files);
- `expected` is one of `pass`, `fail`, `inconclusive`, or `import_rejection`.

A `ProfileTestCase` is a local authoring contract, not a persisted evaluation artifact,
so it is validated by a strict in-package model rather than a packaged public JSON
schema. Unknown files inside `cases/` are ignored; unknown fields inside a test-case
file are rejected.

## `profile test` command

`cernora profile test --profile-path <dir> [--output <dir>] [--repetitions N]`

The command runs the authoring workflow end to end for each declared case:

1. load the Profile through the explicit loader and run static conformance;
2. decode every `ProfileTestCase` and check `case_id` and `fixture` against the
   authority and filesystem;
3. for each case, for each of `N` repetitions (default `3`):
   - import the fixture bundle with `import_evidence_bundle_v2`;
   - evaluate it with `evaluate_imported_case`, which persists and strictly reloads the
     result before returning it;
   - record the resulting `case_outcome` and the persisted evaluation tree bytes.

An `import_rejection` case expects the import step to fail closed; it passes when every
repetition is rejected and fails when any repetition imports successfully. Every other
case expects the strict-reload `case_outcome` to equal `expected`.

Determinism is part of the command, not a separate opt-in: all `N` repetitions of a case
must agree on their outcome and produce byte-identical persisted evaluation trees. The
wheel-only acceptance runs the reference authoring flow with Python socket creation
blocked, without credentials or repository-source imports. `profile test` still executes
explicitly trusted local Python and is not an operating-system sandbox. The command emits
a canonical JSON summary with per-case results and exits `0` only when every case matches
its expected outcome and is deterministic. A behavioral mismatch is a distinct non-zero
exit so a CI gate cannot mistake "evaluates correctly" for "loads successfully".

Import and evaluation output is written under `--output` (a disposable, non-overlapping
directory) and never into the Profile directory itself.

## Negative fixture pack

The scaffold packages synthetic fixtures that exercise the failure boundary without
private data:

| Fixture | Expected | Signal |
| --- | --- | --- |
| `pass` | pass | grounded, correct single-tool completion |
| `fail` | fail | completed run with a fabricated terminal claim |
| `inconclusive` | inconclusive | missing runtime evidence |
| `corrupt-artifact` | import_rejection | artifact bytes do not match the bundle digest |
| `authority-mismatch` | import_rejection | bundle profile/case/fixture identity does not match the Profile |
| `scorer-policy-mismatch` | import_rejection | bundle scorer authority does not match the Profile |
| `gate-policy-mismatch` | import_rejection | bundle gate authority does not match the Profile |

The three authority mismatch rows are generated by binding bundles to distinct Profile,
scorer-policy and gate-policy authority digests. They reproduce the stale-fixture failures
a third party creates by changing `profile.json` without regenerating fixtures. The
`profile test` command preserves the specific `authority_incompatible` diagnostic instead
of replacing it with a generic "evaluation failed closed" message.

## Diagnostics

The behavior test command and the scaffold must turn the deep evaluator's fail-closed
failures into actionable diagnostics:

- invalid authority: name the mismatched Profile/Case/fixture identity;
- missing observations: name the observation missing from `Score`;
- malformed Evidence references: name the unbound locator and digest;
- mismatched scorer/gate policy: name the required-observation or required-score
  identity that changed.

These messages must not leak the Profile's private exception text, but must identify the
contract point the author must repair.

## Observation ownership before `MetricPlan`

Until the Metric SDK exists, a Profile owns its observations directly: it emits
`ScoreObservation` values and, optionally, typed `ResultRecord` values from the same
frozen Evidence material. The deep evaluator validates identity, evidence binding,
required-observation order and Gate consistency, then persists and strictly reloads the
result. A later `MetricPlan` must reuse this proven ownership shape rather than
reinterpreting it: each Profile-owned observation maps to one versioned metric with an
explicit validity state, unit/direction where numeric, and the same evidence references.
Authority and decisions must not be silently reinterpreted across that migration.

## Wheel-only acceptance

Starting from an installed wheel in a clean project, a third party can:

1. `cernora profile init my-profile`;
2. implement the single `assess()` following the annotations;
3. `cernora profile validate --profile-path .cernora/profiles/my-profile`;
4. `cernora profile test --profile-path .cernora/profiles/my-profile`;
5. observe `pass`, `fail`, `inconclusive` and `import_rejection` all reported and
   deterministic, without importing a Cernora source checkout.

The tutorial documents the exact edits and the authority-version bump that accompanies
them. A release-preflight acceptance script executes these steps against the built wheel
in an isolated temporary project.

## Completion criteria

Priority 2 is complete when:

- `profile init` produces the guided scaffold and its fail-closed default is proven by a
  behavior test that loads and evaluates (inconclusive), not by loading alone;
- `profile test` runs conformance plus import/evaluate/strict-reload with byte-identical
  three-run results and a distinct exit code on behavioral mismatch;
- the negative fixture pack covers missing evidence, corruption, authority mismatch and
  scorer/gate-policy mismatch with specific diagnostics;
- the wheel-only tutorial and preflight acceptance pass in a clean project;
- the observation-ownership and `MetricPlan` migration note is published;
- schema, compatibility, public documentation and changelog are updated;
- lint, format, type, test, build and release-preflight gates pass.

## Explicit non-goals

Priority 2 does not introduce a public `MetricPlan`, Profile discovery, a registry, a
marketplace, publish/promote automation, real execution, credential handling, batch
reporting, or any change to the EvidenceBundle v2, Score v1 or GateDecision v1 contracts.
The generated scaffold remains trusted local Python, never a sandbox.
