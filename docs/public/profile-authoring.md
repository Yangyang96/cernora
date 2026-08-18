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
      profile.json
      profile.py
```

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
