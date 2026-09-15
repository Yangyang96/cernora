# First integration: from a completed record to a decision

[简体中文](first-integration.zh-CN.md)

This tutorial runs entirely on synthetic, completed records. It requires Python 3.12 or
3.13 and this checkout's wheel; the new inspection example is unreleased. No Agent, model,
credentials or network service is needed after installation.

## Install outside the checkout

From the repository root, build a wheel, then install it in a new environment:

```sh
uv sync --all-groups
uv run python -m build --wheel --outdir /tmp/cernora-onboarding-dist
uv venv /tmp/cernora-onboarding-venv --python 3.13
uv pip install --python /tmp/cernora-onboarding-venv/bin/python /tmp/cernora-onboarding-dist/cernora-0.1.4-py3-none-any.whl
mkdir /tmp/cernora-onboarding-project
cd /tmp/cernora-onboarding-project
. /tmp/cernora-onboarding-venv/bin/activate
```

Use fresh paths if you have already run these commands. All subsequent commands run here,
outside the checkout. Each output path must be new.

## Generate an inspection export

The packaged example materializes four small native records and an independent reference.
It automatically pairs calls and results, assigns contiguous event sequence numbers,
preserves timestamps, maps the recorded structured claims and computes stdout digests:

```sh
python -m cernora.examples.minimal_adapter fixtures records
python -m cernora.examples.minimal_adapter export records/success.json success.json
cernora agent-run inspect success.json --reference records/reference.json
```

Expected: exit `0`, `tool_succeeded: true`, `state: "evidence_available"`, claims accuracy
`1.0`. This is an inspection result, **not a task pass**.

Run the other paths individually; nonzero exits below are intentional:

```sh
python -m cernora.examples.minimal_adapter export records/failure.json failure.json
cernora agent-run inspect failure.json --reference records/reference.json
# exit 1: tool completed, but the recorded claim differs from the reference

python -m cernora.examples.minimal_adapter export records/missing-evidence.json missing.json
cernora agent-run inspect missing.json --reference records/reference.json
# exit 3: missing tool result, inconclusive; no success is invented

python -m cernora.examples.minimal_adapter export records/field-error.json invalid.json
# exit 3: unknown exitCode field rejected; invalid.json is not created
```

The adapter never reads `reference.json`. Failure records contain the observed wrong value;
expected values do not become claims. Editing the reference changes inspection scoring,
not export bytes. Repeating an export to a different destination produces identical bytes.
Malformed JSON, duplicate keys, unknown fields/versions, dangling claim IDs and inconsistent
timestamps fail closed. Existing files are never overwritten.

## Run a complete Profile evaluation

Inspection accepts `agent-run-export/v1` and returns observations. Full evaluation accepts
an **EvidenceBundle v2** bound to a specific Profile/Case/fixture authority, persists Evidence,
Score and GateDecision, and strictly reloads their identities and digests. Inspection output
cannot be imported as a bundle, and exit `0` from inspection cannot serve as a task gate.

The following packaged example is a separate, neutral lookup task. Its completed native
record is converted by `OfflineWorkflowAdapter`, imported, evaluated and strictly reloaded:

```sh
python -m cernora.examples.offline_workflow full-evaluation
# pass

cernora evidence import --profile builtin:offline-workflow \
  --bundle full-evaluation/bundle/bundle.json --output imported
cernora evidence evaluate --profile builtin:offline-workflow \
  --import-root imported --output evaluated
```

Read `evaluated/case-decision.json`, `evaluated/score.json` and `evaluated/evidence.json`.
For a verified read, use the matching Profile:

```sh
python - <<'PY'
from pathlib import Path
from cernora import read_imported_evaluation
from cernora.profiles.offline_workflow import OfflineWorkflowProfile

print(read_imported_evaluation(Path("evaluated"), OfflineWorkflowProfile()).case_outcome)
PY
```

This prints `pass`. The builtin lookup fixture proves pipeline operation only; it is not
an evaluation of your own Agent or a conversion of the preceding status inspection.

## Create and test your own scoring authority

Create a private scaffold, install the shipped minimal reference implementation, then
exercise every outcome through actual import, evaluation and strict reload:

```sh
cernora profile init my-profile
python - <<'PY'
from pathlib import Path
from cernora.examples.profile_authoring import write_implemented_profile

write_implemented_profile(Path(".cernora/profiles/my-profile"))
PY
cernora profile validate --profile-path .cernora/profiles/my-profile
cernora profile test --profile-path .cernora/profiles/my-profile
```

The test command exits `0` when all seven expected outcomes match across three repetitions:
`pass`, `fail`, `inconclusive`, plus four `import_rejection` cases for corrupt artifacts and
incompatible authority. That exit means the test suite passed, not that every fixture passed.
The generated scaffold without an implemented assessment cannot award a pass.

For real inputs, replace the demo assessment and fixture authority with your frozen task
rules and independent references. Then supply your Adapter's bundle to the preceding import
and evaluate commands, replacing `--profile builtin:offline-workflow` in both with
`--profile-path .cernora/profiles/my-profile`. See [Profile authoring](profile-authoring.md)
and [Adapter conformance](adapter-conformance.md) for authority and integrity requirements.

## What you reuse and what you implement

| Layer | Reuse | Your responsibility |
| --- | --- | --- |
| Runtime / harness | Your existing Agent runner | Execute the task; capture actual configuration, ordered calls/results, stdout/stderr, exit/timeout, final answer, wall time and measured cost. |
| Inspection adapter | This example's `adapt_record` / `export_record` | Map your runner's completed data into the declared native record, or adapt the example mapping to its format. |
| Bundle Adapter | `OfflineWorkflowAdapter` as a narrow reference; conformance helper | Map completed evidence to your Profile's contract, preserve authority, bind artifacts/receipts; never manufacture absent facts. |
| Profile | Private scaffold, example assessment, deterministic test loop | Define task success, sufficiency, references and required observations before evaluating the Agent. |
| Evaluation | Import, evaluate, strict reload, batch and comparison APIs | Supply complete evidence and explicitly select the matching authority. |

The minimal inspection example supports sequential calls only. It preserves absent results,
stdout and budget as unknown; `stderr` stays in the native record because this inspection
projection uses stdout evidence only. It does not capture runtime errors, concurrent event
interleavings, full transcripts, billing or receipt authority. Extend the mapping for your
runtime's observed events; never reorder concurrent events to fit the example. Structured
claims must come from the actual final output, not an expected answer or an unreviewed prose
extraction. A citation existing does not prove its content supports the claim.

For a before/after experiment, freeze event groups, development/validation splits, references,
Profile and effective execution conditions first. Change one factor, preserve failed and
incomplete trials, record measured costs separately, and use the
[controlled comparison](controlled-comparison.md) workflow. These synthetic demonstrations
establish neither improvement nor production reliability.

## Acceptance and migration

The installed-wheel acceptance repeats these commands using isolated Python subprocesses:

```sh
/tmp/cernora-onboarding-venv/bin/python -I /path/to/checkout/scripts/onboarding_wheel_check.py \
  --output /tmp/cernora-onboarding-acceptance
```

It rejects source imports and checks inspection exit classes, deterministic bytes, no export
on field errors, a real Profile gate and the seven-case authoring loop. Its `summary.json`
records interpreter/version and outcomes. This is reproducible command acceptance, not a
claim that an independent human completed a usability study.

The example is additive; existing public wires, APIs and evaluation semantics are unchanged.
Its native `synthetic-completed-record/v1` format is an example, not a universal runtime
connector contract. Existing bundles require no migration. Do not relabel inspection exports
as EvidenceBundle v2.
