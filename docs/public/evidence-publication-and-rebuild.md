# Evidence publication and rebuild policy

Cernora evidence often records tool output, paths and terminal content. Treat every export as
sensitive until it has been deliberately reduced to neutral, reproducible public material.

## What may be published

Repository examples and release artifacts may include only evidence that is:

- newly generated for a neutral public Profile and synthetic Case;
- small enough to review directly;
- free of credentials, personal data, private endpoints and machine-specific paths;
- required to explain or test a public contract; and
- reproducible by a documented deterministic command.

Prefer a compact canonical example, a SHA-256 manifest and the rebuild command over repeated
copies of equivalent runs.

## What must stay out

Do not publish:

- customer, production or proprietary exports;
- credentials, tokens, cookies, keys or endpoint configuration;
- usernames, home directories, checkout paths or machine/process/environment inventories;
- raw private prompts, transcripts, debugging logs or hidden expected answers;
- protected test fixtures, unreleased vulnerability details or unrelated source diffs;
- orchestration records, working plans, review archives or development-intermediate evidence;
- repository metadata or prior history that was not constructed for the public tree; or
- large repeated matrices when a deterministic rebuild and summary are sufficient.

Redaction is not enough when surrounding structure reveals a private system. Replace the
material with a newly authored neutral fixture and rebuild the evidence.

## Public evidence set

For each published generated set, record:

1. the Cernora version and Python version;
2. the public Profile and Case identities;
3. the exact deterministic command;
4. the expected member list and SHA-256 digests;
5. the expected terminal classification; and
6. confirmation that the command uses no network, credentials or source checkout assets.

Generated output should be written to a new directory. Rebuilds must not overwrite prior
evidence. Compare canonical bytes or a sorted path-to-digest manifest, not timestamps or host
metadata.

The wheel-packaged evaluation-core reference rebuild is:

```sh
python -m cernora.examples.offline_workflow ./cernora-offline-example
```

It materializes a synthetic neutral completed export, adapts it to EvidenceBundle v2, imports
and evaluates it, then strictly reloads the persisted result. Run it in a new directory;
success prints `pass`. It does not launch an Agent, exercise a sandbox or capture a runtime
receipt.

## Rebuild review

Before accepting regenerated evidence:

- run the documented command three times in separate clean directories;
- compare the intentional canonical outputs and digests;
- corrupt one bundle or artifact and confirm evaluation cannot pass;
- scan names and payloads for secrets, personal paths and private vocabulary;
- verify every file is an ordinary file inside the declared closed tree; and
- confirm no undeclared repository file was read.

If output varies, document and remove the nondeterministic field before publication. Do not
normalize away a semantic difference after the fact.

## Assurance limits

SHA-256 digests detect content changes and bind referenced bytes. They do not establish who
created the bytes, that the producer was uncompromised, immutable retention, non-repudiation
or malicious-producer resistance. Cernora provides deterministic local evaluation, not an
attestation or archival service.

The packaged rebuild proves only the evaluation-core path from a synthetic completed export.
It is not evidence that an external runtime enforced sandbox, credential, workspace, network,
mount, timeout or cleanup policy. A composed end-to-end system must validate those claims at
the runtime producer boundary and validate scheduling and aggregation at the Experiment
Harness boundary.

Release artifact checks and handoff steps are documented in the
[local release checklist](local-release-checklist.md).
