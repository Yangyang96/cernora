"""Persist and strictly reload one deterministic imported case evaluation."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from cernora.core.canonical import canonical_json, decode_contract
from cernora.core.errors import ContractError
from cernora.core.evidence import Evidence
from cernora.core.gate import GateDecision
from cernora.core.identity import ExternalProducerIdentity
from cernora.core.score import Score
from cernora.evaluation.contracts import (
    ImportedEvaluationAuthority,
    ImportedEvaluationFileDigest,
    ImportedEvaluationManifest,
    ImportedEvaluationReceipt,
)
from cernora.evaluation.imported_case import evaluate_imported_case_v2
from cernora.ingestion.contracts_v2 import LoadedImportPackageV2
from cernora.ingestion.errors import (
    IngestionConfigurationError,
    IngestionIntegrityError,
)
from cernora.ingestion.package_v2 import read_import_package_v2_content
from cernora.profile import Profile

AUTHORITY_PATH = "evaluation-authority.json"
EVIDENCE_PATH = "evidence.json"
SCORE_PATH = "score.json"
DECISION_PATH = "case-decision.json"
RECEIPT_PATH = "evaluation-receipt.json"
MANIFEST_PATH = "digests.json"
SOURCE_PREFIX = "source-import"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_files(loaded: LoadedImportPackageV2) -> dict[str, bytes]:
    files = {
        "bundle.raw.json": loaded.raw_bundle_bytes,
        "bundle.canonical.json": loaded.canonical_bundle_bytes,
        "import-receipt.json": loaded.receipt_bytes,
        "digests.json": loaded.manifest_bytes,
    }
    for artifact in loaded.receipt.artifacts:
        files[artifact.package_path] = loaded.artifact_bytes[artifact.artifact_id]
    return files


def _manifest(files: Mapping[str, bytes]) -> ImportedEvaluationManifest:
    return ImportedEvaluationManifest(
        schema_version="agent.evaluator.imported-evaluation-manifest/v1",
        files=tuple(
            ImportedEvaluationFileDigest(
                path=path,
                size_bytes=len(payload),
                sha256=_sha256(payload),
            )
            for path, payload in sorted(files.items())
        ),
    )


def _evaluation_input_sha256(
    authority: ImportedEvaluationAuthority,
    source_receipt_sha256: str,
) -> str:
    return _sha256(
        canonical_json(
            {
                "authority_sha256": authority.authority_sha256,
                "source_receipt_sha256": source_receipt_sha256,
            }
        )
    )


def _build_package(
    import_root: Path,
    profile: Profile,
) -> tuple[ImportedEvaluationReceipt, dict[str, bytes]]:
    first_source = read_import_package_v2_content(import_root)
    evaluation = evaluate_imported_case_v2(import_root, profile)
    second_source = read_import_package_v2_content(import_root)
    if _source_files(first_source) != _source_files(second_source):
        raise IngestionIntegrityError("source import changed during evaluation")

    source_receipt_sha256 = _sha256(second_source.receipt_bytes)
    evaluation_input_sha256 = _evaluation_input_sha256(
        evaluation.authority,
        source_receipt_sha256,
    )
    evidence = evaluation.evidence
    score = evaluation.score
    decision = evaluation.decision
    if not isinstance(evidence.producer, ExternalProducerIdentity):
        raise IngestionIntegrityError("imported evaluation requires an external producer")
    if (
        decision.scorer_identities != (evaluation.authority.scorer,)
        or decision.policy_identity != evaluation.authority.case_gate
    ):
        raise IngestionIntegrityError("imported case decision does not match authority")

    receipt = ImportedEvaluationReceipt(
        schema_version="agent.evaluator.imported-evaluation-receipt/v1",
        status="evaluated",
        scope="single_case_attempt",
        case_outcome=decision.decision,
        eligible=decision.eligible,
        profile_gate_status="not_evaluated",
        harness_status="not_evaluated",
        evaluation_id=evidence.evaluation_id,
        evidence_id=evidence.evidence_id,
        score_id=score.score_id,
        decision_id=decision.decision_id,
        evaluation_input_sha256=evaluation_input_sha256,
        authority=evaluation.authority,
        authority_sha256=evaluation.authority.authority_sha256,
        bundle=second_source.receipt.bundle,
        producer=evidence.producer,
        run=second_source.receipt.run,
        profile=second_source.receipt.profile,
        case=second_source.receipt.case,
        fixtures=evaluation.authority.fixtures,
        source_receipt_sha256=source_receipt_sha256,
        source_manifest_sha256=_sha256(second_source.manifest_bytes),
        declared_bundle_sha256=second_source.receipt.bundle.declared_sha256,
        canonical_bundle_sha256=second_source.receipt.canonical_bundle_sha256,
        raw_input_sha256=second_source.receipt.raw_input_sha256,
        scorer=evaluation.authority.scorer,
        case_gate=evaluation.authority.case_gate,
    )
    files = {
        f"{SOURCE_PREFIX}/{path}": payload for path, payload in _source_files(second_source).items()
    }
    files.update(
        {
            AUTHORITY_PATH: canonical_json(evaluation.authority),
            EVIDENCE_PATH: canonical_json(evidence),
            SCORE_PATH: canonical_json(score),
            DECISION_PATH: canonical_json(decision),
            RECEIPT_PATH: canonical_json(receipt),
        }
    )
    files[MANIFEST_PATH] = canonical_json(_manifest(files))
    return receipt, files


def _ordinary_tree_files(root: Path) -> dict[str, bytes]:
    try:
        root_mode = root.lstat().st_mode
    except OSError as exc:
        raise IngestionIntegrityError("cannot inspect evaluation package") from exc
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise IngestionIntegrityError("evaluation package is not an ordinary directory")

    files: dict[str, bytes] = {}
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory_name in directory_names:
            candidate = current_path / directory_name
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise IngestionIntegrityError("cannot inspect evaluation directory") from exc
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise IngestionIntegrityError("evaluation tree contains a non-ordinary directory")
        for file_name in file_names:
            candidate = current_path / file_name
            relative = candidate.relative_to(root).as_posix()
            try:
                mode = candidate.lstat().st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                    raise IngestionIntegrityError("evaluation tree contains a non-ordinary file")
                files[relative] = candidate.read_bytes()
            except IngestionIntegrityError:
                raise
            except OSError as exc:
                raise IngestionIntegrityError("cannot read evaluation package file") from exc
    return files


def _decode_stored_package(
    root: Path,
    files: Mapping[str, bytes],
    profile: Profile,
) -> ImportedEvaluationReceipt:
    try:
        manifest = decode_contract(files[MANIFEST_PATH], ImportedEvaluationManifest)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid imported evaluation manifest") from exc
    expected_paths = {MANIFEST_PATH, *(item.path for item in manifest.files)}
    if set(files) != expected_paths:
        raise IngestionIntegrityError("evaluation package file set does not match its manifest")
    for item in manifest.files:
        payload = files[item.path]
        if len(payload) != item.size_bytes or _sha256(payload) != item.sha256:
            raise IngestionIntegrityError("evaluation package file digest mismatch")

    try:
        authority = decode_contract(files[AUTHORITY_PATH], ImportedEvaluationAuthority)
        evidence = decode_contract(files[EVIDENCE_PATH], Evidence)
        score = decode_contract(files[SCORE_PATH], Score)
        decision = decode_contract(files[DECISION_PATH], GateDecision)
        receipt = decode_contract(files[RECEIPT_PATH], ImportedEvaluationReceipt)
    except (KeyError, ContractError) as exc:
        raise IngestionIntegrityError("invalid imported evaluation contract") from exc
    if receipt.authority != authority:
        raise IngestionIntegrityError(
            "evaluation receipt authority does not match stored authority"
        )
    if (
        receipt.evaluation_id != evidence.evaluation_id
        or receipt.evidence_id != evidence.evidence_id
        or receipt.score_id != score.score_id
        or receipt.decision_id != decision.decision_id
        or receipt.case_outcome != decision.decision
        or receipt.eligible != decision.eligible
    ):
        raise IngestionIntegrityError("evaluation receipt does not bind stored results")

    expected_receipt, expected_files = _build_package(root / SOURCE_PREFIX, profile)
    if receipt != expected_receipt or dict(files) != expected_files:
        raise IngestionIntegrityError("stored imported evaluation is not canonical")
    return receipt


def read_imported_evaluation(root: Path, profile: Profile) -> ImportedEvaluationReceipt:
    """Strictly reload and recompute one persisted imported evaluation."""

    files = _ordinary_tree_files(root)
    return _decode_stored_package(root, files, profile)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


def _resolve_paths(import_root: Path, output: Path) -> tuple[Path, Path]:
    try:
        output_mode = output.lstat().st_mode
    except FileNotFoundError:
        output_mode = None
    except OSError as exc:
        raise IngestionConfigurationError("cannot inspect evaluation output") from exc
    if output_mode is not None and stat.S_ISLNK(output_mode):
        raise IngestionConfigurationError("evaluation output cannot be a symlink")
    try:
        source = import_root.resolve(strict=True)
        destination = output.resolve(strict=False)
    except OSError as exc:
        raise IngestionConfigurationError("cannot resolve evaluation paths") from exc
    try:
        source_mode = import_root.lstat().st_mode
    except OSError as exc:
        raise IngestionConfigurationError("cannot inspect import root") from exc
    if stat.S_ISLNK(source_mode) or not stat.S_ISDIR(source_mode):
        raise IngestionConfigurationError("import root must be an ordinary directory")
    if not destination.name:
        raise IngestionConfigurationError("evaluation output must name a directory")
    if _paths_overlap(source, destination):
        raise IngestionConfigurationError("import root and evaluation output must not overlap")
    return source, destination


def _is_empty_directory(path: Path) -> tuple[bool, tuple[int, int] | None]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False, None
    except OSError as exc:
        raise IngestionConfigurationError("cannot inspect evaluation output") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return False, None
    try:
        is_empty = next(path.iterdir(), None) is None
    except OSError as exc:
        raise IngestionConfigurationError("cannot inspect evaluation output") from exc
    return is_empty, (info.st_dev, info.st_ino)


def _publish(
    output: Path,
    files: Mapping[str, bytes],
    *,
    replace_empty_identity: tuple[int, int] | None,
) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{output.name}.staging-",
                dir=output.parent,
            )
        )
    except OSError as exc:
        raise IngestionConfigurationError("cannot create evaluation staging directory") from exc
    published = False
    try:
        for relative, payload in sorted(files.items()):
            destination = staging.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)

        if replace_empty_identity is None:
            if output.exists() or output.is_symlink():
                raise IngestionConfigurationError("evaluation output appeared before publication")
        else:
            empty, identity = _is_empty_directory(output)
            if not empty or identity != replace_empty_identity:
                raise IngestionConfigurationError(
                    "existing evaluation output changed before publication"
                )
        os.replace(staging, output)
        published = True
    except IngestionConfigurationError:
        raise
    except OSError as exc:
        raise IngestionConfigurationError("cannot atomically publish evaluation package") from exc
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)


def evaluate_imported_case(
    profile: Profile,
    import_root: Path,
    output: Path,
) -> ImportedEvaluationReceipt:
    """Evaluate, persist, and strictly reload one canonical v2 import package."""

    source, destination = _resolve_paths(import_root, output)
    _, files = _build_package(source, profile)
    empty, empty_identity = _is_empty_directory(destination)
    if destination.exists() or destination.is_symlink():
        if empty:
            _publish(
                destination,
                files,
                replace_empty_identity=empty_identity,
            )
            return read_imported_evaluation(destination, profile)
        if not destination.is_dir() or destination.is_symlink():
            raise IngestionConfigurationError(
                "evaluation output is not an empty directory or valid package"
            )
        markers = (destination / MANIFEST_PATH, destination / RECEIPT_PATH)
        if not all(path.exists() or path.is_symlink() for path in markers):
            raise IngestionConfigurationError(
                "evaluation output contains unrelated non-empty content"
            )
        existing = read_imported_evaluation(destination, profile)
        if _ordinary_tree_files(destination) == files:
            return existing
        raise IngestionConfigurationError("evaluation output contains a conflicting valid package")

    _publish(destination, files, replace_empty_identity=None)
    return read_imported_evaluation(destination, profile)


__all__ = ["evaluate_imported_case", "read_imported_evaluation"]
