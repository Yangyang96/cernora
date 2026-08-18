# Public evaluation-core and Priority 1 acceptance

Cernora `0.1.1` release candidate was exercised with the original sanitized V1/V2
representatives plus the Priority 1 `tool-workflow` and `coding-evaluation` matrices. These
task labels do not mean EvidenceBundle v1: every run uses EvidenceBundle v2/import v2. The
Priority 1 runs also emit ResultRecord v1 and EvaluationReport v1.

The accepted run used clean repository-external Python 3.12.12 and 3.13.12 environments.
Each environment installed fixed Python dependencies and the built Cernora wheel, then ran
the public rebuild script with `PYTHONPATH` unset and user-site packages disabled. The script
rejects a Cernora import from the source repository and blocks Python socket creation inside
the evaluation process.

## Scope limit

The rebuild begins with packaged synthetic completed exports. It does not launch a real
Agent, create or inspect a sandbox, inject credentials, manage a workspace, enforce runtime
network or mount policy, capture tool/process observations, or produce an independently
trusted runtime receipt. Socket blocking proves that this evaluator acceptance stays offline;
it is not an operating-system sandbox claim.

The result therefore validates the Cernora core path—Adapter, EvidenceBundle v2, Import,
Profile assessment, Score, GateDecision and strict reload—not a complete end-to-end Agent
evaluation system. An external Agent Runtime and Experiment Harness require separate
acceptance.

## Result

- Sanitized V1 workflow: three byte-identical `pass` runs with strict persisted-result
  reload.
- Sanitized V2 coding: backend, frontend and fail-closed cases each produced three
  byte-identical `pass` runs with strict reload.
- `tool-workflow`: all 18 frozen rows matched their expected outcome; 17 accepted rows
  produced three byte-identical trees with strict reload and the corrupt row was rejected.
- `coding-evaluation`: all 20 frozen rows matched the 2 pass / 8 fail / 9 inconclusive / 1
  rejection matrix; 19 accepted rows produced three byte-identical trees with strict reload.
- Corrupt artifact, missing artifact, Profile-authority mismatch and candidate traversal
  were rejected before an eligible pass.
- A well-formed but incorrect coding candidate remained eligible evidence and produced the
  expected behavioral `fail` GateDecision.
- Python 3.12.12 and 3.13.12 produced byte-identical 3,778-file acceptance trees with SHA-256
  `c3c8b8f7edfdd8072ba2459cd7eab8886e9dce1609bbbeff670d196aacaae7b9`; the reviewed
  summary SHA-256 is `6ebf251c0d83db68cd8dac6dab2c828012383f59544706e9f5b1db64e1b8d4d1`.

The exact compact result is [acceptance-summary.json](acceptance-summary.json). Raw generated
Bundle, import and evaluation trees are not committed: they are deterministic, larger than
the useful review surface and rebuilt by the command below. No private V1/V2 task data or
development evidence is used.

## Rebuild

Install the built wheel in a clean environment, change to a directory outside the checkout,
then run the repository's public rebuild script by path:

```sh
env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  python /path/to/cernora/scripts/rebuild_acceptance.py \
  --output ./cernora-public-acceptance
```

The command prints `pass` only after comparing `cernora-public-acceptance/summary.json`
byte-for-byte with `docs/public/acceptance-summary.json`; its SHA-256 must match the value
above. The output directory must not already exist.

This is evaluation-core release-candidate evidence, not Agent-runtime/sandbox evidence and
not a claim that GitHub or PyPI publication occurred.
