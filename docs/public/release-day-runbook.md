# Release-day runbook

This is the immutable release procedure for Cernora `0.1.0`. A listed step is not proof that
the remote action completed; the release evidence records the actual state. The release owner
is `Yangyang96`; the PyPI and TestPyPI username is `oohchild`.

## Hard entry conditions

- The final pre-release Goal is `READY_FOR_REMOTE_RELEASE_HANDOFF`, with fresh artifact
  digests and all local gates passing.
- `https://github.com/Yangyang96/cernora` is still the approved repository target and the
  release owner has admin access.
- The `cernora` project name is still available on the target package index, or the owner has
  already created the project through the approved pending-publisher flow.
- The release owner rechecks the recorded name/trademark risk, Apache-2.0, `NOTICE`, shipped
  provenance, copyright subject and public-distribution approval.

Stop if any identity, approval, artifact digest or support claim has changed.

## 1. Freeze publication facts in one bounded release window

Use the actual UTC publication date as `YYYY-MM-DD`; do not substitute the date on which the
candidate was prepared.

1. `CHANGELOG.md` must contain `## 0.1.0 - YYYY-MM-DD` and `Initial public release.`
2. Both READMEs must use the current-release notice and install through a supported Python
   virtual environment with `python -m pip install cernora`.
3. `SECURITY.md` must describe the published `0.1.x` support rule and keep the no-LTS promise.
4. Recheck every link and platform row. Do not promote Linux, Windows, macOS, architecture or
   installer support without the native evidence required by the matrix.

These facts change the wheel and sdist bytes compared with the TestPyPI rehearsal. Rebuild,
rerun every full gate, reinspect both archives and record new SHA-256 digests before any tag
or upload.

## 2. Establish the public repository controls

1. In a fresh clone of the approved private repository, preserve its benign placeholder commit,
   add only the rebuilt allowlisted source as one clean `main` commit, and push without force.
2. Let `.github/workflows/ci.yml` run on Ubuntu with Python 3.12 and 3.13. Its retained
   `cernora-dist-<commit-sha>` artifact must match the locally accepted files byte-for-byte.
3. Protect `main`: require the CI checks, block force pushes and deletion, require review for
   changes when another trusted reviewer is available, and restrict direct release changes.
4. Create `testpypi` and `pypi` GitHub environments. Restrict deployment refs; require a
   reviewer and prevent self-review when the repository plan and contributor set make that
   possible. Do not allow an unprotected auto-created environment to publish.
5. Enable GitHub private vulnerability reporting and verify that the path described in
   `SECURITY.md` is visible before calling it supported.
6. Make the repository public only after the exact private `main` CI and available controls pass.

Windows remains not yet supported until native Windows CI exercises the README flow and both
empty/nonempty atomic directory-publication races. Add macOS or other Linux jobs before
broadening those rows beyond their recorded architectures and evidence.

## 3. Configure Trusted Publishing

Configure the two services independently; the user accounts being named the same does not
share settings.

| Index | Owner/repository | Workflow | Environment |
| --- | --- | --- | --- |
| TestPyPI | `Yangyang96/cernora` | `.github/workflows/release.yml` | `testpypi` |
| PyPI | `Yangyang96/cernora` | `.github/workflows/release.yml` | `pypi` |

Use OIDC only: no long-lived package-index token or password belongs in repository secrets.
The workflow grants `id-token: write` only to the selected publish job, downloads the exact
artifact from an identified successful CI run, and does not rebuild. Protect changes to the
workflow as release-authority changes.

## 4. Rehearse, tag and publish

1. The `0.1.0` TestPyPI rehearsal is already immutable and must not be overwritten after the
   publication-fact edit. For future versions, rehearse before freezing the production version
   or use an explicit prerelease version; never reuse a filename.
2. Bind the final artifact pair to the exact successful CI run and compare its SHA-256 values
   with the locally accepted pair before continuing.
3. Create `v0.1.0` on the exact accepted `main` commit. Never move or replace this tag.
4. Create the GitHub Release from that tag and attach the same accepted wheel and sdist.
5. Dispatch `release.yml` from the `v0.1.0` tag with `target=pypi`, the same CI run ID and
   commit SHA. The protected `pypi` environment is the final upload checkpoint.
6. Fetch the production index record, compare filenames and SHA-256 values, then install
   `cernora==0.1.0` from real PyPI in clean Python 3.12 and 3.13 environments and rerun the
   documented examples.

## 5. Start the next version

After `0.1.0` is published, open a new `Unreleased` section and bump the project to `0.1.1`
for any patch. Build new artifacts and create `v0.1.1`; never edit `v0.1.0`, move its tag,
replace its GitHub Release assets or attempt to overwrite its PyPI files. A breaking Supported
Preview change follows the compatibility matrix and requires `0.2.0` plus migration notes.
