# Profile authoring

The Profile SDK Preview lets a project define deterministic validation and assessment for
one explicit class of completed evidence. It does not provide runtime execution or plugin
discovery.

## Create a private scaffold

From a project directory, run:

```sh
cernora profile init my-profile
```

Cernora uses the nearest Git root, or the current directory when no Git root exists, and
creates:

```text
.cernora/
  .gitignore
  profiles/
    my-profile/
      profile.py
      profile.json
      resources/
        expected-value.json
      cases/
        pass.json
        fail.json
        inconclusive.json
        corrupt-artifact.json
        authority-mismatch.json
        scorer-policy-mismatch.json
        gate-policy-mismatch.json
      fixtures/
        pass/
        fail/
        inconclusive/
        corrupt-artifact/
        authority-mismatch/
        scorer-policy-mismatch/
        gate-policy-mismatch/
      tests/
        test_profile.py
      README.md
```

- `profile.json` is the strict CaseProfile v1 authority; `profile.py` is the fixed,
  fail-closed factory.
- `resources/expected-value.json` is the frozen expected stdout the scaffold Case compares
  against; its digest is bound in `profile.json`.
- `cases/*.json` declares one behavior test row each for `cernora profile test`.
- `fixtures/*/` holds one complete synthetic EvidenceBundle v2 package per row.
- `tests/test_profile.py` proves the scaffold loads and fails closed; `README.md` documents
  authority roles and version-bump rules.

The ignore file contains `*`, making the workspace private by default. Cernora does not run
Git commands and does not stage or publish the Profile. Do not force-add `.cernora/`.

For a deliberately public location, provide it explicitly:

```sh
cernora profile init my-profile --output profiles/my-profile
```

Initialization refuses invalid names, existing destinations and unsafe filesystem entries
rather than overwriting them.

## Authority file

`profile.json` is a strict `CaseProfile` v1 document. It declares:

- a unique Profile identity and version;
- one or more uniquely identified Cases;
- fixture references and exact digests;
- the scorer policy and required observations; and
- the gate policy and required score identities.

Treat a change to Profile, Case, fixture, scorer or gate identity as an authority change.
Evidence created for different authority must fail closed, not be coerced into the new
Profile.

## Fixed factory

Local loading executes exactly `profile.py:create_profile()` from the directory supplied by
the user:

```python
from cernora import Profile


def create_profile() -> Profile:
    return MyProfile()
```

The returned object must implement the Preview `Profile` protocol:

```python
class Profile(Protocol):
    @property
    def authority(self) -> CaseProfile: ...

    @property
    def projection_version(self) -> str: ...

    def validate_import(
        self,
        package: AuthorityBoundImportPackageV2,
    ) -> None: ...

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment: ...
```

The generated scaffold deliberately raises `NotImplementedError` from `assess()`. It cannot
accidentally pass evidence before the author implements assessment.

## Implement validation

`validate_import()` should reject any authority or Profile-specific structural mismatch. At
minimum, compare the bound Profile and Case with `authority`. Validate command shapes,
terminal payloads and Profile-owned formats here when they are prerequisites for meaningful
assessment.

Do not infer missing observations, repair producer bytes or read undeclared files. Generic
bundle, artifact, digest and closed-tree validation is already owned by the importer.

## Implement assessment

`assess()` receives an immutable authority-bound package and evaluator-generated context. It
returns `ProfileAssessment` containing:

- Evidence v1 bound to the supplied evaluation and source receipt;
- Score v1 whose observations reference that Evidence; and
- the exact required observation identifiers declared by the scorer policy; and
- optionally, typed Preview `ResultRecord` values in `result_records`.

Keep assessment deterministic and side-effect free. A Profile must not launch tools, contact
services, mutate the imported package, publish output or compose GateDecision. The deep
evaluator cross-checks identities and required observations, applies gate policy, persists the
result and reloads it strictly.

When `result_records` is non-empty, every required observation must have a matching boolean
`outcome` or `constraint` record consistent with Score v1. The deep evaluator validates each
record's evidence reference, derives report validity, and persists a manifest-bound
`evaluation-report.json`. Advisory or diagnostic records remain visible but cannot change
the GateDecision. Leave the field at its default `()` to preserve the pre-report behavior.

Missing, malformed or contradictory evidence must not produce a passing observation. Use a
behavioral false observation only when sufficient valid evidence proves the behavior failed;
otherwise allow evaluation to fail closed as inconclusive.

## Validate and test

Static conformance checks the protocol and canonical authority:

```sh
cernora profile validate --profile-path .cernora/profiles/my-profile
```

This command executes trusted local Python. Review `profile.py` before running it. Static
conformance does not prove assessment behavior.

`profile test` runs the complete behavior workflow in one command: static conformance plus a
real import, evaluation and strict reload for every `cases/*.json` row:

```sh
cernora profile test --profile-path .cernora/profiles/my-profile
```

Each row declares a `fixture` subdirectory under `fixtures/` and an `expected` outcome of
`pass`, `fail`, `inconclusive` or `import_rejection`. The command runs every row three times,
requires byte-identical persisted results, and reports a canonical JSON summary. It exits `0`
only when every row matches its expected outcome deterministically; a behavioral mismatch is a
distinct non-zero exit, so a CI gate cannot mistake "loads successfully" for "evaluates
correctly." `--output` selects a disposable output directory (a temporary directory is used
otherwise); `--repetitions` overrides the default of three.

Every declared `case_id` must belong to the Profile authority and match the fixture bundle.
Expected import rejections retain their deterministic diagnostic, including stale Profile,
scorer-policy and gate-policy authority. Evaluation rejects and identifies missing required
observations, mismatched scorer versions and unbound Evidence-reference locators and digests.

The generated scaffold stays fail-closed until you implement `assess()`. Its `profile test`
run reports `inconclusive` for the missing-evidence fixture and fails closed for completed
evidence, proving the scaffold never silently passes.

A complete Profile test suite should also cover:

1. one valid import and evaluation followed by strict result reload;
2. every required observation's pass and behavioral-fail cases;
3. malformed payload, artifact corruption and authority mismatch;
4. deterministic repeated evaluation with byte-identical inputs; and
5. absence of network, credentials and undeclared filesystem dependencies.

Use `builtin:offline-workflow`, `builtin:coding-task`, `builtin:tool-workflow` and
`builtin:coding-evaluation` as packaged reference Profiles, not as a registry. The latter two
demonstrate structured results for tool and coding evidence respectively; selection is always
explicit. The coding example consumes frozen synthetic execution capsules and does not show
how to execute untrusted candidate code.

## Implement the scaffold assessment

The minimal implemented assessment for the generated scaffold is shipped as the
`cernora.examples.profile_authoring` reference. It implements one required observation,
`claim_grounded`, which is `true` exactly when the run recorded one `check_value --key alpha`
action, its stdout equals `resources/expected-value.json`, the terminal claim equals the frozen
value, and the claim's `evidence_sha256` equals the stdout SHA-256. Missing or
infrastructure-inconclusive evidence emits an `invalid` observation rather than a behavioral
`false`, so it stays `inconclusive`.

```python
from cernora.examples.profile_authoring import write_implemented_profile

write_implemented_profile(Path(".cernora/profiles/my-profile"))
```

After implementing `assess()`, rerun both commands. The first three fixtures report `pass`,
`fail` and `inconclusive`; the corruption, authority, scorer-policy and gate-policy mismatch
fixtures report `import_rejection` with their deterministic diagnostics. The
`scripts/profile_authoring_wheel_check.py` script rebuilds this exact loop from an installed
wheel in a clean project, requiring no credentials, blocking network access and refusing a
source checkout.

## Evolution

### `result_records` migration

`ProfileAssessment.result_records` is additive and defaults to `()`, so existing Profile
constructors require no change. To opt in, emit versioned records for every required Score
observation, keep their values/applicability/reasons/evidence references consistent with
Score v1, and treat numeric units and directions as part of the record contract. Do not
write `evaluation-report.json` yourself; persistence and strict reload belong to Cernora.

Profile authoring APIs and Reference Profile layout are Preview. Breaking changes within
`0.1.x` require a changelog entry and migration notes, with deprecation first where feasible.
Version your Profile authority and projection deliberately; never relabel bytes created under
an earlier meaning.

### Observation ownership before `MetricPlan`

Until a shared Metric SDK exists, a Profile owns its deterministic observations directly: it
emits `ScoreObservation` values and, optionally, typed `ResultRecord` values from the same
frozen Evidence material. The deep evaluator validates identity, evidence binding,
required-observation order and Gate consistency, then persists and strictly reloads the
result. A later `MetricPlan` must reuse this proven ownership shape rather than reinterpreting
it: each Profile-owned observation maps to one versioned metric with an explicit validity
state, a unit and direction where numeric, and the same evidence references. Authority and
decisions must not be silently reinterpreted across that migration.
