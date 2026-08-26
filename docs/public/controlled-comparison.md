# Controlled comparisons

Cernora `0.1.4` adds an additive Preview surface for comparing exactly two configurations from one
complete `BatchInput v1`. It consumes completed evidence only; it does not run an Agent, select a
configuration, or authorize promotion.

## Controlled input

`ComparisonInput v1` embeds the full Batch Input and selects a Baseline and Candidate. The input
must exhaust the Batch configurations and bind every Case, split, Experiment and repetition. For
every Case-by-configuration cell, it embeds a strict canonical `ExperimentAuthority v1` whose
recomputed digest must equal the Batch slot's `experiment_id`. Core derives the Runtime, model,
prompt/instruction, tool schema, generation configuration, timeout, resources, retry policy,
dataset, Profile, case-neutral evaluation policy, case-specific evaluation authority, report
contract and statistical-plan projections from that bound authority; they are not independent
caller assertions.

A separately content-identified `Treatment v1` declares every permitted arm difference. Its
closed change kinds are prompt/instruction, model, tool schema, generation configuration and
Runtime version. Every actual projection difference must have exactly one matching Treatment
entry; invariant or undeclared differences produce `not_comparable`, never a partial comparison.
Configuration-level projections must also remain coherent across Cases. Embedded Evaluation
receipts, when present, must match the projected Case, Profile and evaluation authorities.
Callers cannot supply rates, deltas, intervals or conclusions.

## Statistics

The initial Primary Outcome is Reliable Success Rate: `pass` counts as one; behavioral failure,
evaluation invalidity and infrastructure unavailability count as zero. Trials pair by Case and
predeclared repetition. Retry Attempts remain diagnostics and never become independent samples.

`case-clustered-paired-bootstrap/v1` samples whole paired Cases with a versioned SHA-256 counter
sampler, retains every Trial in each sampled Case, uses exactly 10,000 resamples, and reports a
closed 95% nearest-rank percentile interval. Its seed comes from the Comparison Input identity.
An interval touching zero is `uncertain`. Cernora emits no p-value or significance claim.

When predeclared and qualified, pass@k is `1-C(n-c,k)/C(n,k)` and pass^k is
`C(c,k)/C(n,k)`. The calculation requires equal independent Trial counts; retries do not count.

## Guardrails and conclusions

Hard Guardrails are predeclared, scoped and evaluated independently. Supported metrics are
evaluation validity, Reliable Success Rate, and Profile-owned failure-code rate. Missing or
incompatible evidence makes a Guardrail unavailable and blocks `improved`.

The closed conclusions are `improved`, `no_change`, `uncertain`, `mixed`, `regressed` and
`not_comparable`. `improved` requires a wholly positive Primary interval, a point delta meeting the
predeclared practical threshold, and every hard Guardrail satisfied. Guardrails are never averaged
into a composite. The Summary also reports a paired four-by-four outcome transition matrix and
evidence-bound failure-code migration; these diagnostics do not choose the conclusion.

## API, package and CLI

Package-root Preview functions include `materialize_treatment`, `materialize_comparison_input`,
`build_comparison_summary`, `summarize_comparison`, `reload_comparison_summary` and
`reload_comparison_package`. `reload_batch_summary_package` exposes the full strict M2 package as a
path-free `BatchInput` plus its derived `BatchSummary` so assemblers do not discard Trial evidence.

```bash
cernora comparison validate comparison-input.json
cernora comparison summarize comparison-input.json --output comparison-summary
```

The output is a new atomic closed directory containing canonical input and Summary JSON,
deterministic Markdown, a binding receipt and `digests.json`. Valid comparisons, including
`not_comparable` or non-improving results, exit `0`; usage/configuration conflicts exit `2`; corrupt
or unverifiable input exits `3`.

## Compatibility and migration

The M3 surface is additive Preview in the local `0.1.4` release candidate and has not been publicly
released. Existing evidence, Profile, evaluation and M2 Batch contracts are unchanged. M2 callers
need no migration. New comparison producers must pin the versioned schemas and materialize
identities only after all declarations and Trial evidence are frozen.
