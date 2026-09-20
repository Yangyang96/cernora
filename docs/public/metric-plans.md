# Metric composition Preview

A Profile can opt into `Metric`, `MetricBinding` and `MetricPlan` to share deterministic
calculations. They evaluate already imported evidence, reuse ResultRecord v1 and
ScoreObservation v1, and never run an Agent or discover plugins. Existing built-in Profiles
retain their identities and calculations.

## Compose and bind

```python
from cernora import MetricBinding, MetricPlan, ToolCalls, ToolSelection

plan = MetricPlan(metrics=(
    MetricBinding(
        metric=ToolSelection(),
        role="required",
        parameters_json='{"allowed_tools":["lookup","help"],"allow_empty":false}',
    ),
    MetricBinding(metric=ToolCalls(), role="required", maximum=8),
))
```

A binding explicitly selects an implementation and canonical JSON parameters. Duplicate or
unknown parameters, unknown Plan versions, duplicate output IDs, and invalid roles are
rejected. Each Metric has a declared ID, implementation version, value type, unit and
direction. JSON parameters are immutable strings and are canonicalized on construction;
there is no shared mutable parameter dictionary between Metrics.

`plan.canonical_bytes` describes every binding, version, parameter, role and maximum, in
execution/report order. Store it with the Profile's resources. Declare a fixture reference
with `sha256=plan.sha256`, set the Profile's scorer `policy_version=plan.scorer_version`,
and set `required_observations=plan.required_observations`. The scorer version embeds the
full Plan digest; it is not just a human-readable version label.

The Profile must call `plan.validate_authority(authority)` when loading its authority
(including its `authority` property used during strict reload), and validate that imported
Profile/Case identities match. Then, inside `assess(package, context)`:

```python
from cernora import MetricContext

metric_context = MetricContext.from_import(package, context)
records = plan.evaluate(metric_context, authority)
observations = plan.observations(records)
```

Use those observations in the existing Score and return those records in
`ProfileAssessment.result_records`. The Profile still owns Evidence projection and the
Gate policy. The evaluator continues to cross-check identities, references, required
observations and report/score agreement. See the packaged examples for the complete code.
Do not accept Plan overrides from individual runs or derive expected facts from their answers.

## Roles and result contracts

- `required`: boolean result becomes a constraint. A numeric result requires an explicit
  inclusive `maximum`; its measurement is retained as `<metric_id>.value`, alongside the
  boolean constraint under `<metric_id>`.
- `advisory`: visible result that does not enter the Gate.
- `diagnostic`: measurement or diagnostic that does not enter the Gate.

The first version supports upper bounds only, not weights, arbitrary threshold expressions,
or report priority overrides. Task outcome and policy composition remain Profile-owned;
choose required bindings to express the domain's requirements. A non-valid required record
never becomes a passing observation. Optional failures do not alter other results.

## Built-in catalogue

| Metric | Parameters | Calculation and evidence boundary |
| --- | --- | --- |
| `ToolSelection` | `allowed_tools`, optional `allow_empty=false` | Tests every recorded tool against the explicit set. Empty traces are not passing by default. Incomplete traces are unavailable. |
| `ArgumentMatch` | `allowed_argv`, optional `allow_empty=false` | Maps each tool to an explicit list of exact argv alternatives. Undeclared tools or arguments fail. No shell parsing, inferred equivalences or domain-specific argument rules. |
| `FactMatch` | `answer_artifact`, `source_artifact`, nonempty `expected`; optional JSON pointers and `allow_extra=false` | Compares structured answer fields with frozen expected values and a matching delivered successful tool output. Uses actual terminal-answer identity; merely naming an artifact or citation does not establish support. |
| `ToolCalls` | none | Counts invocation identities, including failed attempts, repeated tools, help and Skill reads. Incomplete or duplicate-identity traces are unavailable, never an exact zero. |
| `Latency` | `artifact`, optional `scope="agent_wall"` | Reads a bound JSON timing record with `clock_id`, `scope`, `start_ms`, `end_ms`; computes elapsed milliseconds in one declared clock domain. Invalid, reversed or missing intervals are unavailable. |

For example, `ArgumentMatch` parameters may contain:

```json
{"allowed_argv":{"lookup":[["lookup","--id","alpha"],["lookup","alpha"]]}}
```

`FactMatch` uses RFC 6901 object/array pointers. It distinguishes JSON booleans and numbers,
requires every expected field, and rejects extra answer fields unless explicitly permitted.
A missing answer field or wrong answer is a valid false result when the expected source is
available. Missing source/mapping is unavailable. Disagreement between the frozen reference
and cited source is uncertainty, not evidence that the Agent failed. This is exact structured
comparison, not natural-language entailment.

The catalogue intentionally does not yet perform multi-source fact joins, dynamic D2 argument
binding, general CLI normalization, partial-trace lower bounds, or provider timing capture.
Profiles own source mapping; new semantic capabilities need versioned implementations and
conformance evidence. Timing bytes must come from an existing bound artifact, never an
unreferenced attachment. A claimed clock domain or content digest is not producer authentication.

## Two domains and a custom Metric

Run the synthetic resource-status and inventory Profiles outside the checkout after installing
the wheel, using a fresh output directory:

```sh
python -m cernora.examples.metric_plans /tmp/metric-plan-example
```

Both use the same five implementations. Inventory adds `MinimumStock` through the same
Metric protocol. The command verifies pass, wrong-answer failure, incomplete capture and
reference-conflict behavior, including strict report reload for published evaluations.
The synthetic wrapper emits a timing receipt on its diagnostic stream; it does not pretend
these bytes were captured from a live Agent. The example is authoring documentation, not a
new builtin selector or evidence of live integration.

A custom implementation supplies `definition`, `validate_parameters(parameters_json)` and
`evaluate(context, parameters_json)`. It returns an existing ResultRecord with its own metric
ID, wire version `agent.evaluator.result-record/v1`, role `diagnostic`, the declared value
shape, and references obtained from the context. The Plan applies the binding role afterward.
See `MinimumStock` in `cernora.examples.metric_plans` for an implementation.

Context contains immutable completed calls and artifact bytes. Each implementation receives
only those inputs and canonical parameters. Returned records are revalidated, including
reference membership, duplicate references, shape and identity. Exceptions or invalid custom
results become `invalid` records with the stable reason `metric_execution_or_contract_error`;
exception text is not copied into public output. The Metric's declared version must change
when its calculation changes. No mechanism proves that arbitrary Python code honestly uses
its declared version: custom Metrics, like Profile factories, are trusted code, not sandboxed
plugins. They must not access network, credentials, clock, filesystem or undeclared resources.

## Compatibility and migration

This is additive Preview in the `0.1.x` line. It changes neither bundle/import/report wires
nor existing Profile semantics. The package-root exports documented here and their Metric
parameter contracts are Preview; other implementation helpers remain internal.

Opt in with a new Profile/scorer authority and stored Plan resource. Preserve old authorities
and old reports; do not reinterpret historical results through a new Plan. Role, parameter,
maximum, order or Metric-version changes alter the Plan/scorer digest and require new
Profile authority. Strict reload must select the matching old or new Profile explicitly.

The existing Bundle boundary is preserved: a complete successful terminal permits pass/fail,
whereas incomplete infrastructure or terminal evidence permits inconclusive. A required Metric
that cannot decide over a bundle claiming complete evidence produces an invalid/unavailable
observation, and the existing evaluator rejects publication rather than inventing a pass or
rewriting terminal evidence. Such conflicts have CLI error class 3. A genuinely incomplete
capture can persist an inconclusive report. Do not mark a runtime incomplete just to accommodate
a scoring error. Extending that boundary would require a separate compatibility decision.

Validation includes two-domain import/evaluate/reload, three identical evaluations of the
same input, Plan drift, tampered artifacts, unknown parameters/versions, missing evidence,
source conflicts, numeric thresholds and custom Metric exceptions/invalid references.
