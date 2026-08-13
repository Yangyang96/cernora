"""Validate and atomically persist canonical EvidenceBundle v2 imports."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from cernora.core.canonical import canonical_json, decode_contract, strict_json_loads
from cernora.core.case import CaseProfile
from cernora.core.errors import ContractError
from cernora.core.evidence_bundle_v2 import (
    EvidenceBundleV2,
    bind_evidence_bundle_v2,
    canonical_evidence_bundle_v2,
    decode_evidence_bundle_v2,
    verify_artifact_payloads_v2,
)
from cernora.ingestion.contracts_v2 import (
    AuthorityBoundImportPackageV2,
    ImportedArtifactV2,
    ImportedBundleIdentityV2,
    ImportedTerminalArtifactOwnerV2,
    ImportedToolArtifactOwnerV2,
    ImportFileDigestV2,
    ImportManifestV2,
    ImportReceiptV2,
    LoadedImportPackageV2,
)
from cernora.ingestion.errors import (
    AuthorityIncompatibleError,
    IngestionConfigurationError,
    IngestionIntegrityError,
    UnsupportedEvidenceVersionError,
)
from cernora.profile import Profile

RAW_BUNDLE_PATH = "bundle.raw.json"
CANONICAL_BUNDLE_PATH = "bundle.canonical.json"
RECEIPT_PATH = "import-receipt.json"
MANIFEST_PATH = "digests.json"

V2_BUNDLE_VERSION = "agent.evaluator.evidence-bundle/v2"
V2_RECEIPT_VERSION: Literal["agent.evaluator.import-receipt/v2"] = (
    "agent.evaluator.import-receipt/v2"
)
V2_MANIFEST_VERSION: Literal["agent.evaluator.import-manifest/v2"] = (
    "agent.evaluator.import-manifest/v2"
)

FileIdentity = tuple[int, int]


@dataclass(frozen=True)
class TreeSnapshot:
    files: dict[str, FileIdentity]
    directories: dict[str, FileIdentity]


@dataclass(frozen=True)
class OutputLocation:
    requested: Path
    resolved: Path
    parent_descriptor: int
    parent_identity: FileIdentity


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or not path.parts
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise IngestionIntegrityError(f"{label} is not a contained canonical path")
    return path


def _open_directory(
    path: Path,
    *,
    configuration: bool,
    label: str,
) -> int:
    error_type = IngestionConfigurationError if configuration else IngestionIntegrityError
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise error_type(f"cannot open ordinary {label}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise error_type(f"{label} is not an ordinary directory")
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise error_type(f"cannot inspect ordinary {label}") from exc


def _open_directory_at(
    parent_descriptor: int,
    name: str,
    *,
    configuration: bool,
    label: str,
) -> int:
    error_type = IngestionConfigurationError if configuration else IngestionIntegrityError
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise error_type(f"cannot open ordinary {label}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise error_type(f"{label} is not an ordinary directory")
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise error_type(f"cannot inspect ordinary {label}") from exc


def _read_regular_at(
    root_descriptor: int,
    relative: str,
    *,
    configuration: bool,
    label: str,
    snapshot: TreeSnapshot | None = None,
) -> tuple[bytes, FileIdentity]:
    error_type = IngestionConfigurationError if configuration else IngestionIntegrityError
    parts = PurePosixPath(relative).parts
    if not parts:
        raise error_type(f"{label} has an invalid relative path")
    current = os.dup(root_descriptor)
    file_descriptor = -1
    prefix: list[str] = []
    try:
        for part in parts[:-1]:
            prefix.append(part)
            next_descriptor = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            info = os.fstat(next_descriptor)
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_descriptor)
                raise error_type(f"{label} traverses a non-ordinary directory")
            if snapshot is not None and snapshot.directories.get("/".join(prefix)) != (
                info.st_dev,
                info.st_ino,
            ):
                os.close(next_descriptor)
                raise error_type(f"{label} directory changed after validation")
            os.close(current)
            current = next_descriptor

        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current,
        )
        info = os.fstat(file_descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise error_type(f"{label} is not an ordinary regular file")
        identity = (info.st_dev, info.st_ino)
        if snapshot is not None and snapshot.files.get(relative) != identity:
            raise error_type(f"{label} changed after validation")
        with os.fdopen(file_descriptor, "rb", closefd=True) as stream:
            file_descriptor = -1
            return stream.read(), identity
    except OSError as exc:
        raise error_type(f"cannot read ordinary {label}") from exc
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        os.close(current)


def _expected_directories(paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _scan_closed_tree(
    root_descriptor: int,
    *,
    expected_files: set[str],
    configuration: bool,
) -> TreeSnapshot:
    error_type = IngestionConfigurationError if configuration else IngestionIntegrityError
    expected_directories = _expected_directories(expected_files)
    actual_files: dict[str, FileIdentity] = {}
    actual_directories: dict[str, FileIdentity] = {}

    def visit(directory_descriptor: int, prefix: str) -> None:
        try:
            with os.scandir(directory_descriptor) as entries:
                for entry in entries:
                    relative = f"{prefix}/{entry.name}" if prefix else entry.name
                    info = entry.stat(follow_symlinks=False)
                    identity = (info.st_dev, info.st_ino)
                    if stat.S_ISDIR(info.st_mode):
                        if relative not in expected_directories:
                            raise error_type(
                                "tree does not exactly match its declared closed file set"
                            )
                        child_descriptor = os.open(
                            entry.name,
                            os.O_RDONLY
                            | getattr(os, "O_DIRECTORY", 0)
                            | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=directory_descriptor,
                        )
                        try:
                            opened = os.fstat(child_descriptor)
                            if not stat.S_ISDIR(opened.st_mode) or identity != (
                                opened.st_dev,
                                opened.st_ino,
                            ):
                                raise error_type("tree directory changed during validation")
                            actual_directories[relative] = identity
                            visit(child_descriptor, relative)
                        finally:
                            os.close(child_descriptor)
                    elif stat.S_ISREG(info.st_mode):
                        if relative not in expected_files:
                            raise error_type(
                                "tree does not exactly match its declared closed file set"
                            )
                        actual_files[relative] = identity
                    else:
                        raise error_type("tree contains a non-ordinary entry")
        except OSError as exc:
            raise error_type("cannot inspect closed tree") from exc

    visit(root_descriptor, "")
    if set(actual_files) != expected_files or set(actual_directories) != expected_directories:
        raise error_type("tree does not exactly match its declared closed file set")
    identities = tuple(actual_files.values())
    if len(identities) != len(set(identities)):
        raise error_type("tree files must have distinct filesystem identities")
    return TreeSnapshot(files=actual_files, directories=actual_directories)


def _source_artifact_payloads(
    root_descriptor: int,
    bundle_name: str,
    bundle: EvidenceBundleV2,
    raw_identity: FileIdentity,
) -> dict[str, bytes]:
    if any(artifact.path == bundle_name for artifact in bundle.artifacts):
        raise IngestionIntegrityError("an artifact path cannot alias the bundle file")
    expected_files = {bundle_name, *(artifact.path for artifact in bundle.artifacts)}
    scanned = _scan_closed_tree(
        root_descriptor,
        expected_files=expected_files,
        configuration=False,
    )
    if scanned.files[bundle_name] != raw_identity:
        raise IngestionIntegrityError("bundle file changed during source validation")

    payloads: dict[str, bytes] = {}
    for artifact in bundle.artifacts:
        _relative_path(artifact.path, label="artifact path")
        payload, _ = _read_regular_at(
            root_descriptor,
            artifact.path,
            configuration=False,
            label="artifact file",
            snapshot=scanned,
        )
        payloads[artifact.artifact_id] = payload
    if (
        _scan_closed_tree(
            root_descriptor,
            expected_files=expected_files,
            configuration=False,
        )
        != scanned
    ):
        raise IngestionIntegrityError("source tree changed during artifact reads")
    return payloads


def _artifact_owners(
    bundle: EvidenceBundleV2,
) -> dict[
    str,
    ImportedToolArtifactOwnerV2 | ImportedTerminalArtifactOwnerV2,
]:
    owners: dict[
        str,
        ImportedToolArtifactOwnerV2 | ImportedTerminalArtifactOwnerV2,
    ] = {}
    for action in bundle.tool_actions:
        owners[action.result.stdout_artifact.artifact_id] = ImportedToolArtifactOwnerV2(
            invocation_id=action.invocation_id,
            kind="tool_stdout",
        )
        owners[action.result.stderr_artifact.artifact_id] = ImportedToolArtifactOwnerV2(
            invocation_id=action.invocation_id,
            kind="tool_stderr",
        )
    if bundle.terminal.answer is not None:
        owners[bundle.terminal.answer.artifact.artifact_id] = ImportedTerminalArtifactOwnerV2(
            kind="terminal_answer"
        )
    return owners


def _build_receipt(bundle: EvidenceBundleV2, raw: bytes) -> ImportReceiptV2:
    canonical = canonical_evidence_bundle_v2(bundle)
    owners = _artifact_owners(bundle)
    return ImportReceiptV2(
        schema_version=V2_RECEIPT_VERSION,
        status="validated",
        evaluation_status="not_evaluated",
        bundle=ImportedBundleIdentityV2(
            bundle_id=bundle.bundle_id,
            schema_version=bundle.schema_version,
            declared_sha256=bundle.bundle_sha256,
        ),
        producer=bundle.producer,
        run=bundle.run,
        profile=bundle.profile,
        case=bundle.case,
        raw_input_sha256=_sha256(raw),
        canonical_bundle_sha256=_sha256(canonical),
        artifacts=tuple(
            ImportedArtifactV2(
                artifact_id=artifact.artifact_id,
                declared_path=artifact.path,
                package_path=f"artifacts/{artifact.path}",
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                owner=owners[artifact.artifact_id],
            )
            for artifact in bundle.artifacts
        ),
        evaluation_boundary=bundle.evaluation_boundary,
    )


def _manifest(files: Mapping[str, bytes]) -> ImportManifestV2:
    return ImportManifestV2(
        schema_version=V2_MANIFEST_VERSION,
        files=tuple(
            ImportFileDigestV2(path=path, size_bytes=len(payload), sha256=_sha256(payload))
            for path, payload in sorted(files.items())
        ),
    )


def _package_files(
    bundle: EvidenceBundleV2,
    raw: bytes,
    artifact_bytes: Mapping[str, bytes],
) -> tuple[ImportReceiptV2, ImportManifestV2, dict[str, bytes]]:
    receipt = _build_receipt(bundle, raw)
    files = {
        RAW_BUNDLE_PATH: raw,
        CANONICAL_BUNDLE_PATH: canonical_evidence_bundle_v2(bundle),
        RECEIPT_PATH: canonical_json(receipt),
    }
    for artifact in receipt.artifacts:
        files[artifact.package_path] = artifact_bytes[artifact.artifact_id]
    manifest = _manifest(files)
    files[MANIFEST_PATH] = canonical_json(manifest)
    return receipt, manifest, files


def _preflight_schema(raw: bytes, *, label: str) -> str:
    try:
        value = strict_json_loads(raw)
    except ContractError as exc:
        raise IngestionIntegrityError(f"{label} has invalid JSON") from exc
    if type(value) is not dict:
        raise IngestionIntegrityError(f"{label} has an invalid schema discriminator")
    version = value.get("schema_version")
    if type(version) is not str:
        raise IngestionIntegrityError(f"{label} has an invalid schema discriminator")
    return version


def _read_package_files(
    root: Path | None = None,
    *,
    root_descriptor: int | None = None,
) -> dict[str, bytes]:
    if root_descriptor is None:
        if root is None:
            raise ValueError("root or root_descriptor is required")
        descriptor = _open_directory(
            root,
            configuration=False,
            label="import package root",
        )
    else:
        if root is not None:
            raise ValueError("root and root_descriptor are mutually exclusive")
        descriptor = os.dup(root_descriptor)
    try:
        initial: dict[str, tuple[bytes, FileIdentity]] = {}
        for path, label in (
            (RAW_BUNDLE_PATH, "stored Bundle"),
            (RECEIPT_PATH, "stored receipt"),
            (MANIFEST_PATH, "stored manifest"),
        ):
            initial[path] = _read_regular_at(
                descriptor,
                path,
                configuration=False,
                label=label,
            )
        raw_bundle = initial[RAW_BUNDLE_PATH][0]
        raw_receipt = initial[RECEIPT_PATH][0]
        raw_manifest = initial[MANIFEST_PATH][0]

        bundle_version = _preflight_schema(raw_bundle, label="stored Bundle")
        receipt_version = _preflight_schema(raw_receipt, label="stored receipt")
        manifest_version = _preflight_schema(raw_manifest, label="stored manifest")
        if (
            bundle_version,
            receipt_version,
            manifest_version,
        ) != (
            V2_BUNDLE_VERSION,
            V2_RECEIPT_VERSION,
            V2_MANIFEST_VERSION,
        ):
            raise UnsupportedEvidenceVersionError("unsupported import package version")

        try:
            manifest = decode_contract(raw_manifest, ImportManifestV2)
        except ContractError as exc:
            raise IngestionIntegrityError("invalid v2 import manifest") from exc
        expected_files = {MANIFEST_PATH, *(item.path for item in manifest.files)}
        snapshot = _scan_closed_tree(
            descriptor,
            expected_files=expected_files,
            configuration=False,
        )
        for path, (_, identity) in initial.items():
            if snapshot.files.get(path) != identity:
                raise IngestionIntegrityError("stored package changed during validation")

        files = {path: value[0] for path, value in initial.items()}
        for path in expected_files - set(files):
            _relative_path(path, label="import package path")
            files[path] = _read_regular_at(
                descriptor,
                path,
                configuration=False,
                label="import package file",
                snapshot=snapshot,
            )[0]
        if (
            _scan_closed_tree(
                descriptor,
                expected_files=expected_files,
                configuration=False,
            )
            != snapshot
        ):
            raise IngestionIntegrityError("stored package changed during file reads")
        return files
    finally:
        os.close(descriptor)


def _loaded_files(loaded: LoadedImportPackageV2) -> dict[str, bytes]:
    files = {
        RAW_BUNDLE_PATH: loaded.raw_bundle_bytes,
        CANONICAL_BUNDLE_PATH: loaded.canonical_bundle_bytes,
        RECEIPT_PATH: loaded.receipt_bytes,
        MANIFEST_PATH: loaded.manifest_bytes,
    }
    for artifact in loaded.receipt.artifacts:
        files[artifact.package_path] = loaded.artifact_bytes[artifact.artifact_id]
    return files


def _decode_import_package_v2_content(
    files: Mapping[str, bytes],
) -> LoadedImportPackageV2:
    try:
        raw_bundle = files[RAW_BUNDLE_PATH]
        raw_receipt = files[RECEIPT_PATH]
        raw_manifest = files[MANIFEST_PATH]
    except KeyError as exc:
        raise IngestionIntegrityError("import package is missing a required contract file") from exc

    try:
        manifest = decode_contract(raw_manifest, ImportManifestV2)
    except ContractError as exc:
        raise IngestionIntegrityError("invalid v2 import manifest") from exc
    expected_files = {MANIFEST_PATH, *(item.path for item in manifest.files)}
    if set(files) != expected_files:
        raise IngestionIntegrityError("import package file set does not match its manifest")
    for item in manifest.files:
        try:
            payload = files[item.path]
        except KeyError as exc:
            raise IngestionIntegrityError("import package manifest names a missing file") from exc
        if len(payload) != item.size_bytes or _sha256(payload) != item.sha256:
            raise IngestionIntegrityError("import package file digest mismatch")

    try:
        bundle = decode_evidence_bundle_v2(raw_bundle)
        receipt = decode_contract(raw_receipt, ImportReceiptV2)
    except ContractError as exc:
        raise IngestionIntegrityError("invalid v2 import package contract") from exc
    canonical_bundle = files.get(CANONICAL_BUNDLE_PATH)
    if canonical_bundle != canonical_evidence_bundle_v2(bundle):
        raise IngestionIntegrityError("canonical Bundle does not match the raw Bundle")
    try:
        artifact_bytes = {
            artifact.artifact_id: files[artifact.package_path] for artifact in receipt.artifacts
        }
        verify_artifact_payloads_v2(bundle, artifact_bytes)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid imported v2 artifact bytes") from exc

    expected_receipt, expected_manifest, expected_package = _package_files(
        bundle,
        raw_bundle,
        artifact_bytes,
    )
    if receipt != expected_receipt or manifest != expected_manifest or files != expected_package:
        raise IngestionIntegrityError("v2 import package is not canonical")
    return LoadedImportPackageV2(
        bundle=bundle,
        raw_bundle_bytes=raw_bundle,
        canonical_bundle_bytes=canonical_bundle,
        receipt=receipt,
        receipt_bytes=raw_receipt,
        manifest=manifest,
        manifest_bytes=raw_manifest,
        artifact_bytes=artifact_bytes,
    )


def read_import_package_v2_content(root: Path) -> LoadedImportPackageV2:
    """Verify stored package bytes without consulting current Profile authority."""

    return _decode_import_package_v2_content(_read_package_files(root))


def bind_import_package_v2_authority(
    loaded_package: LoadedImportPackageV2,
    authority: CaseProfile,
) -> AuthorityBoundImportPackageV2:
    """Bind already-owned package bytes to current explicit Profile authority."""

    bundle = loaded_package.bundle
    try:
        bind_evidence_bundle_v2(bundle, authority)
        case = next(item for item in authority.cases if item.case_id == bundle.case.case_id)
    except AuthorityIncompatibleError:
        raise
    except (ContractError, IngestionConfigurationError, StopIteration, ValueError) as exc:
        raise AuthorityIncompatibleError(
            "imported EvidenceBundle is incompatible with current Profile authority"
        ) from exc
    return AuthorityBoundImportPackageV2(
        content=loaded_package,
        profile=authority,
        case=case,
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


def _prepare_output_location(
    requested: Path,
    *,
    expected_resolved: Path,
    source_root: Path,
) -> OutputLocation:
    try:
        current_resolved = requested.resolve(strict=False)
    except OSError as exc:
        raise IngestionConfigurationError("cannot resolve import output") from exc
    if current_resolved != expected_resolved:
        raise IngestionConfigurationError("import output changed during validation")
    if _paths_overlap(current_resolved, source_root):
        raise IngestionConfigurationError("bundle source and import output must not overlap")
    if not current_resolved.name:
        raise IngestionConfigurationError("import output must name a directory")

    try:
        current_resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IngestionConfigurationError("cannot create import output parent") from exc
    try:
        after_create = requested.resolve(strict=False)
    except OSError as exc:
        raise IngestionConfigurationError("cannot resolve import output") from exc
    if after_create != current_resolved:
        raise IngestionConfigurationError("import output changed during validation")

    parent_descriptor = _open_directory(
        current_resolved.parent,
        configuration=True,
        label="import output parent",
    )
    info = os.fstat(parent_descriptor)
    return OutputLocation(
        requested=requested,
        resolved=current_resolved,
        parent_descriptor=parent_descriptor,
        parent_identity=(info.st_dev, info.st_ino),
    )


def _verify_output_location(location: OutputLocation, source_root: Path) -> None:
    try:
        current_resolved = location.requested.resolve(strict=False)
    except OSError as exc:
        raise IngestionConfigurationError("cannot resolve import output") from exc
    if current_resolved != location.resolved or _paths_overlap(current_resolved, source_root):
        raise IngestionConfigurationError("import output changed during validation")

    current_parent = _open_directory(
        location.resolved.parent,
        configuration=True,
        label="import output parent",
    )
    try:
        info = os.fstat(current_parent)
        if (info.st_dev, info.st_ino) != location.parent_identity:
            raise IngestionConfigurationError("import output parent changed during validation")
    finally:
        os.close(current_parent)


def _entry_info_at(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IngestionConfigurationError("cannot inspect import output") from exc


def _empty_directory_identity_at(
    parent_descriptor: int,
    name: str,
) -> FileIdentity | None:
    info = _entry_info_at(parent_descriptor, name)
    if info is None or not stat.S_ISDIR(info.st_mode):
        return None
    descriptor = _open_directory_at(
        parent_descriptor,
        name,
        configuration=True,
        label="import output",
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if identity != (info.st_dev, info.st_ino):
            raise IngestionConfigurationError("import output changed during validation")
        with os.scandir(descriptor) as entries:
            if next(entries, None) is not None:
                return None
        return identity
    finally:
        os.close(descriptor)


def _create_staging_directory(location: OutputLocation) -> tuple[str, int]:
    for _ in range(100):
        name = f".{location.resolved.name}.staging-{secrets.token_hex(8)}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=location.parent_descriptor)
        except FileExistsError:
            continue
        except OSError as exc:
            raise IngestionConfigurationError("cannot create output staging directory") from exc
        return (
            name,
            _open_directory_at(
                location.parent_descriptor,
                name,
                configuration=True,
                label="output staging directory",
            ),
        )
    raise IngestionConfigurationError("cannot allocate output staging directory")


def _write_package_file(root_descriptor: int, relative: str, payload: bytes) -> None:
    path = _relative_path(relative, label="import package path")
    current = os.dup(root_descriptor)
    file_descriptor = -1
    try:
        for part in path.parts[:-1]:
            with suppress(FileExistsError):
                os.mkdir(part, mode=0o700, dir_fd=current)
            next_descriptor = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            os.close(current)
            current = next_descriptor
        file_descriptor = os.open(
            path.parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=current,
        )
        with os.fdopen(file_descriptor, "wb", closefd=True) as stream:
            file_descriptor = -1
            stream.write(payload)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        os.close(current)


def _remove_tree_at(parent_descriptor: int, name: str) -> None:
    descriptor = _open_directory_at(
        parent_descriptor,
        name,
        configuration=True,
        label="output staging directory",
    )
    try:
        with os.scandir(descriptor) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    _remove_tree_at(descriptor, entry.name)
                else:
                    os.unlink(entry.name, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_descriptor)


def _publish(
    location: OutputLocation,
    source_root: Path,
    files: Mapping[str, bytes],
    *,
    replace_empty: bool,
    expected_empty_identity: FileIdentity | None = None,
) -> None:
    staging_name = ""
    staging_descriptor = -1
    published = False
    try:
        staging_name, staging_descriptor = _create_staging_directory(location)
        for relative, payload in sorted(files.items()):
            _write_package_file(staging_descriptor, relative, payload)
        os.close(staging_descriptor)
        staging_descriptor = -1

        _verify_output_location(location, source_root)
        if replace_empty:
            if (
                expected_empty_identity is None
                or _empty_directory_identity_at(
                    location.parent_descriptor,
                    location.resolved.name,
                )
                != expected_empty_identity
            ):
                raise IngestionConfigurationError(
                    "existing output changed before atomic publication"
                )
        elif _entry_info_at(location.parent_descriptor, location.resolved.name) is not None:
            raise IngestionConfigurationError("output appeared before atomic publication")
        os.replace(
            staging_name,
            location.resolved.name,
            src_dir_fd=location.parent_descriptor,
            dst_dir_fd=location.parent_descriptor,
        )
        published = True
    except IngestionConfigurationError:
        raise
    except OSError as exc:
        raise IngestionConfigurationError("cannot atomically publish import package") from exc
    finally:
        if staging_descriptor >= 0:
            os.close(staging_descriptor)
        if staging_name and not published:
            with suppress(IngestionConfigurationError, FileNotFoundError, OSError):
                _remove_tree_at(location.parent_descriptor, staging_name)


def import_evidence_bundle_v2(
    *,
    profile: Profile,
    bundle_path: Path,
    output: Path,
) -> ImportReceiptV2:
    """Validate one local EvidenceBundle v2 and atomically publish its package."""

    try:
        source_root = bundle_path.parent.resolve(strict=True)
        expected_output = output.resolve(strict=False)
    except OSError as exc:
        raise IngestionConfigurationError("cannot resolve import paths") from exc
    if _paths_overlap(expected_output, source_root):
        raise IngestionConfigurationError("bundle source and import output must not overlap")
    source_descriptor = _open_directory(
        bundle_path.parent,
        configuration=True,
        label="bundle source directory",
    )
    try:
        bound_source = os.stat(source_root)
        opened_source = os.fstat(source_descriptor)
        if (opened_source.st_dev, opened_source.st_ino) != (
            bound_source.st_dev,
            bound_source.st_ino,
        ):
            raise IngestionConfigurationError("bundle source directory changed during validation")
        raw, raw_identity = _read_regular_at(
            source_descriptor,
            bundle_path.name,
            configuration=True,
            label="bundle file",
        )
        try:
            bundle = decode_evidence_bundle_v2(raw)
        except ContractError as exc:
            raise IngestionIntegrityError("invalid EvidenceBundle v2") from exc
        if bundle.profile.profile_id != profile.authority.profile_id:
            raise IngestionConfigurationError(
                "supplied Profile does not match the EvidenceBundle profile identity"
            )
        try:
            artifact_bytes = _source_artifact_payloads(
                source_descriptor,
                bundle_path.name,
                bundle,
                raw_identity,
            )
            verify_artifact_payloads_v2(bundle, artifact_bytes)
        except ContractError as exc:
            raise IngestionIntegrityError("invalid EvidenceBundle v2 artifact bytes") from exc
    finally:
        os.close(source_descriptor)

    provisional_receipt, provisional_manifest, _ = _package_files(
        bundle,
        raw,
        artifact_bytes,
    )
    provisional = LoadedImportPackageV2(
        bundle=bundle,
        raw_bundle_bytes=raw,
        canonical_bundle_bytes=canonical_evidence_bundle_v2(bundle),
        receipt=provisional_receipt,
        receipt_bytes=canonical_json(provisional_receipt),
        manifest=provisional_manifest,
        manifest_bytes=canonical_json(provisional_manifest),
        artifact_bytes=artifact_bytes,
    )
    bound = bind_import_package_v2_authority(provisional, profile.authority)
    profile.validate_import(bound)
    receipt, _, files = _package_files(bundle, raw, artifact_bytes)
    location = _prepare_output_location(
        output,
        expected_resolved=expected_output,
        source_root=source_root,
    )
    try:
        output_info = _entry_info_at(
            location.parent_descriptor,
            location.resolved.name,
        )
        if output_info is not None:
            empty_identity = _empty_directory_identity_at(
                location.parent_descriptor,
                location.resolved.name,
            )
            if empty_identity is not None:
                _publish(
                    location,
                    source_root,
                    files,
                    replace_empty=True,
                    expected_empty_identity=empty_identity,
                )
                return receipt
            _verify_output_location(location, source_root)
            output_descriptor = _open_directory_at(
                location.parent_descriptor,
                location.resolved.name,
                configuration=False,
                label="import package root",
            )
            try:
                existing = _decode_import_package_v2_content(
                    _read_package_files(root_descriptor=output_descriptor)
                )
            finally:
                os.close(output_descriptor)
            profile.validate_import(bind_import_package_v2_authority(existing, profile.authority))
            if _loaded_files(existing) == files:
                _verify_output_location(location, source_root)
                return existing.receipt
            raise IngestionConfigurationError(
                "output contains a conflicting valid v2 import package"
            )

        _publish(
            location,
            source_root,
            files,
            replace_empty=False,
        )
        return receipt
    finally:
        os.close(location.parent_descriptor)


__all__ = [
    "bind_import_package_v2_authority",
    "import_evidence_bundle_v2",
    "read_import_package_v2_content",
]
