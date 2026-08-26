# Validity-first batch summaries

Cernora `0.1.3` adds an additive Preview surface for deterministic summaries of already completed
experiment matrices. Core remains Runtime-neutral: it does not start, authenticate, schedule,
retry, interrupt or clean up an Agent, and it does not parse a companion Execution Pack.

## Authoritative input

`BatchInput v1` is one canonical, content-identified JSON value. A producer must declare a complete
ordered Trial-slot inventory and provide exactly one completed Trial for every slot. Every Trial
binds its RunPlan, Execution, Case, Configuration, repetition, Experiment and complete Attempt
chain.

An Attempt contains exactly one of:

- a complete Evaluation Package embedded as byte-exact base64 files, with its evaluator manifest,
  payload digests, contracts and cross-contract identities strictly checked; or
- a normalized, receipt-bound lifecycle failure for an Attempt that produced no evaluable export.

The P4 Attempt identity is separate from the source producer Attempt identity. This preserves the
Execution-wide retry chain while still requiring an embedded Evaluation Package to bind the exact
producer Attempt it evaluated.

Core rejects unknown fields, non-canonical JSON, caller-provided rates, naked pass/fail JSON,
incomplete, duplicate or unknown Trials, broken retry predecessors, mismatched RunPlan or Execution
bindings, digest tampering, invalid package files, non-completed Executions and exhausted budgets.
A verified lifecycle failure is retained as an unavailable Trial; it does not invalidate the batch.

## Outcomes and rates

Core derives exactly four Trial outcomes: `pass`, `behavioral_fail`, `evaluation_invalid` and
`infrastructure_unavailable`. The planned Trial is always the denominator authority. Overall,
Configuration, Case and Case-by-Configuration groups report exact numerator and denominator pairs:

- Evaluation Validity Rate = pass plus behavioral fail / planned Trials;
- Behavioral Success Rate = pass / valid Trials; and
- Reliable Success Rate = pass / planned Trials.

When a group has no valid Trials, Behavioral Success Rate is `0/0` with a null value, not zero.
Attempt diagnostics retain first-attempt success, retry count/rate, Attempt evaluation validity,
infrastructure distribution and verified resource totals. A total is unavailable when any Attempt
lacks the required structured receipt; missing token or cost evidence is never represented as zero.

Milestone 2 publishes no delta, confidence interval, bootstrap result, pass-at-k, Winner,
improvement or regression conclusion. Profile-owned failure codes come only from strictly loaded
versioned ResultRecords and are never guessed from free-form text.

## Python and CLI

Package-root Preview functions include `validate_batch_input`, `build_batch_summary`,
`summarize_batch` and `reload_batch_summary`. The publishing function writes a new closed directory
atomically and refuses to replace any existing path. The package retains `batch-input.json` so
strict reload can rederive the Summary. `batch-summary.json` is authoritative;
`batch-summary.md` contains only facts present in that JSON, and `digests.json` closes the package.

```sh
cernora batch validate batch-input.json
cernora batch summarize batch-input.json --output batch-summary
```

Exit `0` means the input or Summary is valid, even when every behavioral Trial fails. Exit `2`
means CLI usage or authority-selection incompatibility. Exit `3` means corrupt, incomplete or
unverifiable input. Batch quality never uses exit `1` and is not a deployment Gate.

## Migration note

This is an additive opt-in Preview surface. Existing evidence import, evaluation, Profile and Gate
callers require no migration. New batch producers must pin `agent.evaluator.batch-input/v1`, use the
packaged `batch-input-v1.schema.json`, materialize the content identity after all Trial and Attempt
facts are frozen, and treat any later change as a new Batch Input identity.
