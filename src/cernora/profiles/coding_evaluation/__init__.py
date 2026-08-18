"""Deterministic coding-evaluation Profile."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from importlib import resources
from pathlib import PurePosixPath
from typing import Any, Literal

from cernora.core.canonical import canonical_json
from cernora.core.case import CaseProfile
from cernora.core.evidence import Artifact, Evidence, EvidenceReference, Failure, ToolAction
from cernora.core.identity import external_producer_identity
from cernora.core.result import ResultRecord, ResultValidity
from cernora.core.score import Score, ScoreObservation
from cernora.ingestion.contracts_v2 import AuthorityBoundImportPackageV2
from cernora.profile import ProfileAssessment, ProfileEvaluationContext

_PROFILE_RESOURCE = "resources/profile.json"
_AUTHORITY_RESOURCE = "resources/authority-v1.json"
_ORACLE_RESOURCE = "resources/oracle-v1.json"
_PROJECTION_VERSION = "cernora.coding-evaluation-projection/v1"
_TREE_VERSION = "cernora.candidate-tree/v1"
_TREE_DOMAIN = "cernora.candidate-tree-manifest/v1"
_CAPSULE_VERSION = "cernora.synthetic-execution-capsule/v1"
_TERMINAL_VERSION = "cernora.coding-terminal-binding/v1"
_REQUIRED_RESULT_IDS = ("task_outcome", "policy_compliance")

_RESULT_SHAPES: tuple[
    tuple[
        str,
        Literal["outcome", "constraint", "advisory", "diagnostic"],
        Literal["boolean", "integer", "number", "string"],
        str | None,
        Literal["higher_is_better", "lower_is_better", "neutral"] | None,
    ],
    ...,
] = (
    ("task_outcome", "outcome", "boolean", None, None),
    ("policy_compliance", "constraint", "boolean", None, None),
    ("resolution_test_rate", "diagnostic", "number", "ratio", "higher_is_better"),
    ("regression_test_rate", "diagnostic", "number", "ratio", "higher_is_better"),
    ("resolution_tests_passed", "diagnostic", "integer", "count", "higher_is_better"),
    ("resolution_tests_total", "diagnostic", "integer", "count", "neutral"),
    ("regression_tests_passed", "diagnostic", "integer", "count", "higher_is_better"),
    ("regression_tests_total", "diagnostic", "integer", "count", "neutral"),
    ("build_succeeded", "diagnostic", "boolean", None, None),
    ("candidate_binding", "diagnostic", "boolean", None, None),
    ("terminal_binding", "diagnostic", "boolean", None, None),
    ("diff_scope_compliant", "diagnostic", "boolean", None, None),
    ("protected_test_tamper", "diagnostic", "boolean", None, None),
    ("forbidden_file_change", "diagnostic", "boolean", None, None),
    ("candidate_self_mutation", "diagnostic", "boolean", None, None),
    ("retry_policy_compliance", "diagnostic", "boolean", None, None),
)


@dataclass(frozen=True)
class _Analysis:
    values: dict[str, bool | int | float]
    reference: EvidenceReference
    changed_paths: tuple[str, ...]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_object(payload: bytes, *, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member in {label}: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number in {label}: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def _canonical_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return (
        bool(path)
        and not path.startswith("/")
        and "\\" not in path
        and not any(ord(character) < 32 or ord(character) == 127 for character in path)
        and bool(parsed.parts)
        and all(part not in {"", ".", ".."} for part in path.split("/"))
        and parsed.as_posix() == path
        and unicodedata.normalize("NFC", path) == path
    )


def validate_candidate_tree(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    """Validate and return one canonical, closed UTF-8 Candidate Tree v1."""

    if set(value) != {"schema_version", "entries", "tree_sha256"}:
        raise ValueError(f"{label} has an invalid member set")
    if value["schema_version"] != _TREE_VERSION or type(value["entries"]) is not list:
        raise ValueError(f"{label} has an invalid version or entries")
    entries = value["entries"]
    if not entries:
        raise ValueError(f"{label} must contain at least one file")
    paths: list[str] = []
    manifest_entries: list[dict[str, Any]] = []
    for entry in entries:
        if type(entry) is not dict or set(entry) != {
            "path",
            "size_bytes",
            "sha256",
            "executable",
            "content",
        }:
            raise ValueError(f"{label} entry has an invalid member set")
        path = entry["path"]
        if type(path) is not str or not _canonical_path(path):
            raise ValueError(f"{label} entry path is not canonical")
        if type(entry["content"]) is not str or type(entry["executable"]) is not bool:
            raise ValueError(f"{label} entry content or executable flag is invalid")
        try:
            content = entry["content"].encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{label} entry content is not strict UTF-8") from exc
        if (
            type(entry["size_bytes"]) is not int
            or entry["size_bytes"] != len(content)
            or type(entry["sha256"]) is not str
            or entry["sha256"] != _sha256(content)
        ):
            raise ValueError(f"{label} entry content binding is invalid")
        paths.append(path)
        manifest_entries.append(
            {
                "path": path,
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "executable": entry["executable"],
            }
        )
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError(f"{label} paths must be sorted and unique")
    if any(
        right.startswith(f"{left}/")
        for index, left in enumerate(paths)
        for right in paths[index + 1 :]
    ):
        raise ValueError(f"{label} has a file/directory prefix collision")
    folded = [unicodedata.normalize("NFC", path).casefold() for path in paths]
    if len(folded) != len(set(folded)):
        raise ValueError(f"{label} paths have a normalization or case-fold collision")
    expected = _sha256(canonical_json({"domain": _TREE_DOMAIN, "entries": manifest_entries}))
    if value["tree_sha256"] != expected:
        raise ValueError(f"{label} domain-separated tree digest is invalid")
    return value


def _load_authority() -> dict[str, Any]:
    package = resources.files(__package__)
    value = _strict_object(package.joinpath(_AUTHORITY_RESOURCE).read_bytes(), label="authority")
    expected = {
        "schema_version",
        "baseline_tree",
        "test_plan",
        "harness",
        "execution",
        "change_policy",
    }
    if set(value) != expected or value["schema_version"] != (
        "cernora.coding-evaluation-authority/v1"
    ):
        raise ValueError("coding evaluation authority has an invalid member set or version")
    validate_candidate_tree(value["baseline_tree"], label="baseline tree")
    plan = value["test_plan"]
    if type(plan) is not dict or set(plan) != {"schema_version", "test_plan_id", "tests"}:
        raise ValueError("coding test plan has an invalid member set")
    tests = plan["tests"]
    expected_tests = [
        ("f2p-add-positive", "fail_to_pass"),
        ("f2p-add-negative", "fail_to_pass"),
        ("p2p-import-module", "pass_to_pass"),
        ("p2p-type-contract", "pass_to_pass"),
    ]
    if (
        type(tests) is not list
        or [
            (item.get("test_id"), item.get("classification")) if type(item) is dict else None
            for item in tests
        ]
        != expected_tests
    ):
        raise ValueError("coding test plan is not the frozen non-empty F2P/P2P set")
    return value


def _resource_digest(value: object) -> str:
    return _sha256(canonical_json(value))


def _artifact_by_id(package: AuthorityBoundImportPackageV2, artifact_id: str) -> bytes:
    try:
        return package.content.artifact_bytes[artifact_id]
    except KeyError as exc:
        raise ValueError(f"coding bundle is missing artifact {artifact_id}") from exc


class CodingEvaluationProfile:
    """Assess a Profile-owned synthetic coding capsule without running candidate code."""

    def __init__(self) -> None:
        package = resources.files(__package__)
        profile_bytes = package.joinpath(_PROFILE_RESOURCE).read_bytes()
        authority_bytes = package.joinpath(_AUTHORITY_RESOURCE).read_bytes()
        self._authority = CaseProfile.model_validate_json(profile_bytes)
        if (self._authority.profile_id, self._authority.profile_version) != (
            "cernora-coding-evaluation-v1",
            "1.0.0",
        ):
            raise ValueError("coding evaluation Profile identity is not frozen")
        if self._authority.scorer_policy.required_observations != _REQUIRED_RESULT_IDS:
            raise ValueError("coding evaluation Required observations are not frozen")
        if len(self._authority.cases) != 1:
            raise ValueError("coding evaluation requires exactly one frozen Case")
        fixtures = self._authority.cases[0].fixture_references
        oracle_bytes = package.joinpath(_ORACLE_RESOURCE).read_bytes()
        expected_fixtures = (
            (_AUTHORITY_RESOURCE, _sha256(authority_bytes)),
            (_ORACLE_RESOURCE, _sha256(oracle_bytes)),
        )
        if tuple((item.path, item.sha256) for item in fixtures) != expected_fixtures:
            raise ValueError("coding evaluation authority and oracle fixtures are not exact")
        self._spec = _load_authority()
        oracle = _strict_object(oracle_bytes, label="oracle")
        if set(oracle) != {
            "schema_version",
            "producer",
            "untrusted_producer",
            "rows",
        } or oracle["schema_version"] != ("cernora.coding-evaluation-oracle/v1"):
            raise ValueError("coding evaluation oracle has an invalid member set or version")
        if oracle["producer"] != {
            "producer_id": "cernora.synthetic.coding-evaluation",
            "producer_version": "1.0.0",
        }:
            raise ValueError("coding evaluation oracle Producer is not frozen")
        if oracle["untrusted_producer"] != {
            "producer_id": "untrusted.synthetic.coding-evaluation",
            "producer_version": "1.0.0",
        }:
            raise ValueError("coding evaluation oracle untrusted Producer is not frozen")
        rows = oracle["rows"]
        if type(rows) is not list or not rows:
            raise ValueError("coding evaluation oracle must be non-empty")
        self._oracle = tuple(rows)

    @property
    def authority(self) -> CaseProfile:
        return self._authority

    @property
    def projection_version(self) -> str:
        return _PROJECTION_VERSION

    def _oracle_row(self, package: AuthorityBoundImportPackageV2) -> dict[str, Any]:
        bundle = package.content.bundle
        matches = [
            row
            for row in self._oracle
            if type(row) is dict and row.get("bundle_id") == bundle.bundle_id
        ]
        if len(matches) != 1:
            raise ValueError("bundle is not an exact Profile-owned synthetic oracle row")
        row = matches[0]
        if set(row) != {
            "row_id",
            "bundle_id",
            "candidate_sha256",
            "capsule_sha256",
            "terminal_sha256",
            "action_shape",
            "terminal_status",
            "infrastructure_status",
        }:
            raise ValueError("coding evaluation oracle row has an invalid member set")
        if (bundle.run.run_id, bundle.run.attempt_id) != (
            f"run-{row['row_id']}",
            "attempt-set-1",
        ):
            raise ValueError("bundle run identity changed frozen oracle")
        expected = [
            (
                "candidate-tree",
                "candidate/tree.json",
                row["candidate_sha256"],
                "application/json",
            ),
            (
                "candidate-tree-stderr",
                "candidate/stderr.txt",
                _sha256(b""),
                "text/plain; charset=utf-8",
            ),
        ]
        if row["capsule_sha256"] is not None:
            expected.extend(
                [
                    (
                        "execution-capsule",
                        "execution/capsule.json",
                        row["capsule_sha256"],
                        "application/json",
                    ),
                    (
                        "execution-capsule-stderr",
                        "execution/stderr.txt",
                        _sha256(b""),
                        "text/plain; charset=utf-8",
                    ),
                ]
            )
        if row["terminal_sha256"] is not None:
            expected.append(
                (
                    "terminal-binding",
                    "terminal/binding.json",
                    row["terminal_sha256"],
                    "application/json",
                )
            )
        actual = [
            (item.artifact_id, item.path, item.sha256, item.media_type) for item in bundle.artifacts
        ]
        if expected != actual:
            raise ValueError("bundle artifacts do not match the exact Profile-owned oracle row")
        if (
            bundle.terminal.status != row["terminal_status"]
            or bundle.infrastructure.status != row["infrastructure_status"]
        ):
            raise ValueError("bundle terminal or infrastructure shape changed frozen oracle")
        expected_actions: tuple[tuple[str, str, tuple[str, ...], str, str], ...] = (
            (
                "capture-candidate-tree",
                "capture_candidate_tree",
                ("capture_candidate_tree", "--frozen-synthetic-fixture"),
                "candidate-tree",
                "candidate-tree-stderr",
            ),
        )
        if row["action_shape"] == "candidate_and_capsule":
            expected_actions += (
                (
                    "observe-execution-capsule",
                    "observe_frozen_execution_capsule",
                    ("observe_frozen_execution_capsule", "--frozen-synthetic-fixture"),
                    "execution-capsule",
                    "execution-capsule-stderr",
                ),
            )
        actual_actions = tuple(
            (
                action.invocation_id,
                action.tool,
                action.argv,
                action.result.stdout_artifact.artifact_id,
                action.result.stderr_artifact.artifact_id,
            )
            for action in bundle.tool_actions
        )
        if actual_actions != expected_actions or any(
            action.result.status != "completed"
            or action.result.exit_code != 0
            or action.result.committed
            or not action.result.delivered
            for action in bundle.tool_actions
        ):
            raise ValueError("bundle action envelope changed frozen oracle")
        return row

    def validate_import(self, package: AuthorityBoundImportPackageV2) -> None:
        if package.profile != self._authority or package.case != self._authority.cases[0]:
            raise ValueError("import package is not bound to this coding evaluation authority")
        bundle = package.content.bundle
        row = self._oracle_row(package)
        expected_producer = (
            "untrusted.synthetic.coding-evaluation"
            if row["row_id"] == "untrusted-execution-authority"
            else "cernora.synthetic.coding-evaluation"
        )
        if (bundle.producer.producer_id, bundle.producer.producer_version) != (
            expected_producer,
            "1.0.0",
        ):
            raise ValueError("coding bundle Producer does not match the frozen synthetic identity")
        candidate = validate_candidate_tree(
            _strict_object(_artifact_by_id(package, "candidate-tree"), label="candidate tree"),
            label="candidate tree",
        )
        capsule_payload = package.content.artifact_bytes.get("execution-capsule")
        if capsule_payload is not None:
            capsule = self._validate_capsule(
                _strict_object(capsule_payload, label="execution capsule")
            )
            if row["row_id"].startswith("reject-wrong-"):
                self._reject_authority_binding(capsule)
        if bundle.terminal.status == "completed":
            answer = bundle.terminal.answer
            if answer is None:
                raise ValueError("completed coding bundle requires a terminal binding")
            terminal = _strict_object(answer.content.encode("utf-8"), label="terminal binding")
            self._validate_terminal(terminal)
        if row["row_id"].startswith("reject-") and not row["row_id"].startswith("reject-wrong-"):
            # Structural rejection rows must already have failed above.
            raise ValueError("malformed candidate tree unexpectedly passed validation")
        if candidate["tree_sha256"] == "":  # pragma: no cover - schema guard
            raise ValueError("candidate tree digest cannot be empty")

    def _validate_capsule(self, value: dict[str, Any]) -> dict[str, Any]:
        expected = {
            "schema_version",
            "authority_id",
            "candidate_tree_sha256",
            "baseline_tree_sha256",
            "test_plan_sha256",
            "harness_sha256",
            "toolchain",
            "platform",
            "command",
            "limits",
            "attempt_policy",
            "attempts",
        }
        if set(value) != expected or value["schema_version"] != _CAPSULE_VERSION:
            raise ValueError("execution capsule has an invalid member set or version")
        if type(value["attempts"]) is not list:
            raise ValueError("execution capsule attempts must be a list")
        for index, attempt in enumerate(value["attempts"], start=1):
            if type(attempt) is not dict or set(attempt) != {
                "attempt",
                "retry_reason",
                "pre_tree_sha256",
                "post_tree_sha256",
                "build",
                "test_results",
                "raw_output_sha256",
            }:
                raise ValueError("execution capsule attempt has an invalid member set")
            if attempt["attempt"] != index or type(attempt["test_results"]) is not list:
                raise ValueError("execution capsule attempts are not contiguous")
            build = attempt["build"]
            if type(build) is not dict or set(build) != {"status", "exit_code"}:
                raise ValueError("execution capsule build receipt is invalid")
            for result in attempt["test_results"]:
                if type(result) is not dict or set(result) != {
                    "test_id",
                    "classification",
                    "status",
                    "output_sha256",
                }:
                    raise ValueError("execution capsule test result is invalid")
        return value

    def _reject_authority_binding(self, capsule: dict[str, Any]) -> None:
        expected = {
            "baseline_tree_sha256": self._spec["baseline_tree"]["tree_sha256"],
            "test_plan_sha256": _resource_digest(self._spec["test_plan"]),
            "harness_sha256": _resource_digest(self._spec["harness"]),
        }
        if any(capsule[key] != digest for key, digest in expected.items()):
            raise ValueError("execution capsule authority binding is invalid")
        raise ValueError("authority rejection row unexpectedly has correct bindings")

    @staticmethod
    def _validate_terminal(value: dict[str, Any]) -> dict[str, Any]:
        if set(value) != {"schema_version", "candidate_tree_sha256", "capsule_sha256"}:
            raise ValueError("terminal binding has an invalid member set")
        if value["schema_version"] != _TERMINAL_VERSION:
            raise ValueError("terminal binding has an invalid version")
        return value

    def assess(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
    ) -> ProfileAssessment:
        self.validate_import(package)
        receipt_reference = EvidenceReference(
            evidence_id=context.evidence_id,
            locator="source-import/import-receipt.json",
            sha256=context.source_receipt_sha256,
        )
        bundle = package.content.bundle
        candidate = validate_candidate_tree(
            _strict_object(_artifact_by_id(package, "candidate-tree"), label="candidate tree"),
            label="candidate tree",
        )
        changed_paths = self._changed_paths(candidate)
        if bundle.terminal.status == "inconclusive":
            row = self._oracle_row(package)
            failure = bundle.terminal.failure
            if failure is None:
                raise ValueError("inconclusive coding bundle requires a failure")
            capsule_payload = package.content.artifact_bytes.get("execution-capsule")
            capsule = (
                self._validate_capsule(_strict_object(capsule_payload, label="execution capsule"))
                if capsule_payload is not None
                else None
            )
            validity, reason = self._classify_inconclusive(
                row["row_id"], candidate, capsule, bundle
            )
            if failure.code != reason:
                raise ValueError("terminal failure code does not match derived evidence condition")
            expected_domain = (
                "infrastructure" if reason == "infrastructure_unavailable" else ("evidence")
            )
            if (
                failure.domain != expected_domain
                or failure.message
                != "Frozen synthetic evidence cannot support an eligible coding conclusion."
            ):
                raise ValueError("terminal failure envelope changed frozen oracle")
            records = self._non_valid_records(validity, reason, receipt_reference)
            return self._assessment(package, context, records, changed_paths)

        capsule_payload = _artifact_by_id(package, "execution-capsule")
        capsule = self._validate_capsule(_strict_object(capsule_payload, label="execution capsule"))
        answer = bundle.terminal.answer
        if answer is None:  # pragma: no cover - EvidenceBundle v2 guard
            raise ValueError("completed coding bundle requires terminal answer")
        terminal = self._validate_terminal(
            _strict_object(answer.content.encode("utf-8"), label="terminal binding")
        )
        analysis = self._analyze(candidate, capsule, terminal, capsule_payload, receipt_reference)
        records = self._result_records(analysis)
        return self._assessment(package, context, records, analysis.changed_paths)

    def _classify_inconclusive(
        self,
        row_id: str,
        candidate: dict[str, Any],
        capsule: dict[str, Any] | None,
        bundle: Any,
    ) -> tuple[ResultValidity, str]:
        expected_tests = [item["test_id"] for item in self._spec["test_plan"]["tests"]]
        condition = False
        validity: ResultValidity = "unavailable"
        if row_id == "missing-execution-evidence":
            condition = capsule is None
        elif capsule is None:
            raise ValueError("inconclusive evidence condition requires a capsule")
        elif row_id == "untrusted-execution-authority":
            condition = (
                capsule["authority_id"] != "cernora.synthetic-execution-authority/v1"
                and bundle.producer.producer_id == "untrusted.synthetic.coding-evaluation"
            )
            validity = "invalid"
        elif row_id == "wrong-capsule-binding":
            condition = capsule["candidate_tree_sha256"] != candidate["tree_sha256"]
            validity = "invalid"
        elif row_id == "partial-test-results":
            results = capsule["attempts"][-1]["test_results"]
            condition = [item["test_id"] for item in results] != expected_tests and len(
                {item["test_id"] for item in results}
            ) == len(results)
        elif row_id == "duplicate-test-result":
            ids = [item["test_id"] for item in capsule["attempts"][-1]["test_results"]]
            condition = len(ids) != len(set(ids))
            validity = "invalid"
        elif row_id == "skipped-test":
            condition = any(
                item["status"] == "skipped" for item in capsule["attempts"][-1]["test_results"]
            )
        elif row_id == "xfailed-test":
            condition = any(
                item["status"] == "xfailed" for item in capsule["attempts"][-1]["test_results"]
            )
        elif row_id == "infrastructure-unavailable":
            condition = (
                bundle.infrastructure.status == "inconclusive"
                and capsule["attempts"][-1]["build"]["status"] == "infrastructure_unavailable"
            )
        elif row_id == "conflicting-attempts":
            attempts = capsule["attempts"]
            signatures = {
                canonical_json({"build": item["build"], "test_results": item["test_results"]})
                for item in attempts
            }
            condition = len(attempts) > 1 and len(signatures) > 1
            validity = "invalid"
        else:
            raise ValueError("unknown inconclusive oracle row")
        if not condition:
            raise ValueError("inconclusive row does not exhibit its derived evidence condition")
        return validity, row_id.replace("-", "_")

    def _changed_paths(self, candidate: dict[str, Any]) -> tuple[str, ...]:
        return tuple(sorted({item["path"] for item in self._derived_diff(candidate)}))

    def _derived_diff(self, candidate: dict[str, Any]) -> tuple[dict[str, str], ...]:
        """Derive add/delete/content/executable changes without rename inference."""

        baseline = {item["path"]: item for item in self._spec["baseline_tree"]["entries"]}
        current = {item["path"]: item for item in candidate["entries"]}
        changes: list[dict[str, str]] = []
        for path in sorted(baseline.keys() | current.keys()):
            if path not in baseline:
                changes.append({"path": path, "kind": "add"})
            elif path not in current:
                changes.append({"path": path, "kind": "delete"})
            else:
                if baseline[path]["sha256"] != current[path]["sha256"]:
                    changes.append({"path": path, "kind": "content"})
                if baseline[path]["executable"] != current[path]["executable"]:
                    changes.append({"path": path, "kind": "executable"})
        return tuple(changes)

    def _analyze(
        self,
        candidate: dict[str, Any],
        capsule: dict[str, Any],
        terminal: dict[str, Any],
        capsule_payload: bytes,
        reference: EvidenceReference,
    ) -> _Analysis:
        expected_authority = {
            "authority_id": "cernora.synthetic-execution-authority/v1",
            "baseline_tree_sha256": self._spec["baseline_tree"]["tree_sha256"],
            "test_plan_sha256": _resource_digest(self._spec["test_plan"]),
            "harness_sha256": _resource_digest(self._spec["harness"]),
            "toolchain": self._spec["execution"]["toolchain"],
            "platform": self._spec["execution"]["platform"],
            "command": self._spec["execution"]["command"],
            "limits": self._spec["execution"]["limits"],
            "attempt_policy": self._spec["execution"]["attempt_policy"],
        }
        if any(capsule[key] != value for key, value in expected_authority.items()):
            raise ValueError("completed capsule is not bound to frozen execution authority")
        candidate_sha = candidate["tree_sha256"]
        attempts = capsule["attempts"]
        if not attempts:
            raise ValueError("completed capsule requires an execution attempt")
        candidate_binding = capsule["candidate_tree_sha256"] == candidate_sha and all(
            attempt["pre_tree_sha256"] == candidate_sha for attempt in attempts
        )
        terminal_binding = terminal["candidate_tree_sha256"] == candidate_sha and terminal[
            "capsule_sha256"
        ] == _sha256(capsule_payload)
        final = attempts[-1]
        build_succeeded = final["build"] == {"status": "passed", "exit_code": 0}
        tests = self._spec["test_plan"]["tests"]
        results = final["test_results"]
        expected_ids = [item["test_id"] for item in tests]
        if [item["test_id"] for item in results] != expected_ids:
            raise ValueError("completed capsule test results are not exact and ordered")
        expected_classes = {item["test_id"]: item["classification"] for item in tests}
        if any(item["classification"] != expected_classes[item["test_id"]] for item in results):
            raise ValueError("completed capsule test classifications changed authority")
        statuses = {item["status"] for item in results}
        if build_succeeded and not statuses <= {"passed", "failed"}:
            raise ValueError("completed build has an unresolved test status")
        if not build_succeeded and statuses != {"not_run_build_failure"}:
            raise ValueError("failed build must bind every test as not run")
        f2p = [item for item in results if item["classification"] == "fail_to_pass"]
        p2p = [item for item in results if item["classification"] == "pass_to_pass"]
        f2p_passed = sum(item["status"] == "passed" for item in f2p)
        p2p_passed = sum(item["status"] == "passed" for item in p2p)
        changed_paths = self._changed_paths(candidate)
        policy = self._spec["change_policy"]

        def matches(path: str, patterns: list[str]) -> bool:
            return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)

        protected = any(matches(path, policy["protected_patterns"]) for path in changed_paths)
        explicit_forbidden = any(
            matches(path, policy["forbidden_patterns"]) for path in changed_paths
        )
        out_of_scope = any(not matches(path, policy["allowed_patterns"]) for path in changed_paths)
        forbidden = explicit_forbidden or out_of_scope
        self_mutation = any(attempt["post_tree_sha256"] != candidate_sha for attempt in attempts)
        retry_compliant = len(attempts) <= self._spec["execution"]["attempt_policy"][
            "max_attempts"
        ] and all(
            (index == 0 and attempt["retry_reason"] is None)
            or (
                index > 0
                and attempt["retry_reason"] == "infrastructure_unavailable"
                and attempts[index - 1]["build"]["status"] == "infrastructure_unavailable"
            )
            for index, attempt in enumerate(attempts)
        )
        values: dict[str, bool | int | float] = {
            "task_outcome": (
                build_succeeded
                and f2p_passed == len(f2p)
                and candidate_binding
                and terminal_binding
            ),
            "policy_compliance": (
                p2p_passed == len(p2p)
                and not protected
                and not forbidden
                and not self_mutation
                and retry_compliant
            ),
            "resolution_test_rate": f2p_passed / len(f2p),
            "regression_test_rate": p2p_passed / len(p2p),
            "resolution_tests_passed": f2p_passed,
            "resolution_tests_total": len(f2p),
            "regression_tests_passed": p2p_passed,
            "regression_tests_total": len(p2p),
            "build_succeeded": build_succeeded,
            "candidate_binding": candidate_binding,
            "terminal_binding": terminal_binding,
            "diff_scope_compliant": not forbidden and not protected,
            "protected_test_tamper": protected,
            "forbidden_file_change": forbidden,
            "candidate_self_mutation": self_mutation,
            "retry_policy_compliance": retry_compliant,
        }
        return _Analysis(values, reference, changed_paths)

    @staticmethod
    def _result_records(analysis: _Analysis) -> tuple[ResultRecord, ...]:
        return tuple(
            ResultRecord(
                id=result_id,
                version="agent.evaluator.result-record/v1",
                role=role,
                value=analysis.values[result_id],
                value_type=value_type,
                validity="valid",
                failure_reason=None,
                evidence_refs=(analysis.reference,),
                unit=unit,
                direction=direction,
            )
            for result_id, role, value_type, unit, direction in _RESULT_SHAPES
        )

    @staticmethod
    def _non_valid_records(
        validity: ResultValidity,
        reason: str,
        reference: EvidenceReference,
    ) -> tuple[ResultRecord, ...]:
        return tuple(
            ResultRecord(
                id=result_id,
                version="agent.evaluator.result-record/v1",
                role=role,
                value=None,
                value_type=value_type,
                validity=validity,
                failure_reason=reason,
                evidence_refs=(reference,),
                unit=unit,
                direction=direction,
            )
            for result_id, role, value_type, unit, direction in _RESULT_SHAPES
        )

    def _assessment(
        self,
        package: AuthorityBoundImportPackageV2,
        context: ProfileEvaluationContext,
        records: tuple[ResultRecord, ...],
        changed_paths: tuple[str, ...],
    ) -> ProfileAssessment:
        bundle = package.content.bundle
        terminal_failure = bundle.terminal.failure
        failures: tuple[Failure, ...] = ()
        if terminal_failure is not None:
            failures = (
                Failure(
                    domain=terminal_failure.domain,
                    code=terminal_failure.code,
                    message=terminal_failure.message,
                    evidence_references=(),
                ),
            )
        evidence = Evidence(
            schema_version="agent.evaluator.evidence/v1",
            evidence_id=context.evidence_id,
            evaluation_id=context.evaluation_id,
            profile_id=bundle.profile.profile_id,
            case_id=bundle.case.case_id,
            run_id=bundle.run.run_id,
            producer=external_producer_identity(
                bundle.producer.producer_id,
                bundle.producer.producer_version,
            ),
            process=None,
            tool_actions=tuple(
                ToolAction(
                    invocation_id=action.invocation_id,
                    tool=action.tool,
                    argv=action.argv,
                    exit_code=action.result.exit_code,
                    timed_out=action.result.status == "timed_out",
                    response_sha256=action.result.stdout_artifact.sha256,
                    committed=action.result.committed,
                    delivered=action.result.delivered,
                )
                for action in bundle.tool_actions
            ),
            artifacts=tuple(
                Artifact(
                    artifact_id=item.artifact_id,
                    path=item.path,
                    sha256=item.sha256,
                    media_type=item.media_type,
                )
                for item in bundle.artifacts
            ),
            answer=None,
            failures=failures,
            metadata={
                "projection_version": _PROJECTION_VERSION,
                "external_action_attested": False,
                "outcome_scope": "profile_owned_synthetic_execution_capsule",
                "candidate_tree_sha256": validate_candidate_tree(
                    _strict_object(
                        _artifact_by_id(package, "candidate-tree"), label="candidate tree"
                    ),
                    label="candidate tree",
                )["tree_sha256"],
                "changed_paths": changed_paths,
                "derived_diff": self._derived_diff(
                    validate_candidate_tree(
                        _strict_object(
                            _artifact_by_id(package, "candidate-tree"),
                            label="candidate tree",
                        ),
                        label="candidate tree",
                    )
                ),
            },
        )
        indexed = {record.id: record for record in records}
        observations: list[ScoreObservation] = []
        for result_id in _REQUIRED_RESULT_IDS:
            record = indexed[result_id]
            if record.validity == "valid":
                if type(record.value) is not bool:
                    raise ValueError("required coding evaluation results must be boolean")
                observations.append(
                    ScoreObservation(
                        observation_id=result_id,
                        applicability="observed",
                        value=record.value,
                        evidence_references=record.evidence_refs,
                    )
                )
            else:
                observations.append(
                    ScoreObservation(
                        observation_id=result_id,
                        applicability="invalid",
                        value=None,
                        reason=record.failure_reason,
                        evidence_references=record.evidence_refs,
                    )
                )
        score = Score(
            schema_version="agent.evaluator.score/v1",
            score_id=context.score_id,
            evidence_id=context.evidence_id,
            scorer_version=self._authority.scorer_policy.policy_version,
            observations=tuple(observations),
        )
        return ProfileAssessment(
            evidence=evidence,
            score=score,
            required_observations=_REQUIRED_RESULT_IDS,
            result_records=records,
        )


__all__ = ["CodingEvaluationProfile", "validate_candidate_tree"]
