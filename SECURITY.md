# Security policy

## Supported versions

Cernora `0.1.0` is the current release. Security fixes target only the latest published
`0.1.x` revision. No long-term support window is promised.

## Reporting a vulnerability

Please do not disclose an unpatched vulnerability in a public issue, discussion or pull
request.

Use [GitHub private vulnerability reporting](https://github.com/Yangyang96/cernora/security/advisories/new).
If GitHub does not show the private reporting form, ask a current maintainer through GitHub
to establish a private channel; do not include exploit details in that request. This file
intentionally does not invent an email address, service-level promise or external reporting
URL.

Include, when safe:

- the affected version or commit;
- the relevant command or public API;
- a minimal reproduction using synthetic data;
- the expected and observed fail-closed behavior; and
- potential impact and any known mitigations.

Remove credentials, personal paths, private exports and production data. Maintainers will
coordinate validation and disclosure through the private channel. Response and remediation
times depend on contributor availability and are not guaranteed.

## Security boundary

Cernora evaluates already completed ordinary-file exports. It does not start or supervise
agents and does not claim to sandbox code. A local Profile selected with `--profile-path`
is trusted Python and executes with the invoking user’s permissions. Review it before use.

Agent launch, credentials, workspace, network/mount isolation, resource limits, timeout and
cleanup belong to an external Agent Runtime. Cernora validates only receipt fields and
declared artifact bytes present in EvidenceBundle v2; their integrity digests do not prove
that the declared isolation occurred or that observations were captured outside Agent control.

Treat malformed, corrupt, authority-mismatched or incomplete evidence as untrusted. Cernora
is designed to reject or fail closed on those conditions, but content digests do not prove
producer identity, non-repudiation or resistance to a compromised producer.

Do not put secrets in evidence bundles, Profile resources, examples or reports. If a secret
is exposed, revoke it at its issuing system before preparing a sanitized reproduction.
