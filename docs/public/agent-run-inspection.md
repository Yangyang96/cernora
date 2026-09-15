# Inspect a completed Agent run (Preview)

Cernora inspects an export after your runtime finishes. It does not launch an Agent,
call a model, or execute the commands in the export. This inspection API is separate
from EvidenceBundle v2 import and Profile evaluation; it never produces a task-level gate.

## First run

Install Cernora from this checkout with `uv sync --all-groups`. Save the following
synthetic export as `run.json`:

```json
{
  "schema_version": "agent-run-export/v1",
  "run_id": "run-1",
  "task_id": "task-1",
  "case_id": "case-1",
  "conditions": {
    "agent": "sample-runner-v1",
    "model": "sample-model-v1",
    "prompt_version": "prompt-v1",
    "budget": 1000,
    "toolset_version": "tools-v1"
  },
  "user_task": "Read the service status.",
  "final_answer": "The service status is ready.",
  "events": [
    {
      "seq": 0,
      "timestamp_ms": 0,
      "kind": "user",
      "payload": {
        "text": "Read the service status."
      }
    },
    {
      "seq": 1,
      "timestamp_ms": 10,
      "kind": "tool_call",
      "payload": {
        "invocation_id": "call-1",
        "tool": "service",
        "argv": [
          "service",
          "status"
        ]
      }
    },
    {
      "seq": 2,
      "timestamp_ms": 20,
      "kind": "tool_result",
      "payload": {
        "invocation_id": "call-1",
        "exit_code": 0,
        "timed_out": false,
        "evidence_id": "output-1"
      }
    },
    {
      "seq": 3,
      "timestamp_ms": 30,
      "kind": "final",
      "payload": {
        "text": "The service status is ready."
      }
    }
  ],
  "claims": [
    {
      "path": "/status",
      "value": "ready",
      "evidence_ids": [
        "output-1"
      ]
    }
  ],
  "tool_outputs": {
    "output-1": "{\"status\":\"ready\"}"
  },
  "tool_output_digests": {
    "output-1": "31bf75f4c0a97cc1f7b60df824fa390b3be9ba014f29b63c87c698ba63d9a9fd"
  }
}
```

Save `{"/status":"ready"}` as `reference.json`, then run:

```sh
uv run cernora agent-run inspect run.json --reference reference.json
```

The canonical JSON reports `tool_call_count: 1`, `tool_succeeded: true`,
`state: "evidence_available"` and claims accuracy `1.0`. These are observations about
this declared export, not proof of a live execution or of the prose answer's correctness.
Remove `--reference` to see an inconclusive evidence assessment.

## Connect your runtime

Export the actual user task, final answer and ordered events. Record each tool invocation
with a unique `invocation_id`, tool name and argv, followed by its result with the same ID,
exit code and timeout flag. Concurrent calls may finish out of order. Sequence numbers
must be contiguous from zero and timestamps nondecreasing. Exactly one final event must
terminate the export, with text identical to `final_answer`. A missing result is allowed
as incomplete evidence and cannot yield tool success. Runtime errors remain inconclusive;
nonzero tool exits and timeouts are recorded as tool failures.

Use the runtime's final structured output for `claims`. Do not copy expected values into
claims. Supply independent expected values in the reference, a flat mapping from claim
path labels to JSON values. Paths such as `/status` are labels, not evaluated JSON Pointers.
Missing and extra paths count as mismatches. Nested JSON values compare exactly, including
boolean/number distinctions. Empty claims or references remain inconclusive. Citation
existence is checked, but whether cited text actually supports a claim is not inferred.
Free-text hallucination, intent, expected tool selection and business correctness require
an appropriate Profile/reference; this inspector does not judge them.

`tool_outputs` holds exact UTF-8 strings keyed by evidence ID. `tool_output_digests` must
contain the same keys and lowercase SHA-256 of those UTF-8 bytes. Every output must be
referenced by a tool result; every claim evidence ID must exist. No filesystem paths or
URLs are dereferenced. Redact before exporting, then compute the digest on the redacted
bytes. Keep unredacted exports in your own ignored storage. Digests detect mismatches;
they do not authenticate the producer or establish reference authority.

Conditions record external Agent/model/Prompt/toolset versions and the harness's token
budget. Cernora does not enforce that budget or verify what the runtime actually sent.
Keep actual effective configuration and cost accounting in your harness. Export public
messages only, without private reasoning, credentials or implementation files.

## Python and failure handling

```python
from pathlib import Path
from cernora.evaluation.agent_export import inspect_agent_run

summary = inspect_agent_run(Path("run.json"), reference={"/status": "ready"})
```

`load_agent_run_export` accepts `Path` for a file, or str/bytes containing JSON. Invalid
JSON (including duplicate keys), malformed events, unknown fields/versions and corrupt
output references raise `ContractError`. They are not converted into a passing report.
The legacy `reference_available` argument supplies no reference and cannot enable scoring.

CLI exit codes: 0 = valid inspection without an observed failure; 1 = observed tool failure
or a scored claim mismatch; 2 = command usage error; 3 = invalid or inconclusive evidence.
No-call runs remain `no_tool_call` and have inconclusive claims even if the inspection exits
0. Exit 0 is not a task pass. Valid observations are JSON on stdout; invalid input diagnostics
are on stderr. The command writes no files. Repeating an inspection has no state to conflict
with and emits identical bytes for identical inputs; it is not persisted bundle import.

## Schema and migration

The packaged `agent-run-export-v1.schema.json` is generated from `AgentRunExport`.
Schema validation covers types and field shapes. Runtime validation additionally checks
payload/kind agreement, call ordering, unique IDs, sequence continuity, final text binding,
output digest equality and reference relationships. Validate with Cernora before using a
schema-valid export for conclusions.

This Preview tightens the unpublished draft: empty tool payloads no longer validate;
results require explicit exit code and timeout fields; messages require text; output digests
require corresponding inline bytes; duplicate claims/IDs and dangling references are rejected.
Existing EvidenceBundle v2 inputs and Profile gates are unchanged. Do not rename an existing
bundle to this schema or submit inspection output to `evidence import`.
