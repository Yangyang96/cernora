# Generic Agent Evaluation Integration Proposal

Status: Proposal. A bounded [Preview inspector](agent-run-inspection.md) now implements event integrity, inline digest checks and exact declared-claim comparison. Other proposed evaluation dimensions remain design candidates. This document defines a vendor-neutral Cernora integration boundary. It contains no product-specific commands, production responses, credentials, private runners, or internal implementation details.

## Goal

Allow any Agent Runtime export to be evaluated while keeping four questions separate: intent understanding, tool and parameter selection, tool execution and evidence, and final-answer faithfulness and abstention.

The runtime, model service, and tools remain the user's responsibility. Cernora receives a sanitized completed-run export and, when available, an authoritative reference.

## Proposed export contract

A future `agent-run-export/v1` should include run/task/case identity, fixed-condition metadata, the user task, an ordered event stream, the final answer, referenced or sanitized tool outputs with digests, and optional field-level human references. Unknown fields, missing identity, invalid event order, digest mismatch, or incomplete export must fail closed or remain inconclusive.

## Evaluation and experiment rules

Report intent, first correct tool call, parameter correctness, tool result, field-level factuality, unsupported assertions, latency, call count, and cost separately. Process exit status is one observation only. Use deterministic field checks before semantic judges, preserving judge inputs and versions. Split datasets by independent event; correlated slices stay together. Fix all conditions and change one intervention variable at a time. Report gains, regressions, and cost.

## Implementation order and acceptance

Implement export validation, event normalization, independent tool/final-answer metrics, field-level factuality and evidence-boundary checks, dataset declarations, and offline synthetic fixtures before publishing a minimal integration tutorial. Acceptance requires vendor-neutral import, distinction between no call/tool failure/wrong answer, fail-closed evidence handling, byte-stable repeated evaluation, and no production data or private implementation in public fixtures.
