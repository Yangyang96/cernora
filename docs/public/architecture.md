# Architecture

[README](../../README.md) | [Product roadmap](../../ROADMAP.md)

Cernora is a deterministic Python evaluator for already completed agent runs. It consumes
ordinary local files and produces evaluator-owned Evidence, Score and GateDecision records.
It does not own agent execution.

This document describes the architecture shipped in the `0.1.x` line, including the
opt-in Preview result report. Generic Metric SDKs, batch reporting, Runtime Connectors and
Gate consumers remain roadmap work rather than current contracts.

## Complete-system composition

Cernora is the independent decision core inside a composed evaluation system:

```text
Experiment Harness
  -> External Agent Runtime
       -> completed export + runtime-owned receipt
  -> Cernora
       -> Evidence + Score + GateDecision
  -> aggregate report
```

The external Agent Runtime owns Agent workflow execution, credentials, sandbox creation,
workspace, network and mount policy, resource limits, timeout, termination, evidence capture
and cleanup. Cernora does not implement or proxy those responsibilities.

The Experiment Harness owns task matrices, scheduling, repetitions, infrastructure retry
policy, aggregation and reporting. It must preserve each Cernora GateDecision exactly and
must not translate runtime success, reward or task completion directly into evaluation pass.

This separation keeps execution and adjudication independent. A complete end-to-end system
combines all three roles; installing Cernora alone intentionally provides only the evaluation
core and completed-export interfaces.

## Data flow

```text
producer-owned completed export
  -> explicit offline Adapter
  -> EvidenceBundle v2 plus declared artifacts
  -> canonical import and strict reload
  -> explicitly selected Profile
  -> Evidence v1 and Score v1, plus optional Preview ResultRecords
  -> evaluator-composed GateDecision v1
  -> optional EvaluationReport v1 that explains but cannot alter the GateDecision
  -> atomic persistence and strict result reload
```

The producer decides how an agent is run and exports the terminal facts. An Adapter only
normalizes that completed export. Cernora then owns validation, authority binding,
evaluation and publication of its result.

## Responsibilities

### Adapter

An Adapter reads one completed local export and writes one closed, canonical EvidenceBundle
v2 tree. It does not launch, resume or retry a process; obtain credentials; use the network;
or decide a score. The caller selects the Adapter explicitly.

See [Adapter conformance](adapter-conformance.md).

### Importer

The importer strictly decodes EvidenceBundle v2, verifies its digest and artifact bytes,
binds it to the supplied Profile and Case authority, and publishes a canonical import
package. Unknown fields, unsupported versions, unsafe paths, missing artifacts, digest
mismatches and inconsistent identities are rejected.

Import publication is conflict-safe. An exact repeat is byte-idempotent; a different result
is not allowed to overwrite an existing output. Strict reload rechecks the closed stored
package instead of trusting objects kept in memory.

### Profile

A Profile owns one `CaseProfile` authority, Profile-specific import validation and
deterministic assessment. Assessment returns bound Evidence, Score, the required
observation set and, when the Profile opts in, typed Preview ResultRecords. It does not
persist results, compose GateDecision or author the final report.

Profiles are selected explicitly as a built-in identifier or a local path. There is no scan,
entry-point discovery or registry. Local Profile Python is trusted code executed with the
current user's permissions; it is not sandboxed.

See [Profile authoring](profile-authoring.md).

### Deep evaluator

The evaluator reloads imported content, binds current authority, creates deterministic
evaluation identities, invokes the Profile, cross-checks returned Evidence, Score and
optional ResultRecords, and composes GateDecision from the Profile's gate policy. For an
opted-in Profile it derives EvaluationReport validity from required records, binds the
report to the existing decision and authority, publishes the closed result package and
reloads it strictly before the result is accepted. A report can explain a GateDecision but
cannot rewrite it.

Behavioral failure remains distinguishable from missing or invalid evidence. Infrastructure,
integrity or authority uncertainty cannot become a passing decision.

## Public contracts

Cernora `0.1.x` accepts only:

- `agent.evaluator.evidence-bundle/v2` as its bundle wire;
- import receipt and manifest v2 for canonical import packages; and
- the documented imported-evaluation package contracts.

The evaluator emits and retains these established output wires:

- `agent.evaluator.evidence/v1`;
- `agent.evaluator.score/v1`; and
- `agent.evaluator.gate-decision/v1`.

Profiles may additionally opt in to the Preview output wires:

- `agent.evaluator.result-record/v1`; and
- `agent.evaluator.evaluation-report/v1`.

The report is stored as `evaluation-report.json`, included in `digests.json`, recomputed on
strict reload and absent for Profiles that do not supply ResultRecords.

The `agent.evaluator.*` strings are protocol identifiers, not Python package names. Bundle
or import v1 is not accepted, converted or silently upgraded.

## Integrity and authority

Identities bind the producer, run, Profile, Case, fixtures and artifacts. Canonical JSON and
SHA-256 digests make content changes detectable. They do not prove producer identity,
non-repudiation, immutable history or resistance to a compromised producer.

Cernora validates only the receipt fields and declared artifact bytes present in an
EvidenceBundle v2. It does not generate or authenticate an external-runtime attestation, and
it cannot establish that a sandbox was created, that isolation policy was enforced or that
observations were captured outside Agent control. Those claims require a trusted external
runtime producer and its own conformance and security evidence.

The built-in `tool-workflow` Profile is intentionally synthetic. A passing outcome requires
the recorded milestone artifacts to equal exact Profile-owned observations protected by the
Profile fixture digest, and Evidence labels the scope as a Profile-owned synthetic
observation with `external_action_attested=false`. Copying those bytes into a producer export
does not prove that an external action occurred; the Profile validates the frozen evaluation
model, not a real runtime.

The built-in `coding-evaluation` Profile has the same explicit synthetic boundary. Its
authority fixtures freeze a baseline tree, test plan, harness, execution policy and an exact
oracle of accepted candidate/capsule artifact digests. Cernora derives the candidate tree
identity and diff, then reports build, FAIL_TO_PASS and PASS_TO_PASS observations from those
frozen capsules. It never executes candidate code and records
`external_action_attested=false`; real build/test attestation remains external-runtime work.

Cernora opens only declared ordinary files, rejects symbolic links in closed output trees,
and avoids in-place repair of persisted evidence. These controls protect deterministic local
evaluation; they do not turn Cernora into a runtime sandbox or evidence vault.

## Extension boundary

The Profile and Adapter protocols are the bounded Preview extension seams. Cernora does not
provide a plugin marketplace, registry, hosted scorer, workflow engine or universal runtime.
The [compatibility matrix](compatibility-matrix.md) states which seams are stable within
`0.1.x`. Future Metric SDK and Runtime Connector proposals are not current `0.1.x` extension
contracts; their sequencing and acceptance conditions are defined in the
[product roadmap](../../ROADMAP.md).
