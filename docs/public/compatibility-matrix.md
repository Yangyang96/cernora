# Compatibility matrix

Cernora `0.1.x` is pre-1.0. Compatibility is defined by tier rather than by treating every
importable module as stable.

| Surface | Tier | `0.1.x` policy |
| --- | --- | --- |
| Python 3.12 and 3.13 | Supported Preview | Tested release range; dropping either requires a minor version and migration note. |
| `cernora evidence import` and `cernora evidence evaluate` | Supported Preview | Command shape, exit classes and canonical JSON behavior remain compatible. |
| `cernora profile init` and `cernora profile validate` | Supported Preview | Private-default workspace and explicit Profile selection remain compatible. |
| EvidenceBundle v2 and import receipt/manifest v2 | Supported Preview | Wire fields and strict validation semantics are not reinterpreted within `0.1.x`. |
| Evidence v1, Score v1 and GateDecision v1 | Supported Preview | Existing wire identifiers and canonical semantics are retained. |
| Documented package-root models and import/evaluate functions | Supported Preview | Compatible within `0.1.x`; additions may be made without changing established behavior. |
| Canonicalization, authority binding, digest checks, conflict-safe publication, strict reload and fail-closed outcomes | Supported Preview | Safety semantics are preserved; they are not relaxed for compatibility. |
| `Profile`, `Adapter`, authoring dataclasses and conformance helpers | Preview | May evolve within `0.1.x` with changelog and migration notes; deprecate first where feasible. |
| Reference Profile layout and Profile-specific helper shapes | Preview | May evolve with documented migration. Profile authority versions remain explicit. |
| Modules not re-exported from `cernora`, parser/storage implementation, tests and build/rebuild scripts | Internal | No compatibility promise. |

## Platform support matrix

The `py3-none-any` wheel tag describes packaging, not operating-system evidence. The rows
below are the `0.1.0` release declarations as of 2026-08-14.

| Platform | Python / architecture / installer | Status | Native evidence | Exclusions and release condition |
| --- | --- | --- | --- | --- |
| macOS | CPython 3.12 and 3.13; Apple silicon (`arm64`); wheel and sdist-built wheel | Supported Preview | Native macOS 26.4 `arm64` release acceptance installed the final wheel outside the checkout on Python 3.12 and 3.13; the Darwin atomic no-replace branch and packaged examples passed. The external release evidence pins the exact artifact digest. | Intel macOS and older macOS releases are untested. |
| Linux | CPython 3.12 and 3.13; Ubuntu GitHub-hosted runner target; wheel and sdist-built wheel | Not yet supported | GitHub CI exercises source gates and exact-wheel acceptance on Ubuntu 3.12/3.13 for the release commit. This CI is release evidence, not yet a separately accepted Linux support qualification. | Do not claim Linux support until native atomic-publication races and the complete README flow are accepted as a platform-support packet. Other distributions and architectures remain untested. |
| Windows | CPython 3.12 and 3.13; architecture not yet qualified; wheel and sdist-built wheel | Not yet supported | The Windows atomic directory-publication branch has code review only; there is no native Windows run or Windows CI. | Add native Windows CI that exercises the atomic publication races and README flow before changing this row. |

Platform support is intentionally narrower than Python-language compatibility. A later native
run may promote a row without changing wire contracts, but the evidence date, interpreter,
architecture and exact artifact digest must be recorded first.

## Versioned input and output

Public input is EvidenceBundle v2 and canonical import v2 only. Bundle or import v1 is not
accepted, converted, dispatched or silently upgraded by Cernora `0.1.x`.

The public path retains:

```text
agent.evaluator.evidence-bundle/v2
agent.evaluator.evidence/v1
agent.evaluator.score/v1
agent.evaluator.gate-decision/v1
```

The different version numbers are intentional. Bundle v2 is the evaluation-capable input;
the established Evidence, Score and GateDecision output contracts remain v1. Wire identifiers
are protocol identities and do not follow the Python package name.

## Change rules

- Breaking a Supported Preview surface requires `0.2.0` and migration notes.
- A Preview break within `0.1.x` requires a changelog entry and migration notes, with a
  deprecation period where feasible.
- Additive validation may reject content that never satisfied the documented contract; it
  must not reinterpret previously valid canonical bytes.
- Authority changes require explicit Profile, Case, fixture, scorer or gate versions as
  applicable.
- Corrupt, incomplete or authority-incompatible input cannot be accepted merely to preserve
  behavior.

## Exit classes

| Exit | Meaning |
| --- | --- |
| `0` | Successful command or eligible passing evaluation. |
| `1` | Eligible evidence proves a behavioral failure. |
| `2` | Usage, selection or authority configuration incompatibility. |
| `3` | Corrupt, incomplete or inconclusive evidence, or another fail-closed evaluation error. |

## Explicit exclusions

Compatibility does not imply an agent runtime, execution sandbox, hosted service, Profile
registry, automatic discovery, marketplace, database, Experiment Harness, runtime-receipt
capture or deployment authority. No such surface exists in `0.1.x`.
