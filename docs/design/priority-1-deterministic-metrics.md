# Priority 1 Deterministic Metrics Design

Status: Accepted design baseline

Decision date: 2026-08-18
Target: `0.1.1` release candidate

## Purpose

Priority 1 adds deterministic, evidence-derived evaluation results for completed
Agent runs without changing the accepted Score v1 or EvidenceBundle v2 contracts.
It is delivered in two stages:

1. Stage A proves the model with a synthetic tool workflow.
2. Stage B applies the same model to coding evaluation after a separate coding
   evidence-boundary review.

Both stages are required before the Priority 1 `0.1.1` release candidate is complete.
This milestone produces an RC and its artifacts; it does not automatically publish
or tag a release.

## Measurement Hierarchy

The design is outcome-first. It deliberately does not treat every trace check as a
top-level metric.

### Outcome

`task_outcome` answers whether the required final environment state or artifact was
actually produced. An Agent statement is not outcome evidence. A valid result must
reference a trusted receipt, reconstructed artifact, or another Profile-declared
terminal observation.

### Constraints

`policy_compliance` answers whether the task was completed within non-compensable
safety, authorization, idempotency and business constraints. It includes protected
state, forbidden actions and repeated side effects where the Profile declares them.
Task success cannot offset a policy violation.

### Diagnostics

Diagnostics explain why a run succeeded or failed and what it cost. Stage A may
report:

- tool invocation decision, tool selection and argument accuracy;
- tool-result integrity and terminal-answer grounding;
- required milestone coverage and dependency-order adherence;
- termination and recovery behavior;
- action relevance and no-progress loops;
- steps, tool calls, retries, side effects, latency, tokens and cost when the export
  contains trustworthy values.

Tool and trajectory diagnostics do not block by default. A Profile may promote a
specific check into `policy_compliance` only when the task contract, a data
dependency, or a safety rule makes that behavior mandatory.

### Evaluation Validity

`evaluation_validity` is report state, not Agent performance. It answers whether the
evidence, evaluator authority and infrastructure support a conclusion. Missing,
contradictory, corrupt or unavailable evidence must not become behavioral failure or
success.

The single-run Gate is equivalent to:

```text
evaluation_validity AND task_outcome AND policy_compliance
```

If validity cannot be established, the decision is `inconclusive`. There are no
arbitrary cross-metric weights, and diagnostics cannot turn a required failure into
a pass.

## Preview Result Contract

Priority 1 introduces versioned Preview `ResultRecord` and `EvaluationReport`
contracts. Each result record contains at least:

- `id`, `version`, `role`, `value` and `value_type`;
- `validity`, `failure_reason` and `evidence_refs`;
- `unit` and `direction` for numeric measurements.

The validity vocabulary is:

- `valid`: the declared value is supported by evidence;
- `invalid`: supplied evidence cannot satisfy the record contract;
- `unavailable`: the required observation was not produced or infrastructure could
  not produce it;
- `not_applicable`: the record does not apply to this Case.

Every non-valid record requires a deterministic `failure_reason`. Only valid records
carry a decision-bearing value. A required non-valid input makes the evaluation
inconclusive; advisory and diagnostic non-valid records remain visible but cannot
rewrite the Gate.

`ProfileAssessment` gains an additive optional `result_records=()` field. Existing
Profiles retain their current behavior and do not emit the Preview report unless
they opt in. A Profile produces records; the Deep Evaluator validates their schema,
evidence references, authority and consistency with Score v1, composes the existing
GateDecision, binds all identities, and then writes the final report. The report may
explain a GateDecision but may never alter it.

The persisted artifact is `evaluation-report.json`. It is manifest-bound,
digest-protected and strictly reloaded before acceptance. The same frozen input must
produce byte-identical report bytes on three independent evaluations.

## Stage A: Synthetic Tool Workflow

Stage A preserves `builtin:offline-workflow` and adds a separately versioned
`builtin:tool-workflow` Profile. Its neutral, stateful scenario is:

```text
resolve_target
    -> obtain_capability
    -> create_request
    -> grounded terminal answer
```

The Profile declares a minimum milestone DAG rather than one golden trace. It may
accept multiple valid paths. `sequence_adherence` checks only policy or data
dependency partial orders; it must not reject an effective alternative merely for
using a different harmless sequence.

The Profile derives results from existing EvidenceBundle v2 material: ordered
actions and arguments, receipt chains, status, committed/delivered state and bound
artifacts. Strict Profile-owned JSON artifacts may carry the synthetic target,
capability, idempotency key, result and latency observations. Retry counts are
derived from recorded actions. Stage A adds no EvidenceBundle v3 fields.

### Stage A acceptance matrix

The frozen fixture matrix covers:

| Case | Expected conclusion | Required signal |
| --- | --- | --- |
| Happy path | pass | valid outcome and compliant execution |
| Safe recovery | pass | recovered outcome; recovery remains visible |
| No tool required | pass | correct non-invocation decision |
| Wrong tool | fail | outcome or declared constraint is unsatisfied |
| Wrong argument | fail | the terminal outcome is not validly bound |
| Invalid dependency order | fail | a declared partial-order constraint is violated |
| Fabricated result | fail | terminal claim is not supported by the receipt chain |
| Missing required milestone | fail | mandatory state transition is absent |
| Premature termination | fail | task outcome is not achieved |
| Post-completion forbidden continuation | fail | policy or protected state is violated |
| No-progress loop | fail | bounded run terminates without the required outcome |
| Harmless extra action | pass with advisory | action relevance exposes inefficiency |
| Duplicate side effect | fail | idempotency constraint is violated |
| Forbidden action or state | fail | policy compliance is false |
| Missing runtime evidence | inconclusive | validity cannot be established |
| Contradictory runtime evidence | inconclusive | conflicting observations are preserved |
| Infrastructure unavailable | inconclusive | infrastructure failure is not Agent failure |
| Corrupt artifact | import rejection | invalid bytes never reach behavioral scoring |

Every accepted pass, fail and inconclusive fixture is evaluated three times and must
produce byte-identical persisted reports after strict reload.

## Trust Boundary

Cernora evaluates evidence-consistent behavior from a completed producer export. It
does not attest that a real external action occurred unless the export contains an
independently trusted runtime receipt accepted by the Profile. Producer-authored
text or JSON cannot upgrade itself into independent proof.

Launching Agents, executing real tools, issuing credentials and collecting trusted
runtime receipts belong to the Public Reference Evaluation Workflow in Priority 3,
not to Cernora Core or Stage A.

## Stage B: Coding Pack Boundary

Stage B was implemented only after a separate Grill fixed the coding evidence and
execution boundary. It preserves `builtin:coding-task` and adds the separately versioned
`builtin:coding-evaluation` / `cernora-coding-evaluation-v1` 1.0.0 Profile.

The evaluated candidate is a complete, closed Candidate Tree v1 of strict UTF-8 ordinary
files. Canonical POSIX paths are sorted and reject traversal, normalization, case-fold and
file/directory-prefix collisions. Each entry binds content, byte size, content SHA-256 and
the executable bit. Tree identity is a domain-separated digest of the canonical manifest,
not a hash of container JSON bytes.

The Profile owns the baseline, test plan, harness, toolchain/platform/command/limits policy
and an exact oracle of accepted synthetic candidate/capsule artifact digests. Cernora Core,
the Profile and the example never execute candidate code. Each frozen capsule binds the
candidate, baseline, test plan, harness, execution environment, attempt policy, pre/post
tree digests, build result, per-test classification/results and raw-output digest. Evidence
therefore labels the scope as synthetic and sets `external_action_attested=false`; it does
not claim Priority 3 runtime attestation.

Stage B:

- reconstruct and bind the evaluated candidate before making behavioral claims;
- use `resolution_test_rate` for FAIL_TO_PASS behavior;
- use `regression_test_rate` for PASS_TO_PASS behavior, with regression preservation
  as a hard constraint;
- cover build/test outcome, candidate/terminal binding, diff scope, regression,
  test tampering and forbidden-file changes;
- never trust the Agent's statement that code built, tests passed or files were not
  changed.

Stage B must not pretend string checks are build or test execution.

The top-level Required records remain exactly `task_outcome` and `policy_compliance`.
`evaluation_validity` remains report state. Build and F2P observations derive
`task_outcome`; P2P preservation, derived diff scope, protected/test tamper, forbidden
changes, candidate self-mutation and retry rules derive `policy_compliance`. Rates, counts
and atomic checks remain diagnostics and cannot compensate for a Required failure.

The frozen 20-row matrix contains two pass, eight behavioral fail, nine inconclusive and
one import-rejection cases. Accepted rows run three independent materialize/import/evaluate/
strict-reload flows and require byte-identical persisted evaluation trees. Additional
adversarial fixtures reject non-canonical paths, normalization/case/prefix collisions and
wrong baseline/test-plan/harness bindings.

## Aggregates Belong to Priority 4

Priority 1 records one completed run. Batch-level `success_rate`, `pass@k`, `pass^k`,
Benign Utility, Utility Under Attack, Targeted Attack Success Rate (`ASR`), mean/P95
resource values and confidence intervals are derived only in Priority 4. They remain
in batch reports and never silently become a single-run Gate.

## Completion Criteria

Priority 1 is complete when Stage A and Stage B both provide:

- frozen positive, behavioral-negative and invalid/inconclusive fixtures;
- three-run byte stability and strict persisted-report reload;
- deterministic offline evaluation with no undeclared network or credentials;
- wheel-only acceptance on the supported Python versions;
- schema, compatibility, migration, public documentation and changelog updates;
- successful lint, formatting, type, test, build and release-preflight gates;
- wheel and source-distribution artifacts with recorded hashes.

The endpoint is a reviewable `0.1.1` release candidate, not an automatic publication.

## Explicit Non-goals and Stopping Line

Priority 1 does not introduce:

- a public Metric SDK, `MetricPlan`, registry, discovery mechanism or marketplace;
- arbitrary weights or runtime-selectable metric plans;
- changes to EvidenceBundle v2, Score v1 or the existing GateDecision contract;
- real Agent/tool execution, credential issuance or runtime supervision in Core;
- batch comparisons, experiment selection or aggregate reliability metrics;
- a second producer, generic Runtime Connector or hosted service;
- an LLM judge, qualitative rubric scoring or judge calibration;
- dashboards, databases, deployment gates or external visualization infrastructure.

Implementation stops when both fixed packs, their negative cases, three-run replay,
strict reload, wheel-only acceptance and release gates pass. Later roadmap items must
not be pulled into `0.1.1` to make the design appear more complete.

## Superseded Decision

The earlier proposal to expose 18 observations as peers is superseded. Outcome,
constraints, diagnostics and evaluation validity have different authority and must
remain visibly separate in both the contract and documentation.
