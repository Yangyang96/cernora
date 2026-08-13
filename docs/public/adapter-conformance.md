# Adapter conformance

An Adapter converts one already terminal ordinary-file export into EvidenceBundle v2 and its
declared artifacts. It is a pure normalization seam, not an agent runner.

## Protocol

```python
from pathlib import Path

from cernora import AdaptedBundle, CompletedExport


class MyAdapter:
    def adapt(self, completed_export: CompletedExport, output: Path) -> AdaptedBundle:
        # Read completed_export.root, validate it, and atomically create output.
        # The canonical bundle must be output / "bundle.json".
        ...
```

The caller supplies a completed-export root and a non-existing output path. A conforming
Adapter returns `AdaptedBundle(bundle_path=output / "bundle.json")`.

## Required output

The output directory is closed: it contains exactly `bundle.json` and every artifact path
declared by the bundle, with no extra files. Requirements include:

- `bundle.json` is canonical strict JSON for `agent.evaluator.evidence-bundle/v2`;
- all files are ordinary files and no path is a symbolic link;
- artifact paths are safe, relative and contained by the output directory;
- every declared artifact has byte content matching its SHA-256 digest;
- terminal answer content matches its owned artifact bytes; and
- Profile, Case, fixture, producer and run identities come from the completed export or
  explicit Adapter configuration, never from evaluator expectations invented after the run.

Write through a private staging directory and publish without replacing an existing output.
On failure, leave no partial accepted tree. Equivalent completed exports should produce
byte-identical output.

## Prohibited behavior

An Adapter must not:

- start, resume, retry, terminate or clean an agent;
- obtain or forward credentials;
- contact a network service;
- infer missing stdout, stderr, delivery, commit or terminal facts;
- use expected answers as observed evidence;
- score behavior or compose GateDecision; or
- silently convert another bundle version into v2.

When the completed export cannot prove a required fact, reject it or represent the terminal
state honestly under the v2 contract. Do not manufacture a successful history.

## Run the conformance helper

```python
from pathlib import Path

from cernora import CompletedExport, check_adapter_conformance

summary = check_adapter_conformance(
    MyAdapter(),
    CompletedExport(root=Path("completed-export")),
    Path("conformance-output"),
)
print(summary.bundle_sha256)
```

`conformance-output` must not already exist. The helper runs the Adapter, checks the closed
tree, strict bundle, canonical bytes and artifact digests, and returns an identity summary.
Each output file is limited to 16 MB during this Preview conformance check.

The helper does not monitor network or process creation. Enforce those policy requirements in
tests appropriate to the Adapter, and always perform a real import and evaluation against the
intended Profile.

## Acceptance matrix

Test at least:

1. a valid completed export through adapt, import, evaluate and strict reload;
2. three equivalent runs producing identical bundle and artifact bytes;
3. missing, extra, changed and symbolic-link inputs;
4. malformed terminal status, process result and receipt combinations;
5. wrong Profile, Case, fixture, producer and run identities;
6. truncated, invalid UTF-8 and digest-mismatched artifacts; and
7. an existing output path, which must never be overwritten or repaired.

Conformance validates format and integrity, not truthfulness of a compromised producer. See
the [evidence publication and rebuild policy](evidence-publication-and-rebuild.md) before
committing Adapter fixtures or generated bundles.

Adapter conformance also does not prove that an Agent ran in a sandbox or that a runtime
receipt was captured independently of the Agent. Those are external Agent Runtime claims.
Cernora validates the completed bytes and declared authority presented at its boundary; the
runtime and its Experiment Harness require separate conformance and acceptance.
