# Release runbook for `0.1.x`

This is the repeatable release procedure for Cernora `0.1.x`. Run it from a clean clone of
`https://github.com/Yangyang96/cernora`. The release owner is `Yangyang96`; the PyPI and
TestPyPI username is `oohchild`.

Use the version declared in `pyproject.toml` everywhere below. A production tag is exactly
`v<version>`. Published tags, GitHub Release assets and package-index files are immutable;
every correction uses a new version.

## 1. Prepare one release commit

1. Update `pyproject.toml` and `src/cernora/__init__.py` to the same version.
2. Move the intended changes from `Unreleased` to `## <version> - YYYY-MM-DD` in
   `CHANGELOG.md`, using the actual UTC release date.
3. Update both READMEs, security guidance, compatibility claims and migration notes when the
   release changes them. Do not broaden a platform claim without its required native evidence.
4. Recheck the recorded name/trademark risk, Apache-2.0, `NOTICE`, shipped provenance,
   copyright subject and public-distribution approval.
5. Run the unified local gate from the repository root:

   ```sh
   uv sync --all-groups
   uv run python scripts/release.py preflight
   ```

The command checks version/changelog agreement, tests, Ruff, formatting, strict mypy,
`git diff --check`, a fresh isolated build, the closed source tree and both archives. It prints
the exact wheel and sdist SHA-256 values. It refuses a nonempty `Unreleased` section so an
already-published version cannot be certified with later work. Any source-byte change
invalidates those results.

## 2. Merge and bind the CI artifacts

1. Push a release branch and merge it through the protected `main` workflow.
2. Require the Ubuntu Python 3.12/3.13 CI jobs and wheel-acceptance jobs to pass for the exact
   release commit.
3. Record that commit SHA and its successful CI run ID. The retained
   `cernora-dist-<commit-sha>` artifact must contain exactly one matching wheel and sdist.
4. Compare the CI artifact hashes with the accepted preflight hashes before publishing.

The `testpypi` and `pypi` GitHub environments remain protected by deployment-ref rules and an
explicit owner approval. The workflow uses OIDC Trusted Publishing; no package-index password
or long-lived upload token belongs in GitHub secrets.

## 3. Optional TestPyPI rehearsal

Rehearse with a unique prerelease version such as `0.1.1rc1`; TestPyPI filenames cannot be
overwritten. Dispatch `.github/workflows/release.yml` with `target=testpypi`, the exact CI run
ID and commit SHA. The workflow downloads the inspected CI artifact and derives its version
from the matching wheel/sdist pair without rebuilding.

After a successful rehearsal, prepare the final production version in a new commit and rerun
the complete preflight and CI sequence. Never relabel prerelease bytes as a production version.

## 4. Publish production

1. Create the annotated tag `v<version>` on the exact accepted `main` commit. Never move or
   replace it.
2. Create the GitHub Release from that tag and attach the exact accepted wheel and sdist.
3. Dispatch `.github/workflows/release.yml` from `v<version>` with `target=pypi`, the same CI
   run ID and commit SHA.
4. Approve the protected `pypi` environment. The workflow verifies the CI identity, derives
   the artifact version, requires the tag to equal `v<artifact-version>`, and uploads without
   rebuilding.

## 5. Verify production

From the exact release tag checkout, run:

```sh
uv run python scripts/release.py verify --version <version>
```

The command downloads the exact production-PyPI wheel and sdist, verifies their published
SHA-256 values and closed contents, installs `cernora==<version>` from production PyPI in clean
CPython 3.12 and 3.13 environments, runs `pip check`, proves the import origin is inside each
environment, reruns the offline/backend/frontend/fail-closed acceptance flows and requires
identical result manifests across both Python versions.

## 6. Start the next version

After publication, add a new `Unreleased` section. A compatible patch increments the patch
version; a breaking Supported Preview change follows the compatibility matrix and requires a
minor version plus migration notes.

`v0.1.0`, its GitHub Release assets and PyPI files are permanently closed. Apply the same rule
to every later release: never edit published release bytes or move a published tag.
