# Priority 4 Batch Experiments and Improvement Loop Design

Status (2026-09-09): batch/comparison implementation and the actual 72-Trial study are locally
verified; evidence is preserved and offline-rebuildable. The candidate regressed. Public
evidence/package release remains separate; see [P4 closeout](../p4-closeout.md).

Historical design note: the 9-Case / 54-Trial requirements below retain the original plan.
They are not the actual run count and do not imply that its publication criteria are satisfied.
Positive improvement is now an explicit P4.5 milestone in the roadmap.

Decision dates: architecture and M1 baseline 2026-08-25; M1 exit and M2 entry baseline 2026-08-26

[Roadmap](../../ROADMAP.md) | [Architecture](../public/architecture.md) |
[Compatibility matrix](../public/compatibility-matrix.md)

## Purpose

Priority 4 turns Cernora's authority-bound single-run decisions into reproducible batch
summaries and controlled comparisons. It proves that two frozen configurations can be
compared without dropping invalid runs, changing evaluation policy mid-experiment or moving
Runtime ownership into Cernora Core.

The first release is a contract proof, not a general benchmark or leaderboard. Results are
claims about the frozen synthetic task set and Profile only. Small-sample uncertainty remains
visible and must not be generalized to all coding Agents or Runtimes.

## Ownership boundary

The open-source companion remains the primary user entry point. Responsibilities are split as
follows:

| Owner | Responsibilities |
| --- | --- |
| Companion | P3 ExperimentSpec, P4 RunPlan, matrix expansion, Runtime Connector, live execution, retries, budgets, checkpoints, completed exports and Attempt Manifest. |
| Cernora Core | Strict reload of Evaluation Packages, Runtime-neutral batch validation, deterministic aggregation and controlled comparison. |
| Companion | End-to-end CLI, execution provenance, authoritative JSON assembly, deterministic Markdown and Evidence Pack publication. |

Cernora Core does not start, authenticate, schedule, retry, sandbox, interrupt or clean up an
Agent. The companion does not award itself a Cernora pass. It invokes the released Core for
every evaluation and aggregation step.

The companion owns execution completeness relative to its declared RunPlan. Core can
prove that every declared Trial appears exactly once in the normalized batch input, but it
cannot detect a producer that omitted a Trial from the RunPlan before publication.

## User flows

The companion exposes three distinct flows:

```text
experiment run       live, authenticated execution plus frozen evaluation
experiment resume    append-only continuation of one incomplete execution
experiment rebuild   offline rebuild from frozen exports and packages
```

`run` and `resume` may contact the external Runtime. `rebuild` performs no Runtime, network or
test execution. A third party without Runtime credentials must be able to rebuild the released
Batch Summary and Comparison Report from the public Evidence Pack.

## Identity model

Priority 4 adds a batch plan around the immutable P3 single-run contract:

```text
RunPlan
  -> Execution instance
      -> planned Trial / Repetition
          -> one or more Attempts under the frozen retry policy
```

### RunPlan and Experiment identity

`RunPlan v1` is a companion-owned canonical JSON contract. It embeds a deduplicated set of
complete `ExperimentSpec v1` objects, lists exact Case and Configuration cells, and declares
the repetition and execution policies. It does not alter or reinterpret the P3
`ExperimentSpec v1` contract.

`run_plan_id` is the canonical content identity of the RunPlan. It freezes at least:

- Dataset identity, version, split and ordered Case identities;
- the complete embedded single-run ExperimentSpecs and their Runtime, model, Prompt, Tool
  Schema and generation configuration;
- Profile, Gate, report and evaluation authority;
- Trial count and pairing rule;
- Timeout, resource, provider-egress, web-search, retry and concurrency policies;
- statistical method and version; and
- companion and Cernora versions.

Budget changes, concurrency changes or another behavior-affecting value produce a new
RunPlan identity. A change to one embedded single-run configuration also produces a new
`experiment_id` under the existing P3 rules. Credentials, account metadata, timestamps,
random identifiers and host paths are excluded from `run_plan_id`.

### Execution identity

Before the first Runtime call, `execution_id` is derived from `run_plan_id` and a freshly
generated random nonce. It identifies one live execution instance and remains stable across
resume. The completed Execution Manifest binds that identity to the full Trial and Attempt
Manifests, completed-export digests, lifecycle receipts and Evaluation Package digests. Two
live executions of the same RunPlan have the same `run_plan_id` but distinct `execution_id`
values.

Reproducibility means the same frozen Execution rebuilds byte-identical evaluation and report
artifacts. It does not mean a stochastic Runtime must repeat the same Agent behavior in a new
live execution. A supported Runtime seed is identity-bound; unsupported seed control is
recorded explicitly as unavailable.

### Trial and Attempt

A Trial is the primary planned sample. An Attempt is one Runtime invocation within a Trial.
Infrastructure retry may append another Attempt, but never overwrites its predecessor.
Behavioral failure is a completed Trial outcome and is not retried.

`trial_slot_id` derives from RunPlan, Case, Configuration and Repetition and is stable across
Executions. `trial_id` also binds the Execution and is unique to one live Execution. Existing
P3 `attempt_id` semantics remain unchanged; the P4 Trial Manifest binds each evidence-derived
Attempt identity to its Trial and ordinal. Canonical report ordering follows the frozen slot
order, so actual completion order cannot change Manifest or report bytes.

## Completeness and resume

Execution storage is append-only and checkpointed atomically. Resume is allowed only when the
RunPlan, Execution identity, complete checkpoint sequence and every existing artifact digest
still verify.

- completed Trials are not re-executed;
- an atomically published result omitted from the latest checkpoint is adopted only after
  strict verification;
- an in-flight Attempt without a valid terminal record becomes interrupted or infrastructure
  evidence only when the coordinator can prove that state; an ambiguous live process blocks
  resume rather than being run twice;
- a retry is appended only when the frozen retry policy permits it;
- changing a budget, policy or input creates a new RunPlan;
- an incomplete or budget-exhausted Execution may emit diagnostics, but not an authoritative
  Batch Summary or Comparison.

Resume never selects results by quality. A completed Trial is not re-executed, a forced
interruption consumes the current Trial, and an unclassifiable slot leaves the Execution
incomplete. Checkpoints use monotonically increasing sequence numbers and are never
overwritten.

The normalized Batch Input is invalid when a planned Trial is absent, duplicated or unknown;
an Attempt chain is broken; a referenced package is missing; or any digest is inconsistent.
Core stops aggregation in those cases.

A declared lifecycle failure with a valid receipt is different from structural corruption.
It produces an unavailable Trial that remains in the denominator. It does not invalidate the
whole Batch Input.

## Milestone 1 approved baseline

Milestone 1 is a Companion-only Repeat Runner release. It proves frozen repeated execution,
safe continuation and offline reconstruction before Core receives a batch API.

### Frozen plan and matrix

`RunPlan v1` is a standalone, strict and canonical JSON object. It embeds each distinct
`ExperimentSpec v1` once and contains ordered `cases`, ordered `configurations` and an exact
list of cells that bind a Case and Configuration to one embedded ExperimentSpec. Baseline and
Candidate have no special semantics in Milestone 1; they are ordinary Configuration IDs.

Before execution, the Runner expands the cells and repetition count into a complete ordered
Trial-slot list. Every slot binds `experiment_id`, Case ID, Configuration ID, repetition
ordinal and deterministic `trial_slot_id`. Execution may append results only to those slots.
It cannot discover, add, remove or replace Trials after `run_plan_id` is frozen.

### Execution initialization and storage

`run` completes preflight and atomically creates the Execution before contacting the Runtime.
The initial records freeze the RunPlan, `execution_id`, complete Trial-slot list, Connector and
Companion identities, platform qualification and execution policies. Once the first Attempt
starts, none of those inputs may change.

Execution storage is append-only:

- every Attempt owns a distinct immutable directory;
- a Trial terminal record is published atomically;
- checkpoints are immutable, monotonically numbered snapshots;
- private temporary work is not authoritative evidence; and
- a completed retry never replaces or deletes its failed predecessor.

The completed Execution Manifest is published only when every planned slot appears exactly
once, every Attempt chain is valid and every referenced digest verifies. Incomplete
Executions may publish diagnostics and checkpoints but not a formal batch result.

### Resume and interruption

`resume` strictly reloads the RunPlan, Execution record, checkpoint sequence and all existing
artifacts before doing live work. It never reruns a completed Trial or chooses an Attempt by
behavioral outcome. A fully published but not yet checkpointed result may be adopted after
verification. A missing terminal becomes lifecycle evidence only when the Runner can prove
the process outcome. If the prior process may still be active or its state cannot be proved,
resume fails closed rather than risking duplicate execution.

Only the frozen P3 retry policy can authorize another Attempt. A graceful stop takes effect
between Trials. A forced interruption of an active Agent is retained as that Trial's outcome;
it is not converted back into an unstarted slot.

### Scheduling and budgets

Reference execution is deterministic and sequential with `concurrency = 1`. The Runner
continues after behavioral failure, timeout or a verified unavailable lifecycle outcome. It
stops only for an integrity violation, ambiguous active process, operator request or hard
budget.

Every RunPlan declares its exact planned-Trial count, maximum-Attempt count, maximum total
wall time, concurrency and the per-ExperimentSpec timeout, CPU and memory limits. Token or
monetary limits may be enforced only when a structured source and frozen pricing authority
make them verifiable; otherwise their control status is explicitly `unavailable`, never zero
or an invented estimate. Maximum Attempts and wall time remain mandatory hard spending
backstops. Budget exhaustion makes the Execution incomplete and never reduces the planned
sample count.

### Milestone 1 artifacts and CLI

Milestone 1 adds Companion-owned `RunPlan v1`, `Execution Manifest v1`, `Trial Manifest v1`,
append-only checkpoints, a portable Execution Pack and deterministic diagnostic Markdown. It
does not calculate aggregate success rates, confidence intervals, a Winner or a Controlled
Comparison; those contracts begin in Milestones 2 and 3.

The approved CLI shape is:

```text
experiment verify PLAN
experiment run PLAN --output DIR --accept-plan-id ID
experiment resume EXECUTION_DIR
experiment rebuild EXECUTION_PACK --output DIR
```

Preflight displays the complete matrix, planned Trial count, worst-case Attempt count and
budget. `--accept-plan-id` prevents live execution of a changed plan. `rebuild` writes to a
new directory and performs no Runtime, network, Docker, Git or test execution. Behavioral
failure remains a valid execution result; structural corruption, exhausted budget or an
incomplete Execution returns nonzero.

### Milestone 1 acceptance

Offline conformance covers at least two Cases by two Configurations by three repetitions,
producing twelve planned Trials. Fixtures cover success, behavioral failure, timeout,
retry-eligible and non-retryable lifecycle failures, missing or duplicate Trials, digest
tampering, resume and budget exhaustion.

The approved exit gate deliberately strengthens the original minimum live acceptance. It uses
the single already-qualified Connector and runs two Cases by two Configurations by three
repetitions sequentially, producing twelve planned Trials with `concurrency = 1`. The two
Configurations are `normal-policy` and an identity-bound `short-timeout-policy`; each Case and
Configuration cell binds its own `experiment_id`.

The live result need not be behaviorally positive. The completed Execution must contain at least
one strictly rebuildable Evaluation and at least one genuine unavailable lifecycle result. After
at least one completed Trial, the operator requests a graceful stop and resumes the same
Execution to completion. A third party without Runtime credentials must strictly reload the
Execution Pack and rebuild byte-identical authoritative Manifests and diagnostics. Natural retry
evidence is retained when it occurs but is not manufactured as an acceptance condition. The
expected release is companion `0.2.0`; Milestone 1 makes no Cernora Core release.

### Milestone 1 exit and Milestone 2 entry gate

Milestone 2 design and test planning may proceed before native acceptance, but its public
contracts must not be frozen or implemented until all of the following are true:

- the strengthened twelve-Trial native acceptance completes under an explicitly accepted
  RunPlan, Attempt budget and wall-time budget;
- the accepted Execution, Execution Pack, offline rebuild and their SHA-256 digests are retained;
- repository, Attempt, report, Pack and built artifacts contain no credentials, personal paths,
  Runtime homes or undeclared files;
- companion `0.2.0` is frozen at a reviewable commit, tag and artifact digest; and
- commit, push, tag, package publication and Evidence Pack publication remain separately
  authorized operations.

A corrupt, ambiguous, incomplete or budget-exhausted Execution cannot satisfy the gate. Changing
an input or budget creates a new RunPlan and Execution rather than continuing the rejected one.

## Milestone 2 approved baseline

Milestone 2 adds a Runtime-neutral, validity-first Batch Summary Preview. Cernora Core does not
parse a companion Execution Pack and does not depend on the companion package. The companion
strictly verifies a completed Pack, normalizes its immutable facts into `BatchInput v1`, and calls
only the released `cernora==0.1.3` wheel. Core never starts or supervises a Runtime and never reads
Runtime credentials.

`BatchInput v1` is strict, canonical and content-identified. Every planned Trial binds RunPlan,
Execution, slot, Case, Configuration, repetition and the complete Attempt chain. An evaluated
Trial includes a strict-reloaded Evaluation Package and its evaluator-owned identities and
digests. A Trial without an evaluable export includes a normalized lifecycle record instead.
Caller-provided rates, naked pass/fail JSON, unknown fields, missing or duplicate Trials, broken
Attempt chains, digest mismatch and incomplete or budget-exhausted Executions are rejected.

Core owns exactly four Trial outcome classes: `pass`, `behavioral_fail`,
`evaluation_invalid` and `infrastructure_unavailable`. Planned Trials remain the sample unit and
denominator authority. The summary reports raw counts and rates overall and by Configuration,
Case and Case-by-Configuration cell. When there are no valid Trials, Behavioral Success Rate is
unavailable rather than zero. Every Attempt contributes to first-attempt, retry, validity,
infrastructure and verifiable resource diagnostics. Unverifiable token or cost values remain
unavailable.

Milestone 2 publishes no Configuration delta, confidence interval, bootstrap result, pass-at-k,
Winner, improvement or regression conclusion. Profile-owned failure codes are verified and
retained but never inferred from trajectory or free-form text. Canonical JSON is authoritative;
deterministic Markdown may express only the same facts. Publication is atomic into a new closed
directory and must pass strict reload.

The intended public surfaces are package-root Preview Batch models and validate, summarize and
reload functions; `cernora batch validate`; `cernora batch summarize`; and companion
`experiment summarize EXECUTION_PACK --output DIR`. Exit `0` means a valid summary even when
behavior is poor, exit `2` means usage, selection or authority incompatibility, and exit `3`
means corrupt, incomplete or unverifiable input. Expected releases are Cernora `0.1.3` and
companion `0.2.1`.

Acceptance covers at least the frozen two-by-two-by-three matrix, all four Trial outcomes,
evaluated and unavailable records, retry chains, zero-valid-Trial groups, missing, duplicate and
unknown Trials, broken predecessors, authority mismatch, digest tampering, unknown fields and
illegal outcomes. Three summaries from identical input must produce byte-identical canonical JSON,
Markdown, identities and file digests. Core and companion wheel-only checks run without the other
source checkout. M2 is complete only after full tests, builds, secret scans, independent review
and strict rebuild of the accepted real M1 Pack all pass.

## Authoritative batch input

Core aggregation consumes only strict-reloaded Evaluation Packages plus normalized lifecycle
records for Trials that produced no evaluable export. It does not accept caller-supplied
percentages or naked success/fail JSON.

Each evaluated Trial binds at least:

- evaluation and decision identities;
- evaluation-input and authority digests;
- Evaluation Package manifest and receipt digests;
- Trial and Attempt identities; and
- the frozen RunPlan, Experiment and Execution identities.

Existing Profiles without structured EvaluationReport output remain eligible for basic
pass/fail/inconclusive aggregation. Failure migration and advanced diagnostics are available
only when a Profile supplies versioned, evidence-bound ResultRecords. Missing diagnostics are
reported as unavailable and are never inferred from free-form Blocking Reasons.

## Validity-first aggregation

Top-level quality rates use planned Trials as their sample unit:

| Result | Numerator | Denominator |
| --- | --- | --- |
| Evaluation Validity Rate | Trials with an eligible pass or behavioral fail | all planned Trials |
| Behavioral Success Rate | passing Trials | valid Trials |
| Reliable Success Rate | passing Trials | all planned Trials |

A successful policy-eligible retry may make its Trial pass. The failed predecessor remains in
the Attempt Manifest and mandatory Attempt diagnostics.

Attempt-level reporting includes at least:

- first-attempt success rate;
- retry rate and retry count;
- Attempt evaluation-validity rate;
- infrastructure-failure distribution; and
- total resource and cost contribution from every Attempt.

This preserves both truths for a Trial that fails once and passes on retry: its final Trial
outcome passed, while first-attempt reliability and Attempt validity did not.

## Failure taxonomy

Failure classification has two authority layers.

Core owns one closed outcome class per Trial:

- `pass`;
- `behavioral_fail`;
- `evaluation_invalid`; or
- `infrastructure_unavailable`.

Profiles own specific, versioned failure codes such as tool selection, argument accuracy,
sequence, grounding, recovery, protected-path violation or regression. Codes must be derived
from Evidence and ResultRecords. One Trial may carry multiple Profile-owned codes. Unknown
causes remain `unclassified`; Core never guesses a category from trajectory prose.

Failure migration is comparable only under the same Profile and authority version.

## Controlled comparison

Priority 4 produces two comparison classes.

### Controlled Comparison

A Controlled Comparison may support improvement or regression conclusions. Baseline and
Candidate must match on:

- Dataset, split, Cases and Trial pairing;
- Profile, Gate, metric/report contract and evaluation authority;
- Trial count, timeout, resource and retry policy; and
- statistical method and confidence level.

Every permitted difference is declared in a content-identified Treatment. A Treatment may
contain several coordinated changes, but no implicit difference is allowed. Unknown or
undeclared differences fail closed.

### Descriptive side-by-side

When a comparison invariant differs, the report may show both frozen results but marks them
`not_comparable`. It cannot emit an improvement percentage, regression claim or promotion
recommendation.

Priority 4 does not create a weighted composite score or automatic Winner. A Controlled
Comparison predeclares one Primary Outcome and explicit Guardrails. Safety, evaluation
validity and regression Guardrails cannot be averaged away. Other quality, cost and latency
results remain side by side.

Possible conclusions include `improved`, `no_change`, `uncertain`, `mixed`, `regressed` and
`not_comparable`. `improved` requires the Primary Outcome to satisfy its declared practical
threshold without violating a hard Guardrail.

## Statistical method

Trial is the execution sample, while Case is the independent unit for cross-task uncertainty.
Repeated Trials for one Case measure Runtime stability; they do not manufacture independent
Cases.

The first Comparison Preview uses a deterministic, Case-clustered paired bootstrap:

- resample paired Cases as whole clusters, retaining every Trial for each Case;
- compute a 95% interval for Candidate-minus-Baseline deltas;
- derive the bootstrap seed from Comparison identity;
- version the estimator and resampling count in the report contract;
- publish raw per-Case deltas beside the interval; and
- emit no p-value or automatic statistical-significance claim.

The nine-Case Reference Acceptance is labeled `contract_proof`. Its intervals may be wide. An
interval crossing zero yields `uncertain`, not proof of no difference.

`pass@k` and `pass^k` are optional Milestone 3 statistics. They are available only when every
Case has the same predeclared number of independent Trials under one Configuration. Retry
Attempts do not count toward k, and Trials cannot be added after viewing results. Otherwise
the statistic is not applicable or has insufficient Trials.

## Efficiency and cost

Efficiency data is diagnostic and never silently changes a GateDecision.

- latency declares exact clock boundaries;
- token usage requires a structured, digest-bound Runtime or provider receipt;
- cost derives from token usage and a frozen, versioned Pricing Snapshot;
- unverifiable values are unavailable, never zero;
- every retry contributes its full time, token and cost values;
- cost per success divides verified total cost by Reliable Successes and is unavailable when
  there is no success; and
- Comparison shows quality, reliability, cost and latency trade-offs without folding them
  into one score.

Priority 4 enforces execution safety budgets but does not turn quality or cost evidence into a
promotion decision. A later external Promotion Policy may define product-release thresholds.

## Improvement Loop Proof

Milestone 4 validates an honest intervention process rather than requiring a positive result:

```text
frozen baseline
  -> predeclared leading failure code and hypothesis
  -> content-identified Treatment and frozen Candidate
  -> regression-set comparison
  -> one held-out evaluation
  -> complete publication of gains, non-gains and regressions
```

The open-source Reference Task Set contains nine substantively distinct synthetic coding
Cases:

- three development Cases;
- three regression Cases; and
- three held-out Cases.

Baseline and Candidate each run three planned Trials per Case, producing 54 planned Trials.
With at most one infrastructure retry, the safety budget permits no more than 108 Attempts.
Development may use smaller fixture subsets; the 54-Trial run is the final Milestone 4
acceptance.

The held-out Manifest identity and split metadata are published before intervention without
revealing Case content. After Candidate identity is frozen, the held-out set is executed once.
Its Cases and complete results are revealed with the Evidence Pack. Revealed Cases join the
regression set and cannot serve as the next intervention's hidden set.

Viewing held-out results and then modifying Candidate creates a new intervention that requires
a new held-out set. `no_change`, `mixed` or `regressed` still completes the process proof when
reported honestly. A positive product claim or promotion requires a separate predeclared
policy and positive held-out evidence.

## Open-source companion and Evidence Pack

The companion is the public first entry point and remains an independent Apache-2.0 project.
It publishes its Harness code, schemas, Connector, Adapter, Profile, synthetic tasks,
deterministic fixture recipes, tests, exact dependency pins and license inventory.

Credentials, account metadata, host paths, private datasets, local Agent state and unreviewed
raw traces are never published.

Source, schemas, revealed Cases and compact CI fixtures live in Git. Full completed exports,
Evaluation Packages, Attempt Manifests and reports ship as immutable release assets. An
Evidence Pack Manifest binds the Git tag, companion version, Cernora version and every
artifact digest. A changed byte creates a new identity and release asset; existing packs are
never overwritten.

Publication gates cover secret scanning, absolute paths, account metadata, licenses,
dependency inventory, package conformance and complete offline rebuild. Content SHA-256 proves
byte integrity and does not claim producer authentication or non-repudiation.

## Budget, concurrency and platform

RunPlan requires planned-Trial, maximum-Attempt, retry, timeout, wall-time and concurrency
budgets. It includes token and estimated-cost limits when they are verifiable.
Runner preflight displays the complete matrix and worst-case Attempt count. Exceeding a hard
budget stops execution as incomplete; it never silently reduces sample size.

Reference Acceptance runs sequentially with `concurrency = 1`. The contract permits explicit
concurrency, but it is identity-bound and must match for Controlled Comparison. Provider rate
limits and resource contention remain observable infrastructure outcomes.

Priority 4 does not expand live platform support. The companion performs live acceptance only
on platforms already qualified by Priority 3. Other platforms are experimental and marked
unqualified. Core's offline aggregation follows the Cernora compatibility matrix. Linux CI may
validate frozen artifacts without claiming live Runtime support.

The reference workflow continues to use one proven Connector. Priority 4 may compare model,
Prompt, Tool Schema, generation configuration or Runtime version Treatments through that
Connector. A second producer and generic Connector SDK remain Priority 6 work.

## Report and CLI semantics

Canonical JSON is the authoritative Batch and Comparison representation. Deterministic
Markdown is rendered from the same model and cannot add conclusions absent from JSON.
External tools may visualize JSON; Core provides no Dashboard, database, Web server or hosted
report service.

Batch and Comparison commands use exit status for report validity, not Candidate quality:

- `0`: valid report produced and strictly reloaded, including mixed or regressed results;
- `2`: usage, selection or comparison-authority incompatibility; and
- `3`: corrupt, incomplete or unverifiable Batch input.

Aggregate regression does not use exit `1` and does not become a deployment Gate. Promotion
and release blocking remain external Gate Consumer work in Priority 9.

## Milestones and release sequence

### Milestone 1 — Companion Repeat Runner

The companion implementation is complete and provides Run, Resume and Rebuild; identity-bound
RunPlan, Execution and Trial formats; append-only Attempts and checkpoints; budgets; strict
completeness; and the frozen matrix. The approved contract and acceptance details are defined in
[Milestone 1 approved baseline](#milestone-1-approved-baseline). This work precedes new Core
contracts so real lifecycle evidence shapes their minimum fields. The strengthened native exit
gate remains pending and blocks Milestone 2 contract implementation.

Expected release, absent intervening versions: companion `0.2.0`; no Cernora release.

### Milestone 2 — Core Validity-first Batch Summary Preview

The decision baseline is approved; implementation begins only after the Milestone 1 exit gate.
Core adds strict Batch Input validation, Evaluation Package reload, Trial and Attempt
aggregation, authoritative persistence and strict reload. The companion consumes only the
released package rather than a source checkout.

Expected releases, absent intervening versions: Cernora `0.1.3`, companion `0.2.1`.

### Milestone 3 — Core Controlled Comparison Preview

Core adds comparison invariants, Treatments, Primary Outcome and Guardrails, deterministic
paired bootstrap, optional qualified pass-at-k statistics and failure migration. The
companion adds authoritative Comparison JSON and deterministic Markdown.

Expected releases, absent intervening versions: Cernora `0.1.4`, companion `0.3.0`.

### Milestone 4 — Improvement Loop Proof and Evidence Release

The companion executes the 54-Trial controlled experiment, completes held-out commit-reveal,
publishes all outcomes and releases the immutable Evidence Pack. It does not force a Core
release when no Core API changes.

Version numbers remain independent. Every milestone is separately releasable and consumes a
previously published Cernora artifact. Batch and Comparison Core contracts remain Preview.

## Completion signal

Priority 4 is complete when:

1. the companion can safely Run, Resume and offline Rebuild a frozen batch without deleting
   or selecting Attempts;
2. Core rejects incomplete Batch inputs and derives byte-identical validity-first summaries
   from strict-reloaded Evaluation Packages;
3. two frozen configurations produce a Controlled Comparison with raw Case deltas, honest
   uncertainty, Failure Migration and efficiency trade-offs;
4. the nine-Case, 54-Trial Improvement Loop Proof completes against regression and held-out
   splits regardless of whether the Treatment improves, changes nothing or regresses; and
5. a third party can download the open-source companion and Evidence Pack and rebuild the
   authoritative JSON and Markdown without Runtime credentials.

## Explicit non-goals

Priority 4 does not include:

- a general benchmark, leaderboard, Dataset registry, data-labeling program or contamination
  platform;
- a second Runtime, generic Connector SDK or broader live platform support;
- Metric SDK or `MetricPlan` extraction from Priority 5;
- LLM-as-a-Judge work from Priorities 7 and 8;
- weighted composite scores or automatic Winners;
- a built-in Dashboard, database, hosted service or report registry;
- Promotion Policy, deployment authority or Gate Consumers from Priority 9;
- mandatory positive intervention results; or
- Runtime execution, credentials, scheduling or sandbox ownership in Cernora Core.
