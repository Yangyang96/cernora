# Cernora product roadmap

**English** | [简体中文](ROADMAP.zh-CN.md)

This document owns Cernora's product priorities after the `0.1` release. For usage,
start with the [README](README.md); for current component boundaries and invariants,
see [Architecture](docs/public/architecture.md).

Cernora will remain an offline, runtime-neutral evaluation core. Future work should
make real evaluations easier to compose, compare and consume without moving agent
execution, credentials, sandboxes or deployment authority into the core.
`1.0` changes the maturity of Cernora's contracts, not this ownership boundary.

## Adapter vocabulary

This roadmap uses two deliberately different terms:

- **Evidence Adapter:** a Cernora extension seam that reads one already completed
  native export and produces a closed EvidenceBundle v2. This interface is Preview
  in `0.1.x` and is part of the intended Stable `1.0` core.
- **Runtime Connector:** a runtime-specific companion
  used by an external Experiment Harness to run an Agent and freeze its completed
  export. It remains outside Cernora Core. A generic interface is introduced only if
  two concrete integrations prove the same narrow contract.

References to a Runtime Connector never mean that the `cernora` package becomes a
universal Agent runner or takes ownership of credentials, sandboxes or processes.

## Priority order

| Order | Milestone | Why it comes here |
| --- | --- | --- |
| 1 | Deterministic metric coverage | Add useful evidence-derived measurements without first freezing a new SDK. |
| 2 | Complete Profile authoring loop | Take third parties from private scaffold to a tested first GateDecision. |
| 3 | Public Reference Evaluation Workflow | Prove the released evaluator against a real external Agent run. |
| 4 | Batch experiments, reporting and improvement loop | Turn repeated runs into reliable comparisons and actionable diagnosis. |
| 5 | Metric SDK and `MetricPlan` Preview | Extract reusable built-in/custom metric composition from proven usage. |
| 6 | Second producer and Runtime Connector maturity | Generalize the connector only after two independent producers expose common needs. |
| 7 | Optional LLM-as-a-Judge Preview | Add qualitative judgment only where deterministic metrics leave a proven gap. |
| 8 | LLM-as-a-Judge stabilization | Graduate the interface only after calibration, drift and failure gates pass. |
| 9 | Staged Gate consumers and provenance | Let external systems consume decisions without transferring deployment authority. |
| `1.0` | Stable public platform boundary | Commit only to contracts proven across independent producers and Profiles. |

## `0.1.x` baseline

The roadmap starts from a released offline evaluation core that already provides:

- the completed-export to EvidenceBundle v2, canonical import, Evidence, Score and
  GateDecision path;
- strict validation, authority binding, fail-closed decisions, atomic persistence
  and strict reload;
- wheel-contained offline workflow and coding examples that run outside a source
  checkout;
- bounded Profile and Evidence Adapter SDK Preview interfaces;
- private-by-default Profile scaffolding, explicit trusted loading and static
  conformance validation under `.cernora/profiles/`.

`0.1.x` accepts EvidenceBundle v2/import v2 only and retains Evidence v1, Score v1
and GateDecision v1 as its current output protocols. The compatibility matrix remains
the authority for exact promises.

The released `0.1.1` additionally provides opt-in Preview ResultRecord v1
and EvaluationReport v1 outputs plus the explicit `tool-workflow` and `coding-evaluation`
reference Profiles. It does not change the published `0.1.0` default behavior.

Useful deterministic metric coverage is the first post-`0.1` capability. A public
Profile authoring loop follows so third parties can prove their own assessment end to
end. A public `MetricPlan` is deliberately later: authoring, real workflow and
experiment evidence should shape that abstraction before it is frozen.

## Priority 1 — Deterministic metric coverage

**Status:** implemented and released in `0.1.1` as opt-in Preview result
reporting. Priority 2 remains the next product milestone.

The accepted implementation baseline is specified in
[`docs/design/priority-1-deterministic-metrics.md`](docs/design/priority-1-deterministic-metrics.md).
That document is authoritative for both the `tool-workflow` and `coding-evaluation`
boundaries. The coding Profile was implemented only after a separate evidence review froze
candidate reconstruction, synthetic execution authority, test classification, tamper and
change-policy semantics.

### Goal

Expand beyond the initial Profile-owned boolean observations with useful,
evidence-derived measurements while preserving deterministic replay and the accepted
Score v1 contract.

This milestone improves what Cernora can measure. It does **not** require a generic
Metric SDK or public `MetricPlan`. Metric selection and Gate policy may remain
explicitly owned by each Profile until real workflows demonstrate a stable reusable
shape.

### Metric model

| Layer | Scope | Gate use |
| --- | --- | --- |
| Outcome or constraint | One completed run; boolean, evidence-bound and required by the Score policy. | Mirrors a required observation and participates in `GateDecision`. |
| Advisory | One completed run; important but non-blocking. | Reported prominently; does not block by default. |
| Diagnostic | One completed run; boolean, numeric or categorical with validity and, when numeric, unit and direction. | Analysis and comparison only. |

### Delivered coverage

- **Tool workflow:** tool selection, argument accuracy, sequence adherence, result
  grounding, recovery behavior, idempotency and forbidden actions.
- **Coding:** build/test result, candidate digest and terminal binding, diff scope,
  regression, test tampering and forbidden-file changes.
- **Reliability and security:** evidence validity and completeness, malformed input,
  timeout and infrastructure failure, repeated side effects and forbidden actions.
- **Efficiency:** Profile-owned tool-workflow evidence supplies latency, steps, tool calls,
  retries and side effects. Token usage, cost and cost-per-success remain deferred until a
  completed export provides trustworthy values.

Each result has an explicit identity, version, value type, unit and direction
where applicable, validity state, failure reason and references to supporting
Evidence. New diagnostic data will first appear in a separate versioned Preview
report rather than silently changing Score v1 within `0.1.x`.

Core evidence invariants are not metrics. Schema/version validation, bundle and
artifact digests, authority binding, contained paths, conflict-safe publication and
strict reload always run first and cannot be downgraded by a Profile.

### Metric admission rules

A metric must be actionable, evidence-derived, reproducible, explicitly versioned
and governed by a Profile or report contract. It must define behavior for missing,
invalid, contradictory and unavailable inputs. Metrics are not added merely to
increase the number of measurements.

### Delivered in `0.1.1`

This milestone proves metric semantics through Profile-owned implementations before
exposing a generic `Metric` interface:

1. **Result records:** emit a versioned record for each observation or measurement
   with at least `id`, `version`, `role`, `value`, `value_type`, `validity`,
   `failure_reason` and `evidence_refs`; numeric records also declare `unit` and
   `direction`.
2. **Tool-workflow pack:** first cover tool selection, arguments, sequence,
   grounding, recovery, idempotency and forbidden actions, with synthetic negative
   fixtures for reordered calls, wrong arguments, fabricated results and repeated
   side effects.
3. **Coding pack:** first cover build/test, candidate/terminal binding, diff scope,
   regression, test tampering and forbidden-file changes. Every behavioral claim is
   evaluated against the reconstructed candidate, not the Agent's assertion.
4. **Reliability and efficiency report:** report validity and infrastructure failure;
   report tool-workflow latency, steps, tool calls, retries and side effects separately.
   Missing or untrusted measurements are unavailable, never zero. Token and cost metrics
   remain deferred.
5. **Profile acceptance:** repeat the same frozen input three times with byte-stable
   deterministic results, covering true, behavioral false, missing evidence,
   contradictory evidence and unavailable infrastructure.

A required observation produces behavioral `pass` or `fail` only when its input is
valid. Missing, invalid or contradictory input remains `inconclusive`; a diagnostic
measurement can never offset a required failure into pass. This milestone also does
not introduce arbitrary cross-metric weighted totals.

### Completion evidence

The `tool-workflow` and `coding-evaluation` Profiles produce required Gate observations and
richer diagnostics from frozen Evidence packages. Their accepted matrices repeat each valid
input three times with byte-identical output, and invalid evidence cannot become pass.

## Priority 2 — Complete Profile authoring loop

### Goal

Turn the `0.1.x` Profile SDK Preview from a safe starting scaffold into a complete,
wheel-only authoring workflow. A third party should be able to create a private
Profile, implement one deterministic assessment, and prove all three outcome classes
without reading Cernora internals or copying a built-in Profile.

The `0.1.x` baseline already provides private-by-default `profile init`, explicit
`profile.py:create_profile()` loading, static conformance validation and
`--profile-path` selection for import/evaluate. The generated `assess()` deliberately
fails closed until implemented; static validation alone does not prove evaluation
behavior.

### Planned work

- provide a guided minimal template for authority, one Case, fixtures, one required
  observation and one completed-export shape;
- keep the generated default fail-closed while making the required implementation
  steps and authority-version changes explicit;
- add a documented Profile test workflow that runs valid pass, behavioral fail and
  invalid/inconclusive cases through real import, evaluation and strict reload;
- generate or package synthetic fixtures for missing evidence, corruption and
  authority mismatch without exposing private data;
- verify deterministic repeated results and absence of undeclared network,
  credentials and repository-root dependencies;
- improve diagnostics for invalid authority, missing observations, malformed
  Evidence references and mismatched scorer/gate policy;
- show how a Profile owns its deterministic observations before `MetricPlan` exists,
  and publish the later migration path to the shared Metric SDK;
- keep private placement under `.cernora/profiles/` and explicit public placement;
- do not add Profile discovery, publish/promote automation, a registry or a
  marketplace.

### Author workflow

```text
cernora profile init <name>
    -> .cernora/profiles/<name>/
    -> implement profile.py:create_profile()
    -> cernora profile validate --profile-path ...
    -> run synthetic pass / fail / inconclusive Cases
    -> Import + Evaluate + Strict Reload
    -> freeze the Profile authority version
```

The minimum directory contains `profile.py`, `profile.json`, `cases/`, `fixtures/`
and local tests. The template explains the authority role of every file, which
changes require a Profile version bump, and why a local Python Profile is explicitly
trusted code rather than a sandbox.

### Delivery slices

1. **Guided scaffold:** one implementable minimal assessment, annotated fixtures and
   a fail-closed default.
2. **Behavior test command:** run static conformance plus real import/evaluate/reload
   through one public command, without treating "loads successfully" as "evaluates
   correctly."
3. **Negative fixture pack:** missing evidence, malformed references, authority
   mismatch, scorer/gate-policy mismatch and nondeterministic results.
4. **Wheel-only tutorial:** install only the wheel in an empty project, create a
   private Profile and produce all three outcome classes without a source checkout.
5. **Migration note:** once `MetricPlan` Preview exists, show how to migrate each
   observation; authority and decisions must not be silently reinterpreted across
   the migration.

### Completion signal

Starting from an installed wheel in a clean project, a third party can run
`profile init`, implement one small domain check, validate it, exercise pass/fail/
inconclusive through a strictly reloaded result, and keep all Profile source and
fixtures private by default.

## Priority 3 — Public Reference Evaluation Workflow

### Goal

Prove that the released package evaluates evidence produced by a real external Agent
Runtime while keeping all runtime ownership outside Cernora.

### Companion project

The workflow will live in a separate companion repository with the working name
`cernora-reference-workflow`. It installs the released `cernora` distribution like a
third party and does not import a Cernora source checkout. Keeping it separate proves
the public package boundary and prevents runtime dependencies from entering the core.

### Reference architecture

```text
ExperimentSpec
    -> thin Experiment Harness
    -> concrete Runtime Connector
    -> external Agent Runtime
    -> frozen completed export
    -> offline Evidence Adapter
    -> EvidenceBundle v2
    -> Cernora Import + Evaluate + Strict Reload
    -> per-run decisions
    -> portable batch report
```

The first connector should reuse a pinned, established open-source container-agent
harness for tasks, datasets, Agent lifecycle, local sandboxing, trials, concurrency
and artifact collection. Cernora should not rebuild those facilities. The chosen
harness, version and license review belong in the companion repository; the Cernora
core and this contract remain runtime-vendor neutral.

### `ExperimentSpec`

Every experiment freezes:

- experiment identity and schema version;
- task-set identity, split and exact Case identifiers;
- Runtime Connector and external harness versions;
- Agent, model and generation parameters;
- system prompt, tool schema and workflow configuration digests;
- Cernora, Profile, scorer, metric/report and Adapter versions;
- repetition count, concurrency and timeout/resource limits;
- retry policy, output root and optional network policy.

Changing one of these values creates a different experiment identity rather than
silently amending an existing run.

### Thin Harness responsibilities

The companion Harness owns only:

- expanding the Case/configuration/repetition matrix;
- invoking the concrete Runtime Connector;
- tracking trial lifecycle and preserving every attempt;
- retrying eligible infrastructure failures according to the frozen policy;
- invoking the Evidence Adapter and released Cernora CLI/API;
- aggregating immutable per-run decisions without rewriting them;
- producing a machine-readable manifest and portable report.

The Runtime Connector invokes one concrete external Runtime, waits for a terminal
state and returns runtime-owned output. A Completed Exporter then freezes terminal
state, tool calls, logs, candidate artifacts, resource measurements, receipts and an
artifact manifest with content digests. The offline Evidence Adapter converts only
that frozen tree to EvidenceBundle v2.

### Authority and retry rules

- An external harness reward or verifier result may be retained as producer-side
  diagnostic evidence, but it is never a Cernora pass or GateDecision.
- Behavioral `fail` is a completed result and is not retried until it disappears.
- Infrastructure retry preserves the failed attempt and records why a new attempt
  was eligible.
- Missing, corrupt or contradictory export data becomes `inconclusive`; aggregation
  never drops invalid runs from the denominator.
- The baseline runs locally, disables optional upload/telemetry, and uses no hosted
  dashboard or registry.
- Secrets remain runtime-owned and are never copied into completed exports,
  EvidenceBundle, reports or Cernora configuration.

### Minimum public scope

- two or three neutral tool/coding tasks split into development, regression and
  hidden validation sets;
- one concrete Runtime Connector and one completed-export format;
- one explicit Evidence Adapter;
- at least three repetitions per Case;
- end-to-end examples of `pass`, behavioral `fail` and `inconclusive`;
- failure injection for timeout, interrupted execution, missing artifact, digest
  mismatch and authority mismatch;
- candidate, terminal and artifact binding where a task produces code;
- a portable result manifest and compact batch report.

### Delivery slices

1. **Vertical tracer:** one task, one external run, one frozen export and one strictly
   reloaded GateDecision.
2. **Failure matrix:** behavioral failure plus infrastructure, corruption and
   authority-mismatch cases.
3. **Repeatable dataset run:** public splits, at least three repetitions and frozen
   experiment identity.
4. **Portable report:** per-run decisions, validity/success separation, efficiency
   measurements and exact rebuild instructions.

The first integration is concrete on purpose. It should reveal the real seam between
runtime production and offline evaluation before any generic Runtime Connector
interface is proposed.

### Completion signal

A clean project can install Cernora from the public package index, use the companion
Harness to run a real external Agent, freeze its export and reproduce the same
evaluator-owned decision without access to the Cernora repository. Another user can
rerun the frozen `ExperimentSpec`, inspect every attempt and rebuild the published
report from machine-readable artifacts.

### Boundary

The companion Harness and Runtime Connector are not Cernora Core. Cernora does not
launch, authenticate, retry, sandbox, supervise or clean up Agents. This milestone
does not build a generic queue, cloud scheduler, multi-Runtime framework, hosted
service or dashboard.

## Priority 4 — Batch experiments, reporting and improvement loop

### Goal

Turn single-run decisions into reproducible comparisons across task sets, runtime
versions and workflow changes, then use those comparisons to guide improvements.

### Planned work

- define portable batch-input and result-summary formats;
- freeze runtime, model, prompt, tool schema, configuration, Profile, dataset and
  repetition count in every experiment identity;
- compute Evaluation Validity Rate, Behavioral Success Rate and Reliable Success
  Rate separately;
- keep aggregate metrics in the batch report; they never silently become a
  single-run Gate;
- add repeated-run stability, pass-at-k, confidence intervals and failure
  distributions where statistically appropriate;
- report latency, steps, tool calls, retries, token usage, total cost and
  cost-per-success beside quality and reliability;
- preserve every invalid or inconclusive run instead of dropping it from averages;
- publish machine-readable reports for CI and external visualization;
- establish a repeatable improvement loop:
  `frozen baseline -> failure taxonomy -> targeted intervention -> regression set -> hidden-set retest`;
- compare interventions without changing the evaluation policy mid-experiment.

The failure taxonomy will distinguish planning, tool selection, arguments, sequence,
grounding, recovery, behavioral mismatch, safety violation and infrastructure or
evaluation failure.

### Batch artifacts

Every batch experiment produces at least four portable artifacts:

- `experiment-spec`, freezing every independent variable, dataset split, repetition
  count and retry policy;
- `attempt-manifest`, preserving every attempt, terminal state, retry eligibility
  and linked per-run artifacts;
- `run-results`, retaining each strictly reloaded decision, validity state and
  measurement;
- `batch-summary`, derived only from those immutable results and carrying aggregates,
  intervals, failure distributions and rebuild metadata.

Two experiments are marked comparable only when their dataset/cases, Profile,
metric/report contract and Gate policy match, or when the comparison declaration
explicitly explains the differences. Changes to model, prompt, tool schema, Runtime,
resource limits or retry policy remain visible in the comparison manifest.
Behavioral failure is not retried; infrastructure retry preserves the original
attempt; every invalid run remains in the total and validity statistics. Selecting
only the best attempt as the result is prohibited.

### Delivery slices

1. **Repeat runner:** freeze a Case × configuration × repetition matrix and emit an
   immutable attempt manifest.
2. **Validity-first summary:** deliver validity, behavioral success and reliable
   success as separate top-level results before adding more complex statistics.
3. **Comparison report:** show baseline and candidate absolute values, deltas, sample
   counts, intervals, failure migration and cost/latency trade-offs.
4. **Improvement proof:** intervene on one leading failure class and retest with the
   same regression set plus an untouched hidden set, publishing non-improvements and
   new regressions as well as gains.

### Completion signal

Two frozen configurations can be compared through a documented repeatable process
that exposes quality, reliability, safety, efficiency, uncertainty and regression,
and an intervention can be validated against both regression and hidden cases.

## Priority 5 — Metric SDK and `MetricPlan` Preview

### Goal

After metric coverage, a real workflow and repeated experiments reveal actual reuse
needs, provide a narrow Preview interface through which Profiles can compose built-in
and domain-specific custom metrics.

### Target interface

A small `Metric` interface will own:

- stable `metric_id` and `metric_version` values;
- parameter and output-value contracts;
- deterministic evaluation from authority-bound Evidence where applicable;
- evidence references, validity state and failure reason on every result.

Each Profile will declare a versioned `MetricPlan` composed of explicit
`MetricBinding` values:

```python
MetricPlan(
    metrics=(
        MetricBinding(metric=tool_selection, role="required"),
        MetricBinding(metric=result_grounding, role="required"),
        MetricBinding(metric=answer_completeness, role="advisory"),
        MetricBinding(metric=latency_ms, role="diagnostic"),
        MetricBinding(metric=MyDomainMetric(...), role="advisory"),
    )
)
```

A binding may include versioned parameters, thresholds and report priority when the
metric's value contract supports them. The first version will not offer arbitrary
weighted totals: an average must not hide the failure of a critical observation.

The first roles remain narrow: `required` may affect `GateDecision`, `advisory` is
prominent but non-blocking, and `diagnostic` supports analysis and comparison.

The Profile and scorer authority bind the complete plan, including every metric
version, role, parameter and threshold. Changing any of them requires an authority
version change. A CLI caller cannot rewrite the plan for one run or disable a
required observation.

Cernora will expose a deliberately small built-in metric library and conformance
fixtures. Profile authors may import those modules or implement the same interface
for custom metrics. There will be no global registry, automatic discovery or metric
marketplace.

The API begins as Preview. The existing Profile-owned implementations remain valid
until migration evidence shows that the shared interface is ready to replace them.

### Authoring and conformance

Built-in and custom metrics use exactly the same contract. The conformance suite
will verify at least that:

- repeated execution over the same authority-bound Evidence produces the same
  result;
- values satisfy their declared type, unit, direction and validity contracts;
- every conclusion references Evidence present in the current evaluation;
- missing, invalid, contradictory and unsupported input retains a failure reason and
  cannot become pass;
- a custom metric cannot access undeclared network, credentials or repository-root
  resources;
- a required-metric error fails closed, while advisory/diagnostic errors remain
  visible and cannot rewrite other metric results.

The first authoring flow uses explicit Python imports: a Profile constructs its
`MetricPlan` directly, with no entry-point or user-directory scanning. Cernora ships
a small documented built-in catalog, one custom-metric tutorial and synthetic
conformance fixtures, but no global name-resolution promise.

### Delivery slices and migration

1. Identify genuinely repeated observation contracts in two existing Profiles.
2. Extract the minimum `Metric`, `MetricResult`, `MetricBinding` and `MetricPlan`
   Preview.
3. Migrate one Profile using only built-ins and another combining built-in and custom
   metrics.
4. Authority-bind plan identity, parameters, thresholds, roles and priorities, with
   negative tests.
5. Publish a migration note and compatibility window from Profile-owned observations
   to `MetricPlan`.
6. Consider maturity promotion only after both real Profile classes work without a
   private bypass.

### Completion signal

At least two substantially different Profiles compose built-in and custom metrics
through the same `MetricPlan`; authority changes are detected, conformance failures
fail closed and the abstraction removes duplication without weakening Profile-owned
Gate policy.

## Priority 6 — Second producer and Runtime Connector maturity

### Goal

Use a second independent completed-export producer to prove runtime neutrality and
discover which Evidence Adapter, Profile and Runtime Connector patterns deserve durable
public interfaces.

### Planned work

- integrate a second producer before extracting shared runtime-facing abstractions;
- decide whether a narrow public Runtime Connector interface is justified by common
  behavior demonstrated in both integrations;
- keep any Runtime Connector limited to producing a frozen completed export; it will
  not move credentials, scheduling, sandboxing or process ownership into Cernora;
- publish conformance fixtures for terminal state, tool calls, artifacts, candidate
  code and infrastructure failure;
- improve Adapter diagnostics and minimal reproducible failure packages;
- add Profile templates for tool workflows, coding tasks and domain-specific
  deterministic evaluation;
- document authoring compatibility and migration rules;
- support portable import and result formats for external analysis tools.

### Candidate Connector contract

If two implementations justify an abstraction, the generic contract describes one
attempt rather than an entire experiment:

```text
FrozenAttemptSpec
    -> Runtime Connector
    -> TerminalState + runtime-owned output location + infrastructure receipt
    -> Completed Exporter
    -> immutable completed-export directory
```

The Harness continues to own Case expansion, concurrency, retry and batch lifecycle.
The Runtime Connector submits one frozen attempt to one concrete Runtime and waits
for an explicit terminal state. The Completed Exporter turns runtime-specific output
into a closed directory; the Evidence Adapter then interprets that directory as a
Cernora EvidenceBundle. These three layers must not collapse into an object that
runs, selects evidence and declares pass.

The second producer acceptance matrix covers successful termination, behavioral
failure, timeout, interruption, partial artifacts, duplicate tool events and corrupt
exports. It must demonstrate equivalent Cernora validity and Gate semantics for
equivalent inputs from both producers. If the two connectors are only superficially
similar, extraction stops and both remain concrete companion integrations.

### Completion signal

At least two independent producers obtain the same evaluation semantics without
product-specific branches in the core and pass the same public conformance suite. A
generic Runtime Connector is added only if that evidence supports a genuinely narrow
interface.

## Priority 7 — Optional LLM-as-a-Judge Preview

`LLM-as-a-Judge` is an evaluation method. `Preview` is the maturity and
compatibility label for its first Cernora interface; it is not a different kind of
judge.

### Goal

Evaluate quality dimensions that deterministic programs cannot reliably decide,
without making model availability or an unverified model opinion the source of hard
facts.

### Planned work

- run the model outside the deterministic core through an explicit Judge Runner;
- bind an explicit Judge definition with identity, version, engine, workflow stage,
  visibility and input/output schema metadata through the Profile authority;
- use stage-specific Judge recipes for distinct jobs such as problem discovery and
  solution repair rather than one universal rubric;
- freeze a Judge Receipt that binds rubric, prompt, model, parameters, input,
  output, latency, tokens, cost and failure state;
- require a structured judgment and evidence references for every dimension;
- split checklist-style rubrics into separately reported dimensions, and treat an
  empty or inapplicable checklist as invalid/inconclusive rather than pass;
- allow only bounded structured-parsing retries and record every attempt in the
  frozen receipt;
- represent judge results through the metric/report model without weakening
  deterministic checks;
- map transport errors, refusal, timeout, invalid structure and missing provenance
  to `inconclusive`;
- build versioned human-label calibration and holdout sets;
- measure agreement, false pass, false fail, repeated-run stability and known
  adversarial biases;
- keep the Preview optional and advisory/shadow by default, with migration notes for
  breaking changes;
- select Judge definitions explicitly through a Profile; do not add automatic
  discovery, a global scorer registry or a hard-coded internal model client.

### Preview contract and delivery slices

The Judge Runner accepts a frozen `JudgeDefinition` and input digest, then returns an
immutable `JudgeReceipt`. Cernora only validates and consumes the receipt; it does
not own provider credentials or call the model again during offline replay. Every
receipt attempt retains a digest of raw structured output, parse result, error class
and cost measurements.

1. **Shadow tracer:** one public dimension that deterministic rules cannot reliably
   judge, one versioned rubric and one inspectable receipt; it does not enter a hard
   Gate.
2. **Failure matrix:** transport, timeout, refusal, invalid structure, empty
   checklist, missing provenance and contradictory evidence all produce explicit
   `inconclusive` results.
3. **Calibration pack:** human labels, annotation guidance, disagreement handling,
   a holdout split and public agreement/false-pass/false-fail calculations.
4. **Profile binding:** Judge definition, stage, visibility and receipt schema all
   enter authority; a CLI cannot swap rubric or model while claiming the same
   evaluation.
5. **Advisory report:** show Judge and deterministic metrics side by side, preserving
   conflicts instead of hiding them in one total.

### Completion signal

Users can reproduce and inspect a frozen Judge Receipt, quantify when its observation
is trustworthy and prove that Judge failure cannot create a passing hard Gate.

## Priority 8 — LLM-as-a-Judge stabilization

This milestone begins only if the Preview fills a real qualitative gap. Stabilizing
LLM-as-a-Judge means stabilizing its public contract, failure semantics and
calibration process; it does not make model output deterministic.

### Maturity path

```text
private experiment -> Preview -> Supported Preview -> Stable
```

- **Preview:** optional, advisory, allowed to evolve, with migration notes.
- **Supported Preview:** receipt and scorer interfaces supported within an explicit
  release line, but calibration scope remains limited.
- **Stable:** compatibility, receipt validation, failure semantics, migration and
  recalibration rules become maintained public contracts.

### Promotion gates

Promotion requires:

- at least one public qualitative use case not replaceable by deterministic checks;
- versioned human-label calibration and holdout sets;
- published targets for agreement, false pass, false fail and repeat stability;
- drift checks across rubric, prompt and model revisions;
- tests for prompt injection, irrelevant verbosity, position bias and self-preference
  where applicable;
- a frozen receipt schema with strict provenance and migration tests;
- fail-closed behavior for transport, refusal, timeout, invalid structure and missing
  provenance;
- documented recalibration triggers and rollback paths;
- evidence from at least two real Profiles or integrations before freezing a shared
  Stable interface.

Every rubric, prompt-template, model-family or sampling-policy change creates a new
calibration candidate. If holdout metrics miss their declared targets, drift cannot
be explained, or a failure class cannot be categorized reliably, the interface
remains Preview or rolls back. Maturity is never promoted by relaxing failure
semantics.

Stable deliverables include Judge Definition and Receipt schemas, validators, a
Calibration Report format, Drift Report, Migration Guide and Recalibration Runbook.
Stable promises these contracts and failure semantics; it does not promise that a
third-party model always emits identical text or scores.

### Hard-Gate rule

Even a Stable judge remains advisory by default. A calibrated judge observation may
block only through a separately versioned Gate policy with an explicit false-pass
tolerance, outage behavior, monitoring and external authorization. Deterministic
evidence checks continue to own hard facts.

### Completion signal

Independent users can produce and validate the same receipt version, know when
recalibration is required and upgrade without an undocumented contract break.

## Priority 9 — Staged Gate consumers and provenance

### Goal

Allow external CI and release systems to consume Cernora decisions safely while
keeping deployment authority external.

### Planned work

- provide a reference advisory/shadow consumer that records decisions without
  blocking;
- allow non-production blocking only after policy and thresholds are frozen and
  negative tests, evaluator-outage behavior, kill-switch proof and rollback proof
  pass;
- require an external authority record before any production enforcement;
- bind every consumed decision to the exact candidate or artifact digest;
- record Profile, metric plan, Score, Gate policy and GateDecision versions;
- preserve a kill switch in the consuming system;
- investigate optional signed producer attestations without overstating what content
  digests prove;
- keep human, security and deployment approvals independent of Cernora.

### Consumer contract and staged rollout

A reference consumer accepts only a strictly reloaded GateDecision and rechecks its
candidate/artifact digest, Profile authority, Score, Gate policy and decision
version. It cannot read an unverified producer reward or reuse the previous pass when
a decision is missing.

```text
observe only
    -> shadow comparison
    -> non-production block
    -> externally authorized production enforcement
```

Each promotion requires an independent policy record and exit criteria. Shadow
measures decision coverage, false signals and unavailability. Non-production
rehearses evaluator outage, timeout, kill switch, rollback and old-version
compatibility. Production keeps authorization, on-call and exception processes in
the external release system. Cernora only produces and validates decisions; it does
not provide a bypass code or deployment button.

The consumption record contains at least the decision digest, target artifact
digest, consumption time, consumer version, operating mode, resulting action,
exception reason and authority record used. An optional signature can prove that a
principal attested to bytes; it cannot turn incomplete Evidence into trustworthy
fact.

### Completion signal

An external system can consume a strictly bound GateDecision, fail safely when
evaluation is unavailable and disable the new Gate without bypassing existing
release controls.

## `1.0` product shape

### Place in the complete system

A complete Agent evaluation system may combine a dataset, Experiment Harness,
Runtime Connector, Agent Runtime, Completed Exporter, Evidence Adapter, Cernora and
an external Gate consumer. Its outer flow resembles other full evaluation systems,
but Cernora's differentiating boundary remains: a Harness cannot declare evaluator
pass, Runtime output must be frozen into an evidence contract, validity remains
separate from behavioral failure, and persisted decisions must survive strict
reload.

Cernora therefore remains an evaluation core/harness component in both `0.1` and
`1.0`, never the Experiment Harness itself. The complete experience is assembled in
public companion workflows; the core does not absorb a Runtime, dataset scheduler,
hosted traces or deployment authority merely to appear all-in-one.

`1.0` is a stable offline evaluation product, not an Experiment Harness or universal
Runtime. It contains:

- a Stable completed-export path from EvidenceBundle v2 through canonical import,
  Evidence, Score and GateDecision;
- Stable fail-closed validation, authority binding, persistence and strict reload;
- a Stable Evidence Adapter contract for converting completed native exports into
  EvidenceBundle v2;
- a Stable, wheel-only Profile authoring and conformance workflow from private
  scaffold through strictly reloaded pass/fail/inconclusive acceptance;
- Stable Profile-selected deterministic metric contracts, including the supported
  built-in/custom Metric and `MetricPlan` surface proven by real Profiles;
- portable per-run and batch result formats that preserve validity, behavioral
  success, reliability, safety and efficiency separately;
- at least one fully public real Reference Evaluation Workflow, including an
  external Harness and concrete Runtime Connector, plus conformance evidence from at
  least two independent completed-export producers;
- documented compatibility, migration, security and provenance boundaries;
- reference shadow and non-production Gate consumption without giving Cernora
  deployment authority.

Two surfaces are conditional rather than mandatory parts of the Stable core:

- a generic Runtime Connector is included only if two concrete external integrations
  prove a genuinely shared interface; otherwise the concrete integrations remain
  companion projects and `1.0` still does not claim a universal Runtime;
- LLM-as-a-Judge is Stable only if it passes its calibration, drift and failure
  gates; otherwise it remains an optional Preview outside the Stable core.

Production blocking always remains externally authorized, even when the consumed
Cernora contracts are Stable.

## `1.0` readiness criteria

Cernora should declare `1.0` only when:

- supported wire, CLI, Profile, Evidence Adapter and metric contracts are proven
  across multiple independent producers and Profiles;
- upgrade and migration behavior is documented and tested;
- deterministic replay passes across every supported Python version and platform;
- security, evidence and provenance claims match what the implementation proves;
- release automation, compatibility tests and vulnerability response are sustainable;
- extension interfaces remain small enough to evolve internals safely;
- at least one real Reference Evaluation Workflow is reproducible from public
  artifacts alone;
- a generic Runtime Connector, if shipped, is justified by two concrete integrations
  and remains outside Cernora Core;
- any LLM-as-a-Judge surface included in `1.0` has passed the stabilization gates;
  otherwise it remains Preview outside the Stable core;
- staged Gate consumers preserve shadow, non-production and externally authorized
  production semantics.

## Explicit non-goals

This roadmap does not include:

- a universal Agent Runtime or automatic Runtime discovery;
- a credential broker, sandbox service or workspace supervisor;
- a hosted evaluation SaaS, database or dashboard;
- a Profile marketplace, metric marketplace or benchmark registry;
- a generic model router or multi-provider execution platform;
- deployment approval or production authority;
- replacing deterministic evidence checks with an LLM Judge.

## How roadmap work is selected

A milestone begins only with:

1. a concrete user or integration need;
2. a narrow public contract;
3. machine-checkable positive and negative acceptance;
4. an explicit compatibility classification; and
5. a stopping rule that prevents speculative platform expansion.

Proposals should describe the completed export, required evaluation decision and
evidence boundary before introducing a new abstraction.
