# Cernora

**English** | [简体中文](https://github.com/Yangyang96/cernora/blob/main/README.zh-CN.md)

> Evidence-bound evaluation for tool-using agents.

Cernora is an independent evaluation core for completed agent runs. It is offline and
runtime-neutral, turning producer-owned exports into evaluator-owned, reproducible results:

```text
completed export -> EvidenceBundle v2 -> Import -> Evidence -> Score -> GateDecision
```

Cernora does not ask the runtime whether it succeeded. It validates the evidence,
binds it to an explicit Profile and Case, reloads every persisted result strictly,
and fails closed when evidence or evaluation authority is missing, inconsistent or
corrupt.

> **Current release:** `0.1.0` is the initial public release. Python 3.12 and 3.13
> are the tested language targets; see the
> [platform matrix](https://github.com/Yangyang96/cernora/blob/main/docs/public/compatibility-matrix.md#platform-support-matrix)
> for OS status.

## Why Cernora?

A plausible final answer is not proof that an agent completed a task correctly.

An agent can select the wrong tool, pass the wrong arguments, ignore the returned
data, modify an unexpected artifact, or report success after its environment failed.
If all of those outcomes are reduced to one score, behavioral failures and invalid
evaluations become indistinguishable.

Cernora makes three distinctions explicit:

- **execution and evaluation are separate authorities;**
- **scoring starts only after completed evidence passes strict validation;**
- **behavioral failure is different from missing, corrupt or inconclusive evidence.**

This makes evaluations replayable, reviewable and suitable for CI or release
decisions without giving the evaluator control of the agent runtime.

## Where Cernora fits

Cernora owns the offline decision path, not Agent execution or experiment
orchestration. An external Runtime produces a completed export; an explicit Adapter
normalizes it; Cernora validates, scores and emits a bound `GateDecision`. See
[Architecture](https://github.com/Yangyang96/cernora/blob/main/docs/public/architecture.md)
for the complete composition and exact
component responsibilities.

## Core guarantees

- **Runtime-neutral:** evaluates completed local exports rather than starting or
  supervising an agent.
- **Evidence-bound:** binds Profile, Case, fixture, artifact, producer and run
  identities through explicit versioned contracts and content digests.
- **Strictly replayable:** canonical packages are persisted and reloaded before a
  result is accepted.
- **Fail-closed:** corrupt, incomplete or authority-incompatible evidence never
  becomes a pass.
- **Outcome-aware:** distinguishes eligible behavioral failure from an invalid or
  inconclusive evaluation.
- **Portable:** public examples and Profile resources run from the installed wheel
  without a source checkout, service credential or network connection.

Content digests detect changed bytes; they do not authenticate a producer or provide
non-repudiation.

## Quickstart

### 1. Install from PyPI in a virtual environment

Use CPython 3.12 or 3.13. The commands below create an isolated environment so the
installation does not modify a system- or package-manager-owned Python. Replace
`python3.12` with `python3.13` if that is the interpreter you installed:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install cernora
cernora --version
```

Release maintainers who need to verify exact local artifacts should use the
[local release checklist](https://github.com/Yangyang96/cernora/blob/main/docs/public/local-release-checklist.md)
instead of the PyPI command above.

### 2. Run the packaged workflow example

Run this command from any directory:

```bash
python -m cernora.examples.offline_workflow ./cernora-offline-example
```

The output directory must not already exist. When repeating the example, choose a fresh
path such as `./cernora-offline-example-2`; Cernora refuses to overwrite a completed result.

Expected terminal result:

```text
pass
```

The example materializes a packaged synthetic completed export, adapts it into
EvidenceBundle v2, imports it canonically, evaluates it and strictly reloads the result.
It does not launch an Agent, create a sandbox, capture a runtime receipt or require runtime
credentials.

### 3. Run a packaged coding case

```bash
python -m cernora.examples.coding_task ./cernora-coding-example backend-v1
```

This output directory must also be new for each run.

The coding example also provides `frontend-v1` and `fail-closed-v1` cases. Each case uses a
packaged synthetic candidate/export, binds the candidate to its terminal evidence and
performs evaluator-owned post-terminal checks. It does not run candidate code or an Agent.

## Decision semantics

| Result | Meaning |
| --- | --- |
| `pass` | Evidence is eligible and every required observation is valid and satisfied. |
| `fail` | Evidence is eligible and proves a behavioral mismatch. |
| `inconclusive` | Evidence, infrastructure or evaluation authority is missing, corrupt, incompatible or otherwise invalid. |

CLI exit classes preserve the same distinction:

| Exit | Meaning |
| --- | --- |
| `0` | Successful command or eligible passing evaluation. |
| `1` | Eligible evidence proves behavioral failure. |
| `2` | Usage, selection or authority configuration incompatibility. |
| `3` | Corrupt, incomplete or inconclusive evidence, or another fail-closed evaluation error. |

## Reference Profiles

| Profile | What it demonstrates |
| --- | --- |
| `offline-workflow` | Exact command selection, response integrity and answer grounding against protected fixture evidence. |
| `coding-task` | Candidate format and digest binding, terminal binding and evaluator-owned post-terminal checks across backend, frontend and fail-closed cases. |

These Profiles are neutral public examples. A Profile defines versioned evaluation
authority; users select a Profile rather than toggling individual checks at runtime.

## Evaluate a completed export

Import an EvidenceBundle v2 for one explicit built-in Profile:

```bash
cernora evidence import \
  --profile builtin:offline-workflow \
  --bundle ./completed-export/bundle.json \
  --output ./imported
```

Evaluate the strictly persisted import:

```bash
cernora evidence evaluate \
  --profile builtin:offline-workflow \
  --import-root ./imported \
  --output ./evaluated
```

Cernora `0.1.x` accepts EvidenceBundle v2/import v2 only. It does not convert or
silently reinterpret legacy bundle formats.

## Profile and Adapter SDK Preview

The Preview SDK exposes two intentionally narrow extension seams:

- a `Profile` defines authority, import validation, evidence projection, scoring
  observations and gate policy;
- an `Adapter` converts one already completed native export into a closed,
  canonical EvidenceBundle v2.

The Adapter never starts or retries an Agent, obtains credentials, manages a sandbox or
performs runtime cleanup.

Conformance helpers validate the documented static contract:

```python
from cernora import check_adapter_conformance, check_profile_conformance
```

They complement, rather than replace, a real import and evaluation acceptance run.

### Private-by-default Profile authoring

```bash
cernora profile init my-profile
cernora profile validate --profile-path .cernora/profiles/my-profile
```

By default, Profile sources are created under the nearest project root at
`.cernora/profiles/<name>/`. The `.cernora` workspace contains its own
`.gitignore` so private fixtures and policies are not accidentally committed.

Create a deliberately public Profile only by selecting another destination:

```bash
cernora profile init public-profile --output profiles/public-profile
```

Local Profile loading is explicit trusted-code execution through
`profile.py:create_profile()`. Cernora does not scan for Profiles, maintain a
registry, modify Git state or claim to sandbox local Python.

## What `0.1.0` verified

The release acceptance process:

- installed the exact wheel outside the repository on Python 3.12 and 3.13;
- ran the workflow representative three times with identical canonical results;
- ran all three coding cases three times each;
- strictly reloaded the imported and evaluated result packages;
- rejected corrupt, missing, authority-mismatched and path-traversal evidence;
- preserved an eligible `fail` for valid evidence that proves behavioral mismatch;
- scanned the public tree, wheel and source archive against a closed allowlist.

See the [public acceptance report](https://github.com/Yangyang96/cernora/blob/main/docs/public/acceptance.md)
and its compact [machine-readable summary](https://github.com/Yangyang96/cernora/blob/main/docs/public/acceptance-summary.json).

These checks begin with packaged synthetic completed exports. They prove the Cernora
evaluation-core path; they do not prove Agent launch, sandbox enforcement, trusted runtime
receipt capture or Experiment Harness behavior.

## Scope

Cernora `0.1.x` is the offline evaluation core. It does not provide an Agent Runtime,
experiment scheduler, hosted service, registry, remote judge or deployment authority.
`1.0` will mean that the evaluator contracts are stable, not that Cernora has become
an Experiment Harness.
See [Architecture](https://github.com/Yangyang96/cernora/blob/main/docs/public/architecture.md)
for current ownership boundaries and the
[product roadmap](https://github.com/Yangyang96/cernora/blob/main/ROADMAP.md) for planned capabilities.

## Roadmap

The first post-`0.1` priority is broader deterministic metric coverage using the
existing Profile/Scorer ownership model. The next priority completes the Profile
authoring loop from scaffold to a tested first GateDecision. A reusable `MetricPlan`
comes later, after authoring, a real reference workflow and repeated experiments
have proven the abstraction. See the bilingual
[product roadmap](https://github.com/Yangyang96/cernora/blob/main/ROADMAP.md) for the
full priority order, acceptance signals and explicit non-goals.

## Documentation

- [Product roadmap](https://github.com/Yangyang96/cernora/blob/main/ROADMAP.md)
- [Architecture](https://github.com/Yangyang96/cernora/blob/main/docs/public/architecture.md)
- [Profile authoring](https://github.com/Yangyang96/cernora/blob/main/docs/public/profile-authoring.md)
- [Adapter conformance](https://github.com/Yangyang96/cernora/blob/main/docs/public/adapter-conformance.md)
- [Compatibility matrix](https://github.com/Yangyang96/cernora/blob/main/docs/public/compatibility-matrix.md)
- [Evidence publication and rebuild](https://github.com/Yangyang96/cernora/blob/main/docs/public/evidence-publication-and-rebuild.md)
- [Public acceptance](https://github.com/Yangyang96/cernora/blob/main/docs/public/acceptance.md)
- [Local release checklist](https://github.com/Yangyang96/cernora/blob/main/docs/public/local-release-checklist.md)
- [Release-day runbook](https://github.com/Yangyang96/cernora/blob/main/docs/public/release-day-runbook.md)
- [Changelog](https://github.com/Yangyang96/cernora/blob/main/CHANGELOG.md)

## Contributing and security

Contributions are welcome within the documented runtime/evaluator boundary. Start
with [CONTRIBUTING.md](https://github.com/Yangyang96/cernora/blob/main/CONTRIBUTING.md).

Do not place secrets in evidence or public Profiles. Treat local Profile Python as
code execution with the current user permissions. Report suspected vulnerabilities
through the process in
[SECURITY.md](https://github.com/Yangyang96/cernora/blob/main/SECURITY.md).

## License

Cernora is available under the
[Apache License 2.0](https://github.com/Yangyang96/cernora/blob/main/LICENSE).
