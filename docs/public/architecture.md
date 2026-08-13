# Architecture

[README](../../README.md) | [Product roadmap](../../ROADMAP.md)

Cernora is a deterministic Python evaluator for already completed agent runs. It consumes
ordinary local files and produces evaluator-owned Evidence, Score and GateDecision records.
It does not own agent execution.

This document describes the architecture shipped in the `0.1.x` line. Planned metrics,
reporting, Runtime Connectors and Gate consumers belong in the product roadmap rather
than in this current-state contract.

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
  -> Evidence v1 and Score v1
  -> evaluator-composed GateDecision v1
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
deterministic assessment. Assessment returns bound Evidence, Score and the required
observation set. It does not persist results or compose GateDecision.

Profiles are selected explicitly as a built-in identifier or a local path. There is no scan,
entry-point discovery or registry. Local Profile Python is trusted code executed with the
current user's permissions; it is not sandboxed.

See [Profile authoring](profile-authoring.md).

### Deep evaluator

The evaluator reloads imported content, binds current authority, creates deterministic
evaluation identities, invokes the Profile, cross-checks returned Evidence and Score, and
composes GateDecision from the Profile's gate policy. It publishes a closed result package
and reloads it strictly before the result is accepted.

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
