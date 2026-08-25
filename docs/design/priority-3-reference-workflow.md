# Priority 3 Public Reference Evaluation Workflow Design

Status: Completed in the independent companion workflow on 2026-08-25

Decision date: 2026-08-21
Target: separate `cernora-reference-workflow` repository

## Purpose

Priority 3 proves that the released `cernora==0.1.2` wheel can evaluate evidence from a
real external coding Agent without absorbing Runtime ownership into Cernora Core. The
deliverable is a reproducible, local, containerized vertical tracer that runs an external
Agent Runtime, freezes a completed export, adapts that export offline into
`EvidenceBundle v2`, evaluates it with a companion-owned Profile, and strictly reloads the
result.

This document freezes the decisions reached during the Priority 3 design review and records
the completed handoff boundary. The companion repository retains the exact implementation
and acceptance evidence.

## Decision status

The product and architecture choices below were implemented without moving Runtime ownership
into Cernora Core.

The completed execution record covers:

- reproducing the public-wheel baseline and recording the downloaded wheel digest;
- verifying the Harness, Runtime, Docker, authentication and telemetry behavior together;
- creating the companion repository, schemas, fixtures, adapter and Profile;
- executing conformance, failure-injection, repeatability, secret-scan and license gates;
- confirming that the companion repository satisfies its publication gate.

If verification fails, record the observation and revise this document explicitly. Do not
silently substitute a different Runtime, model, harness, authority or export shape.

## Approved baseline

| Concern | Decision |
| --- | --- |
| First workflow | Containerized coding Agent evaluation |
| Companion repository | Separate `cernora-reference-workflow` Git repository |
| Cernora dependency | Exact public-index wheel `cernora==0.1.2` |
| Harness | One exact open-source container-harness pin; recorded in the companion |
| Runtime | One exact external CLI Runtime pin; recorded in the companion |
| Model | `gpt-5.6-terra` |
| Reasoning effort | `medium` |
| Authentication | User subscription through an explicit auth-file path |
| Execution | Local Docker only; live authenticated runs remain manual |
| Web search | Disabled |
| Network claim | Provider egress is allowed; no network-isolation claim |
| Vertical tracer | Synthetic Python `tiny-calculator` repair task |
| Evaluation Profile | Companion-owned `cernora-reference-coding-v1` |
| Test authority | Task-owned deterministic Test Runner receipt |
| Export | Strict `completed-export/v1` allowlist with content hashes |
| Identity | Canonical JSON plus SHA-256 content identity |
| Retry | At most one eligible infrastructure retry after a fixed 10 seconds |
| Supported host | macOS on Apple Silicon, after native acceptance passes |
| CI role | Linux validates frozen exports offline; it does not perform live Runtime runs |
| Publication | Keep private until every release gate passes |

## Why this Harness and Runtime

The external Harness owns tasks, datasets, container lifecycle, trials, Runtime invocation
and raw artifact collection. The companion project adds only the narrow orchestration,
freezing, adaptation and Cernora-specific evaluation required to prove the public boundary.
It must not evolve into a second general-purpose Agent harness.

The selected Runtime supports a local CLI using an operator subscription without making an
API key the baseline. Alternative producers remain possible future connectors; they are not
implementation dependencies for this milestone.

The exact pins are part of the experiment identity. An upgrade is a new compatibility
decision and requires new frozen evidence; it must not silently reinterpret an existing
experiment.

## Ownership boundaries

```text
ExperimentSpec v1                 companion owns intent and identity
    -> pinned external Harness    harness owns task/container lifecycle
    -> pinned external Runtime    Runtime owns Agent behavior
    -> raw trial artifacts        Harness/Runtime diagnostic output
    -> completed-export/v1        companion freezes a closed evidence set
    -> offline Evidence Adapter   companion translates, never re-executes
    -> EvidenceBundle v2          Cernora public import boundary
    -> Profile evaluation         companion-owned assessment authority
    -> strict reload              Cernora proves portable result integrity
```

Cernora Core remains Runtime-vendor neutral. Harness and Runtime dependencies belong only in
the companion repository. The companion must consume Cernora through the installed public
wheel and must not import a source checkout, use repository-relative internals or copy
private package code.

## Companion repository shape

The implementation uses this responsibility-oriented layout. Exact module names may evolve
if the same boundaries remain obvious.

```text
cernora-reference-workflow/
  LICENSE
  README.md
  pyproject.toml
  uv.lock
  docs/
    architecture.md
    compatibility.md
    release-checklist.md
  schemas/
    experiment-spec-v1.schema.json
    completed-export-v1.schema.json
  src/cernora_reference_workflow/
    experiment_spec.py
    lifecycle.py
    export.py
    secrets.py
    adapter.py
    profile.py
    report.py
  tasks/tiny-calculator-v1/
    task.json
    prompt.md
    pyproject.toml
    src/calc.py
    tests/
  tests/
    unit/
    conformance/
    adversarial/
    fixtures/
  scripts/
    verify_public_wheel.py
    run_tracer.py
    verify_release.py
```

The repository is independent, not nested in this repository and not a submodule. Its
license is Apache-2.0. Generated attempts, exports, authentication material and local Agent
state must be ignored by default.

## Vertical tracer

The first task is a neutral, synthetic Python repair named `tiny-calculator-v1`:

- `add()` behaves incorrectly for negative values;
- the task prompt authorizes editing only `src/calc.py`;
- `tests/` and `pyproject.toml` are protected paths;
- two fail-to-pass tests describe the defect;
- two pass-to-pass tests protect existing behavior;
- dependencies are preinstalled in an image pinned by digest;
- task build and tests require no network access.

This task is intentionally small. Priority 3 is proving boundary integrity and evidence
authority, not benchmarking model intelligence. A behavioral-failure fixture is a real
completed external Runtime attempt. A separately versioned harder task may be used instead
of modifying a successful export to look like a behavioral failure.

## Companion-owned Profile

The tracer uses a new explicit Profile authority named
`cernora-reference-coding-v1`, created only through the public Profile SDK.

It does not reuse `builtin:coding-evaluation`. That built-in authority is bound to its own
synthetic producer and oracle assumptions, including an external-action attestation that
does not describe this workflow. Reusing it would make the evidence appear compatible
while changing the meaning of the authority.

The companion Profile is loaded explicitly. Priority 3 does not add Profile discovery,
registration or promotion to Cernora Core. Its assessments are deterministic and derived
from the frozen export. Harness rewards and Runtime success messages may be retained as
diagnostics, but neither is authoritative evidence of pass.

## `experiment-spec/v1`

### Identity

The ExperimentSpec is strict canonical JSON. Its identity is:

```text
experiment_id = sha256(canonical_json(experiment_spec_without_experiment_id))
```

Canonicalization uses UTF-8, lexicographically sorted object keys, no insignificant
whitespace and schema-defined number representations. Unknown fields fail validation.
Every behavior-affecting input is included directly or by a content digest.

### Required behavior-affecting fields

- schema identity and version;
- task identity, task content digest and allowed/protected path policy;
- container image reference including immutable digest;
- Harness name, exact version and configuration digest;
- Runtime name, exact version and non-secret configuration digest;
- model name and reasoning effort;
- prompt and instruction digests;
- timeout and resource limits;
- provider-egress and web-search policies;
- retry policy;
- Test Runner plan and authority digest;
- companion Profile authority and version;
- exporter, adapter and report schema versions;
- Cernora package version and downloaded wheel digest.

### Explicitly excluded fields

- credentials, tokens or the content or digest of authentication files;
- account, organization or subscription identifiers;
- host absolute paths and usernames;
- wall-clock creation times;
- random UUIDs;
- the physical output-root path.

Those values may be needed operationally but must not alter semantic identity or leak into
portable evidence.

## `completed-export/v1`

### Publication model

An export is created in a private staging directory, validated and secret-scanned, then
published atomically with no replacement of an existing identity. The final directory is
closed: every file is allowlisted, every regular file is hashed in `manifest.json`, and
unknown or missing content is an error.

Symlinks, hard-link ambiguity, sockets, devices, named pipes and path traversal are
rejected. The adapter reads the frozen directory read-only and performs no Runtime, shell,
Docker, Git or network actions.

### Allowlisted shape

```text
completed-export/
  manifest.json
  terminal.json
  runtime/
    harness-trial-config.json
    harness-trial-result.json
    runtime-session/*.jsonl
    trajectory.json
    runtime-events.jsonl
  candidate/
    tree-manifest.json
    files/...
  tests/
    test-plan.json
    test-results.json
    stdout.txt
    stderr.txt
  receipts/
    process.json
    resources.json
```

The schema may make individual Runtime diagnostic files optional where the Harness or
Runtime does not emit them, but it must make that optionality explicit. Absence cannot be
represented by inventing an empty file.

`manifest.json` binds:

- schema version and experiment identity;
- attempt identity and lifecycle outcome;
- every relative path, media type, byte length and SHA-256 digest;
- exporter identity and version;
- source trial identity;
- test authority and test-plan digest;
- pre-run and post-run candidate-tree digests.

`terminal.json` records a single terminal lifecycle state and its reason. It is not a test
verdict.

### Prohibited content

The export must never contain:

- `auth.json` or other Runtime authentication material;
- Runtime user configuration or entire Agent home directories;
- environment dumps or shell history;
- Docker, Git, npm or pip credentials;
- telemetry state or machine identifiers;
- files outside the allowlist.

The secret scanner is a publication gate. On detection, publication fails and the private
staging output is retained only under the documented local cleanup policy. The exporter
must not silently redact a file and then claim the result is the original frozen evidence.

## Test authority and verdicts

The task-owned Test Runner is the sole behavioral verdict authority. It executes the frozen
test plan after the Agent terminal step and records:

- exact command and working directory in portable form;
- test-plan and test-source digests;
- process exit status and termination reason;
- structured results for the two fail-to-pass and two pass-to-pass tests;
- raw stdout and stderr;
- process and resource receipts;
- candidate-tree manifests before and after the attempt.

A pass requires a complete, internally consistent receipt, all required tests passing,
protected paths unchanged and all referenced digests verifying. Missing, malformed,
corrupt, mismatched or unverifiable evidence produces `inconclusive`, never pass.

The exporter freezes the receipt exactly once. The adapter does not rerun tests. Harness
rewards, Runtime terminal messages and prose in the trajectory are non-authoritative
diagnostics and cannot upgrade a fail or inconclusive result.

## Authentication and secret boundary

Live runs use the operator's Runtime subscription, not an API key. The operator supplies an
explicit Runtime auth-file path from outside the repository. The
workflow copies or mounts only the minimum authentication file into an ephemeral Runtime
home and removes the ephemeral state during cleanup.

Inlining auth JSON is forbidden because it would place secret JSON in an environment
variable and increase the chance that process or environment capture leaks it. The auth
file, its digest, account metadata and absolute source path are excluded from specs,
exports, logs and reports.

Live authenticated execution is a manual local step. CI operates only on synthetic
fixtures and already-frozen, secret-scanned exports. CI must not receive the operator's
Runtime subscription credentials.

## Network and telemetry boundary

The Runtime requires provider communication, so the first workflow permits provider-required
egress. It makes no claim that the Agent container is network-isolated. Web search is
disabled, and the task, dependency installation and tests do not require network access.

Network-capable commands such as `curl` or `wget` remain visible in the trajectory
and report as diagnostic events. They are not, by themselves, proof that isolation was
enforced. The compatibility spike must document the effective Harness and Runtime network
configuration accurately.

All available Harness and Runtime telemetry is disabled through documented configuration.
The spike must verify the effective setting and exported artifacts instead of treating a
configuration flag as proof. If a component cannot disable telemetry, publication is
blocked until the boundary and its implications are explicitly reconsidered.

## Attempt lifecycle and retry policy

Every attempt is immutable and ends in exactly one terminal state, including completed,
behavioral failure, timed out, interrupted or infrastructure failure. All attempts remain
addressable even when a retry occurs; a later attempt never overwrites the first.

Only these failures are retry-eligible:

- failure to start the container or Runtime before useful task execution; or
- an explicitly classified transient provider error before a terminal Agent result.

The policy allows at most one retry after a fixed 10-second delay with no jitter. The retry
references its predecessor and keeps the same ExperimentSpec identity while receiving a
distinct attempt identity.

The following are never retried automatically:

- behavioral failure;
- timeout or operator interruption;
- missing, corrupt or authority-mismatched evidence;
- evaluation inconclusive;
- secret-scan failure;
- exporter or manifest integrity failure.

An experiment report lists every attempt and selects a terminal attempt only according to
the frozen retry policy. It must not hide an earlier failure.

## Failure and fixture matrix

The acceptance suite combines real lifecycle outcomes with deterministic derived export
mutations. It must not pretend that all failures came from live Runtime execution.

Real executions cover:

- successful repair;
- genuine completed behavioral failure;
- timeout;
- interruption.

Derived fixtures cover:

- missing required artifact;
- content or manifest digest mismatch;
- Profile or Test Runner authority mismatch;
- planted fake-secret detection.

Every derived fixture records the source export digest, a versioned deterministic mutation
recipe and its own identity. Mutation occurs before fixture publication; the resulting
fixture is subsequently immutable. Fake credentials must be syntactically recognizable but
provably non-live.

Expected semantics are fail closed:

- valid complete passing evidence may pass;
- valid complete failing evidence fails;
- missing, corrupt, mismatched or unverifiable authority is inconclusive;
- secret detection rejects export publication and therefore cannot be evaluated as a
  normal completed export.

## Platform contract

The companion workflow initially supports macOS on Apple Silicon as Supported Preview only
after native acceptance passes with the pinned Docker image. Linux CI validates schemas,
fixtures, adapter behavior, strict reload and byte determinism offline. It is supporting
evidence for the Cernora package boundary, not a claim that live Linux Runtime execution is
supported.

Windows, Intel macOS, remote Docker, hosted runners and Kubernetes are unsupported in this
milestone. The candidate environment inside Docker is Linux and pinned by immutable image
digest.

## Portable run report

The companion emits a machine-readable JSON report and a Markdown rendering derived from
the same model. This is a versioned companion artifact, not a third Cernora Core import
contract and never an input to evaluation. The JSON form is authoritative; the Markdown
form must not add conclusions absent from JSON.

Each report contains:

- its report-schema version and ExperimentSpec identity;
- exact task, image, Harness, Runtime, model, Cernora wheel, Profile and Adapter identities;
- the complete ordered attempt list and retry links;
- lifecycle outcome separately from evaluation validity and behavioral decision;
- strict-reload result identity and referenced EvidenceBundle identity;
- Test Runner authority and receipt digests;
- export, candidate-tree and artifact-manifest digests;
- diagnostic duration, resource and token data when available and verifiable;
- explicit missing-data markers rather than invented zeroes;
- exact offline rebuild and evaluation command inputs.

The first report is per experiment and must not introduce Priority 4 statistics such as
pass-at-k, confidence intervals or cross-experiment rankings. Host absolute paths,
credentials, account identifiers and raw environment values are prohibited.

## Quality and publication gates

The private companion repository may be published only when all gates pass:

1. A clean temporary project installs exact `cernora==0.1.2` from the public Package Index;
   the wheel digest is recorded and import, evaluate and strict reload succeed with the
   Cernora source tree unavailable.
2. The Harness, Runtime, Python, Docker image and all Python dependencies are exactly pinned;
   the license inventory records every shipped dependency.
3. ExperimentSpec and Completed Export validators reject unknown fields, unsafe paths,
   missing files, unexpected files, invalid states and digest mismatches.
4. The adapter and Profile pass public-SDK conformance without importing Cernora internals.
5. Real and derived failure cases produce the expected fail-closed outcomes.
6. Re-evaluating the same frozen export three times produces byte-identical portable Cernora
   results and reports.
7. Secret scanning covers repository content, staged exports and publication artifacts with
   a deterministic planted-secret test.
8. Offline rebuild and evaluation instructions work after required packages and images have
   been acquired; frozen evaluation itself performs no network, Runtime or test execution.
9. The native macOS Apple Silicon tracer passes end to end with telemetry settings, auth
   cleanup and provider-egress behavior documented from observed evidence.
10. No generated attempts, credentials, local Agent state, source-checkout imports or host
    absolute paths are committed.

Until every gate passes, keep the repository and all artifacts local or private. Do not
push a public remote merely because the happy-path tracer works.

### Acceptance command surface

The companion repository exposes these commands as the documented handoff surface:

```sh
uv sync --frozen --all-groups
uv run python scripts/verify_public_wheel.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/verify_release.py
```

The public-wheel verifier performs the clean public-index install and source-isolation
check. `verify_release.py` composes schema, conformance, failure-fixture, three-run
determinism, secret and license checks; it does not perform a live authenticated Runtime run.
The live tracer remains a separate, explicit local command:

```sh
uv run python scripts/run_tracer.py --spec examples/tiny-calculator-v1.json
```

These commands are the accepted companion handoff surface. Their implementation and passing
release evidence completed the Priority 3 publication gate.

## Completed implementation order

1. Reproduce and record the public-wheel release baseline in a clean temporary project.
2. Create the independent Apache-2.0 companion repository with exact dependency pins and
   private-by-default ignores.
3. Implement strict models, JSON Schemas and negative tests for `experiment-spec/v1` and
   `completed-export/v1` before writing the Runtime adapter.
4. Run a minimal Harness/Runtime compatibility spike that verifies subscription auth, the
   pinned model, telemetry settings, provider egress, artifact locations and cleanup.
5. Build `tiny-calculator-v1` and its deterministic Test Runner authority.
6. Implement `cernora-reference-coding-v1` through the public Profile SDK.
7. Implement atomic export, manifest verification and secret scanning.
8. Implement the offline adapter, strict reload and three-run byte-identity gate.
9. Run and freeze the real successful tracer, then obtain the real behavioral failure,
   timeout and interruption attempts.
10. Generate the deterministic negative fixtures, portable report and compatibility record.
11. Run the full private publication gate and publish only after an explicit review.

Schema and export work precedes the adapter intentionally: Runtime-specific fields must be
contained at the export boundary rather than leaking into Cernora evaluation concepts.

## Explicit non-goals

Priority 3 does not include:

- a generic Runtime connector SDK or support for multiple Agent Runtimes;
- making the external Harness or Runtime a Cernora Core dependency;
- a public `MetricPlan`, judge-based scoring or model-as-judge authority;
- batch analytics, comparison dashboards or production gates from Priority 4;
- hosted execution, cloud queues, remote orchestration or a credential service;
- broad operating-system support;
- a claim that arbitrary untrusted tasks are safely isolated while provider egress remains
  open;
- Profile discovery, registry, marketplace or automatic promotion;
- use of API-key credentials in the baseline.

## Completion signal

From an independent clean checkout, an operator can use the pinned local workflow to run a
real external Runtime attempt, freeze a secret-free completed export, disconnect the Runtime,
adapt and evaluate that export through public Cernora APIs, strictly reload the result, and
reproduce byte-identical decisions three times. Failure cases remain fail closed, and the
report makes the exact task, image, Harness, Runtime, model, authority, attempt history and
evidence digests independently inspectable.
