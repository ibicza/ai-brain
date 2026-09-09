"""Versioned final-freeze authority for the M-33.6j.3 Java route.

The V2 contracts deliberately keep JSON decoding, typed authorization, freeze
materialization, Git identity, and Git-object lineage as separate trust layers.
Absolute executable paths are private inputs and never appear in public models.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336IFinalAcquisitionAuthorization,
)

M336J3_EXACT_Q25_SHA = "a2c5cbff8c42ace449b51a187cef70089be15ba3"
M336J3_BRANCH_NAME = "exp/stage3-m336j3-final-freeze-handshake-v10"
M336J3_BRANCH_REF = f"refs/heads/{M336J3_BRANCH_NAME}"
M336J3_UPSTREAM_REF = f"origin/{M336J3_BRANCH_NAME}"
M336J3_ACQUISITION_RUN_ID = "m336i.final-java.global-acquisition.v1"
M336J3_EVALUATION_RUN_ID = "m336j3.final-java.independent-evaluation.v2"
M336J3_R26_SUBJECT = "M-33.6j.3 close final freeze and acquisition handshake"
M336J3_Q26_SUBJECT = "M-33.6j.3 qualify complete disposable final protocol"
M336J3_F26_SUBJECT = "M-33.6j.3 freeze final Java execution authority"
M336J3_H26_SUBJECT = "M-33.6j.3 publish disposable H26 sealed production"
M336J3_E26_SUBJECT = "M-33.6j.3 publish disposable E26 independent evidence"
M336J3_FREEZE_ROOT = Path("artifacts/acquisition/m336j_freeze_v10")
M336J3_AUTHORIZATION_PATH = M336J3_FREEZE_ROOT / "final_authorization_v2.json"
M336J3_FREEZE_MANIFEST_PATH = M336J3_FREEZE_ROOT / "freeze_manifest_v2.json"
M336J3_FROZEN_FILE_MANIFEST_PATH = M336J3_FREEZE_ROOT / "frozen_file_manifest_v2.json"
M336J3_FREEZE_IDENTITY_EXCLUSIONS = frozenset(
    {
        M336J3_AUTHORIZATION_PATH.as_posix(),
        M336J3_FREEZE_MANIFEST_PATH.as_posix(),
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


class M336JFinalV2Error(ValueError):
    """A failure at the V2 final authority boundary."""


@dataclass(frozen=True)
class M336JFinalAuthorizationInputV2:
    acquisition_mode: str
    exact_q26_sha: str
    exact_r26_sha: str
    q26_staging_tree_hash: str
    prospective_f26_freeze_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    acquisition_provider_source_hash: str
    acquisition_provider_callable_signature_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    denylist_hash: str
    authority_root_hash: str
    selector_policy_hash: str
    threshold_manifest_hash: str
    publication_boundary_hash: str
    public_artifact_contract_hash: str
    spdx_reference_binding_hash: str
    execution_capsule_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    remote_command_renderer_hash: str
    minimal_environment_policy_hash: str
    windows_public_jdk_identity_receipt_hash: str
    karina_public_jdk_identity_receipt_hash: str
    karina_stable_host_identity_receipt_hash: str
    acquisition_run_id: str
    branch_ref: str
    allowed_network_hosts: tuple[str, ...]
    expected_global_acquisition_count: int
    expected_windows_acquisition_count: int
    expected_karina_acquisition_count: int


@dataclass(frozen=True)
class M336JFinalAcquisitionAuthorizationV2:
    schema_version: int
    contract_role: str
    acquisition_mode: str
    exact_q26_sha: str
    exact_r26_sha: str
    q26_staging_tree_hash: str
    prospective_f26_freeze_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    acquisition_provider_source_hash: str
    acquisition_provider_callable_signature_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    denylist_hash: str
    authority_root_hash: str
    selector_policy_hash: str
    threshold_manifest_hash: str
    publication_boundary_hash: str
    public_artifact_contract_hash: str
    spdx_reference_binding_hash: str
    execution_capsule_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    remote_command_renderer_hash: str
    minimal_environment_policy_hash: str
    windows_public_jdk_identity_receipt_hash: str
    karina_public_jdk_identity_receipt_hash: str
    karina_stable_host_identity_receipt_hash: str
    acquisition_run_id: str
    branch_ref: str
    allowed_network_hosts: tuple[str, ...]
    expected_global_acquisition_count: int
    expected_windows_acquisition_count: int
    expected_karina_acquisition_count: int
    authorization_hash: str


def load_m336j_final_authorization_input_v2(
    source: Path | dict,
) -> M336JFinalAuthorizationInputV2:
    value = _object(source)
    expected = {item.name for item in fields(M336JFinalAuthorizationInputV2)}
    if set(value) != expected:
        _fail("authorization input fields changed")
    raw_hosts = value.get("allowed_network_hosts")
    if not isinstance(raw_hosts, list):
        _fail("allowed_network_hosts must be a JSON array")
    converted = dict(value)
    converted["allowed_network_hosts"] = _canonical_hosts(raw_hosts)
    try:
        result = M336JFinalAuthorizationInputV2(**converted)
    except TypeError as error:
        raise M336JFinalV2Error("authorization input types changed") from error
    _verify_authorization_values(result)
    return result


def build_m336j_final_authorization_v2(
    value: M336JFinalAuthorizationInputV2,
) -> M336JFinalAcquisitionAuthorizationV2:
    if not isinstance(value, M336JFinalAuthorizationInputV2):
        raise TypeError("M336J V2 authorization builder requires typed input")
    _verify_authorization_values(value)
    body = {
        "schema_version": 2,
        "contract_role": "M336J_FINAL_ACQUISITION_AUTHORIZATION_V2",
        **asdict(value),
    }
    result = M336JFinalAcquisitionAuthorizationV2(
        **body, authorization_hash=content_hash(body)
    )
    verify_m336j_final_authorization_v2(result)
    return result


def dump_m336j_final_authorization_v2(
    value: M336JFinalAcquisitionAuthorizationV2,
) -> bytes:
    verify_m336j_final_authorization_v2(value)
    return (canonical_json(asdict(value)) + "\n").encode("utf-8")


def load_m336j_final_authorization_v2(
    source: Path | dict,
) -> M336JFinalAcquisitionAuthorizationV2:
    value = _object(source)
    expected = {item.name for item in fields(M336JFinalAcquisitionAuthorizationV2)}
    if set(value) != expected:
        _fail("authorization fields changed")
    raw_hosts = value.get("allowed_network_hosts")
    if not isinstance(raw_hosts, list):
        _fail("authorization hosts must be a JSON array")
    converted = dict(value)
    converted["allowed_network_hosts"] = _canonical_hosts(raw_hosts)
    try:
        result = M336JFinalAcquisitionAuthorizationV2(**converted)
    except TypeError as error:
        raise M336JFinalV2Error("authorization types changed") from error
    verify_m336j_final_authorization_v2(result)
    return result


def verify_m336j_final_authorization_v2(
    value: M336JFinalAcquisitionAuthorizationV2,
) -> None:
    if not isinstance(value, M336JFinalAcquisitionAuthorizationV2):
        raise TypeError("M336J V2 authorization must be typed")
    body = asdict(value)
    claimed = body.pop("authorization_hash")
    if (
        value.schema_version != 2
        or value.contract_role != "M336J_FINAL_ACQUISITION_AUTHORIZATION_V2"
        or content_hash(body) != claimed
    ):
        _fail("authorization is not content-derived")
    typed_input = M336JFinalAuthorizationInputV2(
        **{
            item.name: getattr(value, item.name)
            for item in fields(M336JFinalAuthorizationInputV2)
        }
    )
    _verify_authorization_values(typed_input)


def m336j_final_authorization_v2_to_legacy(
    value: M336JFinalAcquisitionAuthorizationV2,
) -> M336IFinalAcquisitionAuthorization:
    """Create the inherited provider adapter only after independent V2 checks."""

    verify_m336j_final_authorization_v2(value)
    body = {
        "schema_version": 1,
        "authorization_role": "FROZEN_FINAL_ACQUISITION_AUTHORIZATION",
        "acquisition_mode": value.acquisition_mode,
        "exact_q23_sha": M336J3_EXACT_Q25_SHA,
        "r24_implementation_tree_identity": value.prospective_f26_freeze_identity,
        "q24_evidence_identity": value.q26_staging_tree_hash,
        "f24_parent_sha": value.exact_q26_sha,
        "f24_freeze_tree_identity": value.prospective_f26_freeze_identity,
        "route_registry_hash": value.route_registry_hash,
        "route_manifest_hash": value.route_manifest_hash,
        "acquisition_provider_source_hash": value.acquisition_provider_source_hash,
        "acquisition_provider_callable_signature_hash": (
            value.acquisition_provider_callable_signature_hash
        ),
        "candidate_pool_hash": value.candidate_pool_hash,
        "acquisition_policy_hash": value.acquisition_policy_hash,
        "denylist_hash": value.denylist_hash,
        "authority_root_hash": value.authority_root_hash,
        "selector_policy_hash": value.selector_policy_hash,
        "threshold_manifest_hash": value.threshold_manifest_hash,
        "publication_boundary_hash": value.publication_boundary_hash,
        "public_artifact_contract_hash": value.public_artifact_contract_hash,
        "windows_public_jdk_identity_receipt_hash": (
            value.windows_public_jdk_identity_receipt_hash
        ),
        "karina_public_jdk_identity_receipt_hash": (
            value.karina_public_jdk_identity_receipt_hash
        ),
        "karina_stable_host_identity_receipt_hash": (
            value.karina_stable_host_identity_receipt_hash
        ),
        "acquisition_run_id": value.acquisition_run_id,
        "allowed_network_hosts": value.allowed_network_hosts,
        "expected_global_acquisition_count": value.expected_global_acquisition_count,
        "expected_windows_acquisition_count": (
            value.expected_windows_acquisition_count
        ),
        "expected_karina_acquisition_count": value.expected_karina_acquisition_count,
        "branch_ref": value.branch_ref,
    }
    return M336IFinalAcquisitionAuthorization(
        **body, authorization_hash=content_hash(body)
    )


@dataclass(frozen=True)
class M336JFinalFreezeManifestV2:
    schema_version: int
    contract_role: str
    exact_q26_sha: str
    exact_r26_sha: str
    q26_staging_tree_hash: str
    freeze_tree_identity: str
    authorization_hash: str
    route_registry_hash: str
    route_manifest_hash: str
    spdx_reference_binding_hash: str
    execution_capsule_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    remote_command_renderer_hash: str
    minimal_environment_policy_hash: str
    candidate_pool_hash: str
    acquisition_policy_hash: str
    denylist_hash: str
    authority_root_hash: str
    selector_policy_hash: str
    threshold_manifest_hash: str
    publication_boundary_hash: str
    public_artifact_contract_hash: str
    windows_public_jdk_identity_receipt_hash: str
    karina_public_jdk_identity_receipt_hash: str
    karina_stable_host_identity_receipt_hash: str
    final_acquisition_reservation_count: int
    final_acquisition_invocation_count: int
    status: str
    manifest_hash: str


def build_m336j_final_freeze_manifest_v2(
    *,
    authorization: M336JFinalAcquisitionAuthorizationV2,
) -> M336JFinalFreezeManifestV2:
    verify_m336j_final_authorization_v2(authorization)
    body = {
        "schema_version": 2,
        "contract_role": "M336J_FINAL_FREEZE_MANIFEST_V2",
        "exact_q26_sha": authorization.exact_q26_sha,
        "exact_r26_sha": authorization.exact_r26_sha,
        "q26_staging_tree_hash": authorization.q26_staging_tree_hash,
        "freeze_tree_identity": authorization.prospective_f26_freeze_identity,
        "authorization_hash": authorization.authorization_hash,
        **{
            name: getattr(authorization, name)
            for name in (
                "route_registry_hash",
                "route_manifest_hash",
                "spdx_reference_binding_hash",
                "execution_capsule_public_receipt_hash",
                "python_environment_manifest_hash",
                "executable_dependency_manifest_hash",
                "remote_command_renderer_hash",
                "minimal_environment_policy_hash",
                "candidate_pool_hash",
                "acquisition_policy_hash",
                "denylist_hash",
                "authority_root_hash",
                "selector_policy_hash",
                "threshold_manifest_hash",
                "publication_boundary_hash",
                "public_artifact_contract_hash",
                "windows_public_jdk_identity_receipt_hash",
                "karina_public_jdk_identity_receipt_hash",
                "karina_stable_host_identity_receipt_hash",
            )
        },
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "status": "F26_READY_TO_COMMIT",
    }
    result = M336JFinalFreezeManifestV2(**body, manifest_hash=content_hash(body))
    verify_m336j_final_freeze_manifest_v2(result, authorization=authorization)
    return result


def dump_m336j_final_freeze_manifest_v2(value: M336JFinalFreezeManifestV2) -> bytes:
    verify_m336j_final_freeze_manifest_v2(value)
    return (canonical_json(asdict(value)) + "\n").encode("utf-8")


def load_m336j_final_freeze_manifest_v2(
    source: Path | dict,
) -> M336JFinalFreezeManifestV2:
    value = _object(source)
    expected = {item.name for item in fields(M336JFinalFreezeManifestV2)}
    if set(value) != expected:
        _fail("freeze manifest fields changed")
    try:
        result = M336JFinalFreezeManifestV2(**value)
    except TypeError as error:
        raise M336JFinalV2Error("freeze manifest types changed") from error
    verify_m336j_final_freeze_manifest_v2(result)
    return result


def verify_m336j_final_freeze_manifest_v2(
    value: M336JFinalFreezeManifestV2,
    *,
    authorization: M336JFinalAcquisitionAuthorizationV2 | None = None,
) -> None:
    if not isinstance(value, M336JFinalFreezeManifestV2):
        raise TypeError("M336J V2 freeze manifest must be typed")
    body = asdict(value)
    claimed = body.pop("manifest_hash")
    hashes = (
        item_value
        for name, item_value in body.items()
        if name.endswith(("_hash", "_identity"))
    )
    if (
        value.schema_version != 2
        or value.contract_role != "M336J_FINAL_FREEZE_MANIFEST_V2"
        or value.status != "F26_READY_TO_COMMIT"
        or not _is_git_sha(value.exact_q26_sha)
        or not _is_git_sha(value.exact_r26_sha)
        or any(not _is_hash(item) for item in hashes)
        or value.final_acquisition_reservation_count != 0
        or value.final_acquisition_invocation_count != 0
        or content_hash(body) != claimed
    ):
        _fail("freeze manifest is invalid")
    if authorization is not None:
        verify_m336j_final_authorization_v2(authorization)
        shared_binding_fields = (
            "route_registry_hash",
            "route_manifest_hash",
            "spdx_reference_binding_hash",
            "execution_capsule_public_receipt_hash",
            "python_environment_manifest_hash",
            "executable_dependency_manifest_hash",
            "remote_command_renderer_hash",
            "minimal_environment_policy_hash",
            "candidate_pool_hash",
            "acquisition_policy_hash",
            "denylist_hash",
            "authority_root_hash",
            "selector_policy_hash",
            "threshold_manifest_hash",
            "publication_boundary_hash",
            "public_artifact_contract_hash",
            "windows_public_jdk_identity_receipt_hash",
            "karina_public_jdk_identity_receipt_hash",
            "karina_stable_host_identity_receipt_hash",
        )
        expected = {
            "exact_q26_sha": authorization.exact_q26_sha,
            "exact_r26_sha": authorization.exact_r26_sha,
            "q26_staging_tree_hash": authorization.q26_staging_tree_hash,
            "freeze_tree_identity": authorization.prospective_f26_freeze_identity,
            "authorization_hash": authorization.authorization_hash,
            **{name: getattr(authorization, name) for name in shared_binding_fields},
        }
        if any(getattr(value, name) != item for name, item in expected.items()):
            _fail("authorization and freeze manifest cross-bindings differ")


@dataclass(frozen=True)
class M336JF26FrozenFile:
    destination_path: str
    source_artifact_role: str
    bytes_hash: str


@dataclass(frozen=True)
class M336JF26FrozenFileManifest:
    schema_version: int
    contract_role: str
    acquisition_mode: str
    files: tuple[M336JF26FrozenFile, ...]
    file_count: int
    manifest_hash: str


M336J3_FINAL_FROZEN_SOURCES = {
    "acquisition_policy.json": (
        "artifacts/acquisition/m336i_freeze_v8/acquisition_policy.json",
        "ACQUISITION_POLICY",
    ),
    "authority_root.json": (
        "artifacts/acquisition/m336i_freeze_v8/authority_root.json",
        "AUTHORITY_ROOT",
    ),
    "authority_statement.txt": (
        "artifacts/acquisition/m336i_freeze_v8/authority_statement.txt",
        "AUTHORITY_STATEMENT",
    ),
    "candidate_pool.json": (
        "artifacts/acquisition/m336i_freeze_v8/candidate_pool.json",
        "CANDIDATE_POOL",
    ),
    "commit_protocol.json": (
        "artifacts/acquisition/m336i_freeze_v8/commit_protocol.json",
        "LEGACY_COMMIT_PROTOCOL",
    ),
    "compiler_jdk_identities.json": (
        "artifacts/acquisition/m336i_freeze_v8/compiler_jdk_identities.json",
        "COMPILER_JDK_IDENTITIES",
    ),
    "denylist.json": (
        "artifacts/acquisition/m336i_freeze_v8/denylist.json",
        "DENYLIST",
    ),
    "karina_host_identity_receipt.json": (
        "artifacts/acquisition/m336i_freeze_v8/karina_host_identity_receipt.json",
        "KARINA_HOST_IDENTITY",
    ),
    "outcome_logic.json": (
        "artifacts/acquisition/m336i_freeze_v8/outcome_logic.json",
        "OUTCOME_LOGIC",
    ),
    "public_artifact_contract.json": (
        "artifacts/acquisition/m336i_freeze_v8/public_artifact_contract.json",
        "PUBLIC_ARTIFACT_CONTRACT",
    ),
    "publication_boundary_contract.json": (
        "artifacts/acquisition/m336i_freeze_v8/publication_boundary_contract.json",
        "PUBLICATION_BOUNDARY",
    ),
    "route_state_machine_contract.json": (
        "artifacts/acquisition/m336i_freeze_v8/route_state_machine_contract.json",
        "ROUTE_STATE_CONTRACT",
    ),
    "selector_policy.json": (
        "artifacts/acquisition/m336i_freeze_v8/selector_policy.json",
        "SELECTOR_POLICY",
    ),
    "spdx_reference_binding.json": (
        "artifacts/acquisition/m336i_freeze_v8/spdx_reference_binding.json",
        "SPDX_REFERENCE_BINDING",
    ),
    "threshold_manifest.json": (
        "artifacts/acquisition/m336i_freeze_v8/threshold_manifest.json",
        "THRESHOLD_MANIFEST",
    ),
    "q25/executable_dependency_manifest.json": (
        "artifacts/m336j/qualification-inputs/executable_dependency_manifest.json",
        "EXECUTABLE_DEPENDENCY_MANIFEST",
    ),
    "q25/public_execution_capsule_receipt.json": (
        "artifacts/m336j/qualification-inputs/public_execution_capsule_receipt.json",
        "EXECUTION_CAPSULE_PUBLIC_RECEIPT",
    ),
    "q25/python_environment_manifest.json": (
        "artifacts/m336j/qualification-inputs/python_environment_manifest.json",
        "PYTHON_ENVIRONMENT_MANIFEST",
    ),
    "q25/q25_tree_manifest.json": (
        "artifacts/m336j/q25_tree_manifest.json",
        "Q25_TREE_MANIFEST",
    ),
    "q25/readiness_result.json": (
        "runs/m336j/readiness_result.json",
        "Q25_READINESS",
    ),
}
M336J3_REHEARSAL_FROZEN_SOURCES = {
    **M336J3_FINAL_FROZEN_SOURCES,
    "acquisition_policy.json": (
        "tests/fixtures/m336j3/count_neutral_acquisition_policy.json",
        "REHEARSAL_ACQUISITION_POLICY",
    ),
    "candidate_pool.json": (
        "tests/fixtures/m336j3/count_neutral_candidate_pool.json",
        "REHEARSAL_CANDIDATE_POOL",
    ),
}
M336J3_REQUIRED_FROZEN_FILES = {
    destination: role
    for destination, (_source, role) in M336J3_FINAL_FROZEN_SOURCES.items()
}
M336J3_REHEARSAL_FROZEN_FILES = {
    destination: role
    for destination, (_source, role) in M336J3_REHEARSAL_FROZEN_SOURCES.items()
}


def build_m336j_f26_frozen_file_manifest(
    repository: Path,
    *,
    acquisition_mode: str = "FINAL",
    readiness: Path | None = None,
    public_capsule_receipt: Path | None = None,
    python_environment_manifest: Path | None = None,
    executable_dependency_manifest: Path | None = None,
    spdx_binding: Path | None = None,
) -> M336JF26FrozenFileManifest:
    root = repository.resolve(strict=True)
    sources = resolve_m336j_f26_frozen_sources(
        root,
        acquisition_mode=acquisition_mode,
        readiness=readiness,
        public_capsule_receipt=public_capsule_receipt,
        python_environment_manifest=python_environment_manifest,
        executable_dependency_manifest=executable_dependency_manifest,
        spdx_binding=spdx_binding,
    )
    roles = (
        M336J3_REQUIRED_FROZEN_FILES
        if acquisition_mode == "FINAL"
        else M336J3_REHEARSAL_FROZEN_FILES
    )
    if acquisition_mode not in {"FINAL", "REHEARSAL"}:
        _fail("frozen file manifest acquisition mode is invalid")
    rows = tuple(
        M336JF26FrozenFile(
            destination_path=destination,
            source_artifact_role=role,
            bytes_hash=bytes_hash(sources[destination].read_bytes()),
        )
        for destination, role in sorted(roles.items())
    )
    body = {
        "schema_version": 2,
        "contract_role": "M336J_F26_FROZEN_FILE_MANIFEST",
        "acquisition_mode": acquisition_mode,
        "files": rows,
        "file_count": len(rows),
    }
    result = M336JF26FrozenFileManifest(**body, manifest_hash=content_hash(body))
    verify_m336j_f26_frozen_file_manifest(result)
    return result


def resolve_m336j_f26_frozen_sources(
    repository: Path,
    *,
    acquisition_mode: str,
    readiness: Path | None = None,
    public_capsule_receipt: Path | None = None,
    python_environment_manifest: Path | None = None,
    executable_dependency_manifest: Path | None = None,
    spdx_binding: Path | None = None,
) -> dict[str, Path]:
    root = repository.resolve(strict=True)
    configured = (
        M336J3_FINAL_FROZEN_SOURCES
        if acquisition_mode == "FINAL"
        else M336J3_REHEARSAL_FROZEN_SOURCES
    )
    if acquisition_mode not in {"FINAL", "REHEARSAL"}:
        _fail("frozen file manifest acquisition mode is invalid")
    result = {
        destination: (root / relative).resolve(strict=True)
        for destination, (relative, _role) in configured.items()
    }
    named = {
        "q25/readiness_result.json": readiness,
        "q25/public_execution_capsule_receipt.json": public_capsule_receipt,
        "q25/python_environment_manifest.json": python_environment_manifest,
        "q25/executable_dependency_manifest.json": executable_dependency_manifest,
        "spdx_reference_binding.json": spdx_binding,
    }
    for destination, supplied in named.items():
        if supplied is not None:
            result[destination] = supplied.resolve(strict=True)
    return result


def load_m336j_f26_frozen_file_manifest(
    source: Path | dict,
) -> M336JF26FrozenFileManifest:
    value = _object(source)
    expected = {item.name for item in fields(M336JF26FrozenFileManifest)}
    if set(value) != expected or not isinstance(value.get("files"), list):
        _fail("frozen file manifest fields changed")
    rows = []
    for row in value["files"]:
        if not isinstance(row, dict) or set(row) != {
            item.name for item in fields(M336JF26FrozenFile)
        }:
            _fail("frozen file row fields changed")
        rows.append(M336JF26FrozenFile(**row))
    result = M336JF26FrozenFileManifest(**{**value, "files": tuple(rows)})
    verify_m336j_f26_frozen_file_manifest(result)
    return result


def verify_m336j_f26_frozen_file_manifest(
    value: M336JF26FrozenFileManifest,
) -> None:
    if not isinstance(value, M336JF26FrozenFileManifest):
        raise TypeError("M336J F26 frozen files must be typed")
    body = asdict(value)
    claimed = body.pop("manifest_hash")
    actual = {row.destination_path: row.source_artifact_role for row in value.files}
    expected_files = (
        M336J3_REQUIRED_FROZEN_FILES
        if value.acquisition_mode == "FINAL"
        else M336J3_REHEARSAL_FROZEN_FILES
    )
    if (
        value.schema_version != 2
        or value.contract_role != "M336J_F26_FROZEN_FILE_MANIFEST"
        or value.acquisition_mode not in {"FINAL", "REHEARSAL"}
        or value.file_count != len(value.files)
        or actual != expected_files
        or len(actual) != len(value.files)
        or tuple(row.destination_path for row in value.files)
        != tuple(sorted(expected_files))
        or any(not _safe_relative(row.destination_path) for row in value.files)
        or any(not _is_hash(row.bytes_hash) for row in value.files)
        or content_hash(body) != claimed
    ):
        _fail("frozen file manifest is invalid")


def dump_m336j_f26_frozen_file_manifest(
    value: M336JF26FrozenFileManifest,
) -> bytes:
    verify_m336j_f26_frozen_file_manifest(value)
    return (canonical_json(asdict(value)) + "\n").encode("utf-8")


def compute_m336j_freeze_tree_identity_v2(
    repository: Path,
    git_executable: Path,
) -> str:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    raw = _git_bytes(
        git,
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    explicit = {
        path.relative_to(root).as_posix()
        for path in (root / M336J3_FREEZE_ROOT).rglob("*")
        if path.is_file()
    }
    paths = tuple(
        sorted(
            {item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item}
            | explicit,
            key=lambda item: item.encode("utf-8"),
        )
    )
    included = tuple(
        path for path in paths if path not in M336J3_FREEZE_IDENTITY_EXCLUSIONS
    )
    return content_hash(
        tuple((path, bytes_hash((root / path).read_bytes())) for path in included)
    )


def compute_m336j_q26_staging_tree_hash(
    repository: Path,
    git_executable: Path,
    *,
    exact_r26_sha: str,
    exact_q26_sha: str,
) -> str:
    """Derive the evidence-only Q26 staging identity from committed bytes."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    raw_paths = _git_bytes(
        git,
        root,
        "diff",
        "--name-only",
        "-z",
        exact_r26_sha,
        exact_q26_sha,
    )
    paths = tuple(
        sorted(
            (
                item.decode("utf-8", errors="strict")
                for item in raw_paths.split(b"\0")
                if item
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not paths or any(
        not (
            path.startswith(("artifacts/m336j3/", "runs/m336j3/"))
            or (path.startswith("docs/m336j3_") and path.endswith(".md"))
        )
        for path in paths
    ):
        _fail("Q26 is not evidence-only")
    rows = tuple(
        (
            path,
            bytes_hash(_git_bytes(git, root, "show", f"{exact_q26_sha}:{path}")),
        )
        for path in paths
    )
    return content_hash(rows)


@dataclass(frozen=True)
class M336JGitExecutableReceiptV2:
    schema_version: int
    contract_role: str
    executable_role: str
    binary_hash: str
    normalized_version_hash: str
    execution_capsule_public_receipt_hash: str
    environment_identity_hash: str
    bare_executable_lookup_count: int
    status: str
    receipt_hash: str


def build_m336j_git_executable_receipt_v2(
    git_executable: Path,
    *,
    execution_capsule_public_receipt_hash: str,
    environment_identity_hash: str,
) -> M336JGitExecutableReceiptV2:
    git = git_executable.resolve(strict=True)
    if not git.is_file():
        _fail("Git executable is not a regular file")
    version = _git_text(git, None, "--version")
    if not version.startswith("git version "):
        _fail("exact Git executable does not identify as Git")
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336J_EXACT_GIT_EXECUTABLE_RECEIPT_V2",
        "executable_role": "EXACT_GIT",
        "binary_hash": bytes_hash(git.read_bytes()),
        "normalized_version_hash": content_hash(" ".join(version.split())),
        "execution_capsule_public_receipt_hash": (
            execution_capsule_public_receipt_hash
        ),
        "environment_identity_hash": environment_identity_hash,
        "bare_executable_lookup_count": 0,
        "status": "PASS",
    }
    if any(not _is_hash(body[name]) for name in body if name.endswith("_hash")):
        _fail("Git executable receipt has an invalid identity")
    return M336JGitExecutableReceiptV2(**body, receipt_hash=content_hash(body))


@dataclass(frozen=True)
class M336JFinalFreezeLineagePolicyV2:
    schema_version: int
    contract_role: str
    exact_q25_sha: str
    exact_r26_sha: str
    exact_q26_sha: str
    exact_f26_sha: str
    expected_subject_hashes: tuple[str, str, str]
    expected_branch_name: str
    expected_branch_ref: str
    expected_upstream_ref: str
    policy_hash: str


@dataclass(frozen=True)
class M336JFinalFreezeLineageReceiptV2:
    schema_version: int
    contract_role: str
    policy_hash: str
    git_executable_receipt_hash: str
    ordered_commit_shas: tuple[str, str, str]
    parent_rows: tuple[tuple[str, str], tuple[str, str], tuple[str, str]]
    subject_hashes: tuple[str, str, str]
    head_sha: str
    upstream_sha: str
    remote_sha: str
    merge_count: int
    missing_commit_count: int
    extra_commit_count: int
    dirty_path_count: int
    committed_freeze_byte_mismatch_count: int
    status: str
    receipt_hash: str


def build_m336j_final_freeze_lineage_policy_v2(
    *, exact_r26_sha: str, exact_q26_sha: str, exact_f26_sha: str
) -> M336JFinalFreezeLineagePolicyV2:
    body = {
        "schema_version": 2,
        "contract_role": "M336J_FINAL_FREEZE_LINEAGE_POLICY_V2",
        "exact_q25_sha": M336J3_EXACT_Q25_SHA,
        "exact_r26_sha": exact_r26_sha,
        "exact_q26_sha": exact_q26_sha,
        "exact_f26_sha": exact_f26_sha,
        "expected_subject_hashes": (
            content_hash(M336J3_R26_SUBJECT),
            content_hash(M336J3_Q26_SUBJECT),
            content_hash(M336J3_F26_SUBJECT),
        ),
        "expected_branch_name": M336J3_BRANCH_NAME,
        "expected_branch_ref": M336J3_BRANCH_REF,
        "expected_upstream_ref": M336J3_UPSTREAM_REF,
    }
    result = M336JFinalFreezeLineagePolicyV2(**body, policy_hash=content_hash(body))
    _verify_final_lineage_policy(result)
    return result


def verify_m336j_pre_freeze_lineage_v2(
    repository: Path,
    git_executable: Path,
    *,
    exact_r26_sha: str,
    exact_q26_sha: str,
    expected_branch_name: str = M336J3_BRANCH_NAME,
    expected_upstream_ref: str = M336J3_UPSTREAM_REF,
) -> dict:
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    ordered = _ordered_range(git, root, M336J3_EXACT_Q25_SHA, exact_q26_sha)
    expected = (exact_r26_sha, exact_q26_sha)
    parents = tuple(_parent_row(git, root, item) for item in ordered)
    subjects = tuple(_subject_hash(git, root, item) for item in ordered)
    branch = _git_text(git, root, "symbolic-ref", "--short", "HEAD")
    upstream_ref = _git_text(
        git, root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    upstream = _git_text(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _remote_sha(git, root, M336J3_BRANCH_REF)
    if (
        _git_text(git, root, "rev-parse", "HEAD^{commit}") != exact_q26_sha
        or ordered != expected
        or parents
        != ((exact_r26_sha, M336J3_EXACT_Q25_SHA), (exact_q26_sha, exact_r26_sha))
        or subjects
        != (content_hash(M336J3_R26_SUBJECT), content_hash(M336J3_Q26_SUBJECT))
        or branch != expected_branch_name
        or upstream_ref != expected_upstream_ref
        or upstream != exact_q26_sha
        or remote != exact_q26_sha
        or _git_text(git, root, "status", "--porcelain=v1")
        or int(
            _git_text(
                git,
                root,
                "rev-list",
                "--count",
                "--merges",
                f"{M336J3_EXACT_Q25_SHA}..{exact_q26_sha}",
            )
        )
    ):
        _fail("pre-freeze Git lineage differs from Q25 -> R26 -> Q26")
    body = {
        "schema_version": 2,
        "contract_role": "M336J_PRE_FREEZE_LINEAGE_RECEIPT_V2",
        "ordered_commit_shas": ordered,
        "parent_rows": parents,
        "subject_hashes": subjects,
        "branch_name_hash": content_hash(branch),
        "upstream_ref_hash": content_hash(upstream_ref),
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}


def verify_m336j_final_freeze_lineage_v2(
    repository: Path,
    git_executable: Path,
    policy: M336JFinalFreezeLineagePolicyV2,
    git_receipt: M336JGitExecutableReceiptV2,
) -> M336JFinalFreezeLineageReceiptV2:
    _verify_final_lineage_policy(policy)
    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    if git_receipt.status != "PASS" or git_receipt.bare_executable_lookup_count != 0:
        _fail("exact Git executable receipt is invalid")
    ordered = _ordered_range(git, root, policy.exact_q25_sha, policy.exact_f26_sha)
    expected = (policy.exact_r26_sha, policy.exact_q26_sha, policy.exact_f26_sha)
    parent_rows = tuple(_parent_row(git, root, item) for item in ordered)
    expected_parents = (
        (policy.exact_r26_sha, policy.exact_q25_sha),
        (policy.exact_q26_sha, policy.exact_r26_sha),
        (policy.exact_f26_sha, policy.exact_q26_sha),
    )
    subjects = tuple(_subject_hash(git, root, item) for item in ordered)
    head = _git_text(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git_text(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _remote_sha(git, root, policy.expected_branch_ref)
    branch = _git_text(git, root, "symbolic-ref", "--short", "HEAD")
    status = tuple(
        line
        for line in _git_text(git, root, "status", "--porcelain=v1").splitlines()
        if line
    )
    merge_count = int(
        _git_text(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{policy.exact_q25_sha}..{policy.exact_f26_sha}",
        )
    )
    committed_mismatch = sum(
        _git_bytes(
            git,
            root,
            "show",
            f"{policy.exact_f26_sha}:{relative}",
        )
        != (root / relative).read_bytes()
        for relative in (
            M336J3_AUTHORIZATION_PATH.as_posix(),
            M336J3_FREEZE_MANIFEST_PATH.as_posix(),
        )
    )
    missing = len(set(expected) - set(ordered))
    extra = len(set(ordered) - set(expected))
    if (
        ordered != expected
        or parent_rows != expected_parents
        or subjects != policy.expected_subject_hashes
        or head != policy.exact_f26_sha
        or upstream != head
        or remote != head
        or branch != policy.expected_branch_name
        or status
        or merge_count
        or missing
        or extra
        or committed_mismatch
    ):
        _fail("final Git objects differ from Q25 -> R26 -> Q26 -> F26")
    body = {
        "schema_version": 2,
        "contract_role": "M336J_FINAL_FREEZE_LINEAGE_RECEIPT_V2",
        "policy_hash": policy.policy_hash,
        "git_executable_receipt_hash": git_receipt.receipt_hash,
        "ordered_commit_shas": ordered,
        "parent_rows": parent_rows,
        "subject_hashes": subjects,
        "head_sha": head,
        "upstream_sha": upstream,
        "remote_sha": remote,
        "merge_count": merge_count,
        "missing_commit_count": missing,
        "extra_commit_count": extra,
        "dirty_path_count": len(status),
        "committed_freeze_byte_mismatch_count": committed_mismatch,
        "status": "PASS",
    }
    return M336JFinalFreezeLineageReceiptV2(**body, receipt_hash=content_hash(body))


def verify_m336j_authorization_manifest_cross_bindings_v2(
    authorization: M336JFinalAcquisitionAuthorizationV2,
    manifest: M336JFinalFreezeManifestV2,
) -> None:
    verify_m336j_final_freeze_manifest_v2(manifest, authorization=authorization)


def _verify_authorization_values(
    value: M336JFinalAuthorizationInputV2,
) -> None:
    hashes = (
        item_value
        for name, item_value in asdict(value).items()
        if name.endswith(("_hash", "_identity"))
    )
    if (
        value.acquisition_mode not in {"FINAL", "REHEARSAL"}
        or not _is_git_sha(value.exact_q26_sha)
        or not _is_git_sha(value.exact_r26_sha)
        or value.exact_q26_sha == value.exact_r26_sha
        or any(not _is_hash(item) for item in hashes)
        or value.acquisition_run_id != M336J3_ACQUISITION_RUN_ID
        or value.branch_ref != M336J3_BRANCH_REF
        or value.allowed_network_hosts
        != tuple(sorted(set(value.allowed_network_hosts)))
        or not value.allowed_network_hosts
        or value.expected_global_acquisition_count != 1
        or value.expected_windows_acquisition_count != 1
        or value.expected_karina_acquisition_count != 0
    ):
        _fail("authorization values are invalid")
    _canonical_hosts(list(value.allowed_network_hosts))


def _canonical_hosts(raw_hosts: list) -> tuple[str, ...]:
    if not raw_hosts:
        _fail("network host allowlist is empty")
    hosts = []
    for host in raw_hosts:
        if not isinstance(host, str) or not host or host != host.strip():
            _fail("network hostname is empty or contains whitespace")
        if host != host.casefold() or _HOST.fullmatch(host) is None:
            _fail("network hostname is not canonical")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            _fail("IP literals require a separately frozen policy")
        hosts.append(host)
    if hosts != sorted(hosts) or len(hosts) != len(set(hosts)):
        _fail("network hosts must be sorted and unique")
    return tuple(hosts)


def _verify_final_lineage_policy(value: M336JFinalFreezeLineagePolicyV2) -> None:
    if not isinstance(value, M336JFinalFreezeLineagePolicyV2):
        raise TypeError("M336J V2 final lineage policy must be typed")
    body = asdict(value)
    claimed = body.pop("policy_hash")
    if (
        value.schema_version != 2
        or value.contract_role != "M336J_FINAL_FREEZE_LINEAGE_POLICY_V2"
        or value.exact_q25_sha != M336J3_EXACT_Q25_SHA
        or len(
            {
                value.exact_q25_sha,
                value.exact_r26_sha,
                value.exact_q26_sha,
                value.exact_f26_sha,
            }
        )
        != 4
        or any(
            not _is_git_sha(item)
            for item in (
                value.exact_q25_sha,
                value.exact_r26_sha,
                value.exact_q26_sha,
                value.exact_f26_sha,
            )
        )
        or value.expected_branch_name != M336J3_BRANCH_NAME
        or value.expected_branch_ref != M336J3_BRANCH_REF
        or value.expected_upstream_ref != M336J3_UPSTREAM_REF
        or content_hash(body) != claimed
    ):
        _fail("final lineage policy is invalid")


def _ordered_range(git: Path, root: Path, base: str, head: str) -> tuple[str, ...]:
    ancestor = _git_result(git, root, "merge-base", "--is-ancestor", base, head)
    if ancestor.returncode != 0:
        _fail("lineage base is not an ancestor")
    return tuple(
        line
        for line in _git_text(
            git, root, "rev-list", "--first-parent", "--reverse", f"{base}..{head}"
        ).splitlines()
        if line
    )


def _parent_row(git: Path, root: Path, commit: str) -> tuple[str, str]:
    tokens = _git_text(git, root, "rev-list", "--parents", "-n", "1", commit).split()
    if len(tokens) != 2 or tokens[0] != commit:
        _fail("final-stage commit does not have exactly one parent")
    return tokens[0], tokens[1]


def _subject_hash(git: Path, root: Path, commit: str) -> str:
    return content_hash(_git_text(git, root, "show", "-s", "--format=%s", commit))


def _remote_sha(git: Path, root: Path, branch_ref: str) -> str:
    output = _git_text(git, root, "ls-remote", "--exit-code", "origin", branch_ref)
    rows = tuple(line.split() for line in output.splitlines() if line)
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != branch_ref:
        _fail("remote branch identity is ambiguous")
    return rows[0][0]


def _git_text(git: Path, root: Path | None, *arguments: str) -> str:
    result = _git_result(git, root, *arguments)
    if result.returncode != 0:
        _fail("exact Git command failed")
    return result.stdout.strip()


def _git_bytes(git: Path, root: Path | None, *arguments: str) -> bytes:
    result = subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail("exact Git byte command failed")
    return result.stdout


def _git_result(
    git: Path, root: Path | None, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str):
        return False
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _object(source: Path | dict) -> dict:
    value = strict_json_file(source) if isinstance(source, Path) else source
    if not isinstance(value, dict):
        _fail("JSON boundary requires an object")
    return value


def _is_git_sha(value: object) -> bool:
    return isinstance(value, str) and _GIT_SHA.fullmatch(value) is not None


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _fail(message: str) -> None:
    raise M336JFinalV2Error(f"M336J_FINAL_V2: {message}")
