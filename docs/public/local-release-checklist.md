# Local release checklist

This checklist prepares a Cernora release candidate for owner review. It does not publish a
package, create a remote repository, push a branch, create a tag or claim trademark approval.

Run it from a fresh public Cernora checkout with Python 3.12 or 3.13 and the locked development
environment available.

## 1. Review release intent

- [ ] `CHANGELOG.md` describes the target release under its exact version and UTC date;
  later work starts under a new `Unreleased` section.
- [ ] README and acceptance material call Cernora an independent evaluation core and do not
  claim that packaged synthetic exports exercise an Agent runtime or sandbox.
- [ ] The version agrees across package metadata, `cernora.__version__` and artifact names.
- [ ] Supported Preview or Preview changes have the required migration notes.
- [ ] Name availability, ownership and legal approval are rechecked by the release owner.
- [ ] `LICENSE` is the canonical Apache License 2.0 text and `NOTICE` matches the shipped
  provenance without inventing an organization.
- [ ] The platform table names Linux, Windows and macOS separately and does not treat a
  universal wheel tag or code review as native execution evidence.

## 2. Run source gates

```sh
uv sync --all-groups
uv run python scripts/release.py preflight
```

The unified command runs the source gates, builds into a fresh temporary directory, inspects
the closed tree and artifacts, installs the fresh wheel offline, and runs the complete Profile
authoring acceptance before printing artifact SHA-256 values. CI repeats wheel acceptance
under both supported Python minors. A release candidate is not accepted from partial or
unread test output.

## 3. Inspect the public tree

- [ ] Only intentional root governance, package, public tests, public examples, public docs,
  CI and release-check files are present.
- [ ] There is no nested repository metadata, prior refs, orchestration state, raw private
  evidence, cache, environment, build output or development archive.
- [ ] Every file is an ordinary file; there are no symbolic links or unexpected large files.
- [ ] Text and filenames are scanned for credentials, personal paths, private endpoints and
  non-public product vocabulary.
- [ ] Markdown relative links resolve inside the public tree and documented commands match the
  current CLI help.

## 4. Inspect artifacts

The preflight command confirms that a fresh build produced exactly one wheel and one source
archive matching `project.version`. To recheck an existing `dist/` directory directly, run:

```sh
uv run python scripts/check_release.py --tree . --dist-dir dist
```

Additionally verify:

- [ ] the wheel contains only `cernora/` and its matching distribution metadata;
- [ ] packaged schemas, Reference Profile resources and the offline example are present;
- [ ] the source archive member set is exactly the allowlisted public tree plus generated
  package metadata;
- [ ] neither artifact contains repository metadata, caches, tests outside the public set,
  credentials, personal paths or undeclared large files; and
- [ ] installed metadata reports Apache-2.0, Python 3.12/3.13 support and only declared
  dependencies.

## 5. Verify wheel-only operation

Create a clean directory outside the checkout and install the built wheel. For a network-free
check, prepare a local wheelhouse containing the Cernora wheel and every declared dependency,
then install only from that wheelhouse:

```sh
cernora_check_dir="$(mktemp -d)"
python -m venv "$cernora_check_dir/venv"
"$cernora_check_dir/venv/bin/python" -m pip install \
  --no-index --find-links ./wheelhouse cernora==<version>
cd "$cernora_check_dir"
"$cernora_check_dir/venv/bin/python" -m cernora.examples.offline_workflow ./run
```

The final command must print `pass`. Repeat in three new directories and compare the
intentional canonical outputs. Confirm the process reads no source checkout, contacts no
network service and requires no credentials.

Corrupt a copied bundle or artifact in a disposable run and confirm the corresponding import
or evaluation exits fail closed rather than passing.

This wheel-only check starts from a packaged synthetic completed export. Record it as
evaluation-core acceptance only; it does not validate Agent launch, sandbox policy, runtime
receipt capture or Experiment Harness behavior.

The unified preflight also runs `scripts/profile_authoring_wheel_check.py` from an isolated
wheel installation. It creates a private Profile, implements the guided assessment, and
requires deterministic `pass`, `fail`, `inconclusive` and import-rejection outcomes.

## 6. Verify publication history

- [ ] The public source commit was created from the final allowlisted tree and does not contain
  private Evaluator repository metadata or history.
- [ ] Existing benign repository setup commits are documented; no force push or unrelated ref
  was introduced.
- [ ] `git status --short` is empty in the publication staging clone after the source commit.
- [ ] The committed tree digest and artifact digests are recorded before tag or upload.

## 7. Record the release checkpoint

Record the exact commands, tool versions, exit statuses, tree digest and artifact digests.
Do not push, upload, tag or announce it as published unless the active release Goal has reached
the corresponding explicit remote checkpoint.

The subsequent remote actions and immutable `0.1.1+` process are ordered in the
[release-day runbook](release-day-runbook.md). Any source-byte change after this checklist
invalidates the build and digest evidence above.
