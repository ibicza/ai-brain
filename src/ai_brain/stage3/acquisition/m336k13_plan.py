"""Immutable final-controller invocation-plan binding for M-33.6k.13.

Public objects never contain private path values. The exact executable plan is
still ``M336K5PythonInvocationPlan``; the v13 private object is its write-once
lifecycle receipt.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5_REQUIRED_INTERPRETER_ARGUMENTS,
    M336K5PythonInvocationPlan,
    validate_m336k5_python_invocation,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfile,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k11_execution import (
    OFFICIAL_CONTROLLER,
    M336K11EffectiveEnvironmentBinding,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12NativeExecutionCapsuleReceipt,
    M336K12NativeRouteManifest,
    M336K12NativeStagePlanBinding,
    M336K12OfficialControllerExecutableBinding,
    M336K12OfficialExecutableBindingReceipt,
    M336K12PostFreezeInputBundle,
    M336K12ProducerConsumerParityReceipt,
)

M336K13_PROFILE_ID = "m336k8-final-v6"
M336K13_CONTROLLER_VERSION = "m336k13-controller.v6"
M336K13_EXECUTION_SCOPES = frozenset({"OFFICIAL_CONTROLLER", "REHEARSAL"})
M336K13_TARGET_REPOSITORY_PATH = "scripts/m336k13_run_final_route.py"
M336K13_BOOTSTRAP_REPOSITORY_PATH = "scripts/m336k5_python_bootstrap.py"
M336K13_VALIDATE_SHAPE = (
    "--request",
    "{FINAL_REQUEST}",
    "--validate-only",
    "--validation-receipt",
    "{POST_FREEZE_VALIDATION_RECEIPT}",
)
M336K13_EXECUTE_SHAPE = (
    "--request",
    "{FINAL_REQUEST}",
    "--post-freeze-validation-receipt",
    "{POST_FREEZE_VALIDATION_RECEIPT}",
    "--reservation-release-receipt",
    "{RESERVATION_RELEASE_RECEIPT}",
)
M336K13_VALIDATE_ARGUMENT_ROLES = (
    "FLAG_REQUEST",
    "FINAL_REQUEST",
    "FLAG_VALIDATE_ONLY",
    "FLAG_VALIDATION_RECEIPT",
    "POST_FREEZE_VALIDATION_RECEIPT",
)
M336K13_EXECUTE_ARGUMENT_ROLES = (
    "FLAG_REQUEST",
    "FINAL_REQUEST",
    "FLAG_POST_FREEZE_VALIDATION_RECEIPT",
    "POST_FREEZE_VALIDATION_RECEIPT",
    "FLAG_RESERVATION_RELEASE_RECEIPT",
    "RESERVATION_RELEASE_RECEIPT",
)
M336K13_PATH_ROLES = (
    "PRIVATE_PLAN_FILE",
    "FINAL_REQUEST",
    "POST_FREEZE_VALIDATION_RECEIPT",
    "RESERVATION_RELEASE_RECEIPT",
    "VALIDATE_STARTUP_RECEIPT",
    "EXECUTE_STARTUP_RECEIPT",
    "VALIDATE_ACTUAL_LAUNCHER_RECEIPT",
    "EXECUTE_ACTUAL_LAUNCHER_RECEIPT",
)
M336K13_MUTATION_CASES = (
    "same-filename-different-plan-bytes",
    "same-operation-shape-different-invocation-plan-hash",
    "correct-plan-hash-wrong-plan-bytes-hash",
    "correct-plan-bytes-hash-wrong-plan-file-identity",
    "validate-request-differs-from-execute-request",
    "execute-validation-receipt-differs-from-validate-output",
    "non-prospective-name-with-wrong-validation-identity",
    "release-path-changed",
    "validate-startup-receipt-changed",
    "execute-startup-receipt-changed",
    "startup-receipts-swapped",
    "duplicate-startup-receipt-path",
    "request-collides-with-validation",
    "release-collides-with-startup",
    "relative-private-path",
    "target-changed",
    "target-source-bytes-changed",
    "bootstrap-changed",
    "python-executable-changed",
    "git-executable-changed",
    "powershell-executable-changed",
    "repository-changed",
    "working-directory-changed",
    "environment-prefix-changed",
    "sanitized-environment-changed",
    "source-identity-changed",
    "startup-policy-changed",
    "equal-lineage-sha-bypass",
    "stable-looking-filename-with-unstable-plan",
    "r38a-shape-with-different-full-plan-hash",
    "plan-overwritten-after-q",
    "plan-overwritten-after-f",
    "plan-regenerated-before-execute",
    "second-execute-only-plan",
    "actual-plan-hash-differs-from-frozen",
    "actual-plan-bytes-differs-from-frozen",
    "actual-launcher-receipt-absent",
    "actual-launcher-receipt-forged-pass",
    "actual-receipt-references-another-startup",
    "selected-operation-changed",
    "selected-argument-hash-changed",
    "selected-target-hash-changed",
    "canonical-request-plan-b-launcher-plan-a",
    "target-reopens-plan-b",
    "bootstrap-attestation-after-dispatch",
    "route-event-before-plan-admission",
    "reservation-release-before-plan-admission",
    "controller-before-plan-admission",
    "historical-f37-binding-used-in-v6",
    "historical-v5-profile-used-in-v6",
    "plan-binding-omitted-from-authorization",
    "plan-binding-omitted-from-post-freeze",
    "plan-binding-omitted-from-freeze",
    "plan-binding-omitted-from-preledger",
    "raw-private-plan-path-published",
    "private-environment-value-published",
    "rewrite-counter-forged-zero",
    "parent-fsync-proof-omitted",
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _is_hash(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _is_sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _strict(value: Mapping[str, Any], cls: type, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {item.name for item in fields(cls)}:
        raise M336K2ProtocolError(f"M336K13 {label} fields changed")
    return dict(value)


def _path_identity(value: str | Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        raise M336K2ProtocolError("M336K13 private path is not absolute")
    return content_hash(
        {
            "identity_kind": "NORMALIZED_ABSOLUTE_PRIVATE_PATH",
            "normalized_path": os.path.normcase(os.path.realpath(os.fspath(path))),
        }
    )


def _binding_hash(path_value: str | Path, content_digest: str) -> str:
    return content_hash(
        {
            "path_identity_hash": _path_identity(path_value),
            "content_hash": content_digest,
        }
    )


def _normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(value)))


def _plan_bytes(plan: M336K5PythonInvocationPlan) -> bytes:
    return (canonical_json(plan.canonical_object()) + "\n").encode("utf-8")


def _path_roles(plan: M336K5PythonInvocationPlan, plan_path: Path) -> dict[str, str]:
    validate, execute = plan.validate_arguments, plan.execute_arguments
    if (
        len(validate) != 5
        or validate[0] != "--request"
        or validate[2] != "--validate-only"
        or validate[3] != "--validation-receipt"
        or len(execute) != 6
        or execute[0] != "--request"
        or execute[2] != "--post-freeze-validation-receipt"
        or execute[4] != "--reservation-release-receipt"
    ):
        raise M336K2ProtocolError("M336K13 operation argument shape changed")
    values = {
        "PRIVATE_PLAN_FILE": str(plan_path.resolve(strict=False)),
        "FINAL_REQUEST": validate[1],
        "POST_FREEZE_VALIDATION_RECEIPT": validate[4],
        "RESERVATION_RELEASE_RECEIPT": execute[5],
        "VALIDATE_STARTUP_RECEIPT": plan.validate_startup_receipt,
        "EXECUTE_STARTUP_RECEIPT": plan.execute_startup_receipt,
    }
    if (
        execute[1] != values["FINAL_REQUEST"]
        or execute[3] != values["POST_FREEZE_VALIDATION_RECEIPT"]
    ):
        raise M336K2ProtocolError("M336K13 operation path roles diverged")
    normalized = tuple(
        os.path.normcase(os.path.realpath(value)) for value in values.values()
    )
    if any(not Path(value).is_absolute() for value in values.values()) or len(
        set(normalized)
    ) != len(normalized):
        raise M336K2ProtocolError("M336K13 private path roles collide")
    return values


@dataclass(frozen=True)
class M336K13FinalControllerPlanTemplate:
    schema_version: int
    contract_role: str
    execution_scope: str
    profile_id: str
    profile_hash: str
    process_role: str
    platform_role: str
    target_kind: str
    target_repository_path: str
    target_source_hash: str
    bootstrap_repository_path: str
    bootstrap_source_hash: str
    outer_interpreter_arguments: tuple[str, ...]
    outer_interpreter_argument_hash: str
    validate_operation_shape: tuple[str, ...]
    execute_operation_shape: tuple[str, ...]
    validate_argument_roles: tuple[str, ...]
    execute_argument_roles: tuple[str, ...]
    startup_receipt_role_tuple: tuple[str, ...]
    path_role_tuple: tuple[str, ...]
    path_uniqueness_required: bool
    same_request_path_required: bool
    same_validation_receipt_path_required: bool
    same_plan_file_required: bool
    plan_write_once_required: bool
    plan_rewrite_after_freeze_forbidden: bool
    actual_launcher_attestation_required: bool
    template_hash: str

    ROLE: ClassVar[str] = "M336K13_FINAL_CONTROLLER_PLAN_TEMPLATE"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("template_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "template_hash": self.template_hash}

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.profile_id)
        booleans = (
            self.path_uniqueness_required,
            self.same_request_path_required,
            self.same_validation_receipt_path_required,
            self.same_plan_file_required,
            self.plan_write_once_required,
            self.plan_rewrite_after_freeze_forbidden,
            self.actual_launcher_attestation_required,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or self.profile_id != M336K13_PROFILE_ID
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
            or self.profile_hash != profile.profile_hash
            or (self.process_role, self.platform_role, self.target_kind)
            != ("FINAL_CONTROLLER", "WINDOWS", "SCRIPT")
            or self.target_repository_path != M336K13_TARGET_REPOSITORY_PATH
            or self.bootstrap_repository_path != M336K13_BOOTSTRAP_REPOSITORY_PATH
            or self.outer_interpreter_arguments != M336K5_REQUIRED_INTERPRETER_ARGUMENTS
            or self.outer_interpreter_argument_hash
            != content_hash(M336K5_REQUIRED_INTERPRETER_ARGUMENTS)
            or self.validate_operation_shape != M336K13_VALIDATE_SHAPE
            or self.execute_operation_shape != M336K13_EXECUTE_SHAPE
            or self.validate_argument_roles != M336K13_VALIDATE_ARGUMENT_ROLES
            or self.execute_argument_roles != M336K13_EXECUTE_ARGUMENT_ROLES
            or self.startup_receipt_role_tuple
            != ("VALIDATE_STARTUP_RECEIPT", "EXECUTE_STARTUP_RECEIPT")
            or self.path_role_tuple != M336K13_PATH_ROLES
            or any(value is not True for value in booleans)
            or not _is_hash(self.target_source_hash)
            or not _is_hash(self.bootstrap_source_hash)
            or self.template_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 public plan template is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        row = _strict(value, cls, "public plan template")
        for name in (
            "outer_interpreter_arguments",
            "validate_operation_shape",
            "execute_operation_shape",
            "validate_argument_roles",
            "execute_argument_roles",
            "startup_receipt_role_tuple",
            "path_role_tuple",
        ):
            row[name] = tuple(row[name])
        result = cls(**row)
        result.verify()
        return result


def build_m336k13_final_controller_plan_template(
    *,
    target_source_hash: str,
    bootstrap_source_hash: str,
    execution_scope: str = "OFFICIAL_CONTROLLER",
) -> M336K13FinalControllerPlanTemplate:
    profile = m336k_official_profile_registry().profile(M336K13_PROFILE_ID)
    body = {
        "schema_version": 1,
        "contract_role": M336K13FinalControllerPlanTemplate.ROLE,
        "execution_scope": execution_scope,
        "profile_id": profile.profile_id,
        "profile_hash": profile.profile_hash,
        "process_role": "FINAL_CONTROLLER",
        "platform_role": "WINDOWS",
        "target_kind": "SCRIPT",
        "target_repository_path": M336K13_TARGET_REPOSITORY_PATH,
        "target_source_hash": target_source_hash,
        "bootstrap_repository_path": M336K13_BOOTSTRAP_REPOSITORY_PATH,
        "bootstrap_source_hash": bootstrap_source_hash,
        "outer_interpreter_arguments": M336K5_REQUIRED_INTERPRETER_ARGUMENTS,
        "outer_interpreter_argument_hash": content_hash(
            M336K5_REQUIRED_INTERPRETER_ARGUMENTS
        ),
        "validate_operation_shape": M336K13_VALIDATE_SHAPE,
        "execute_operation_shape": M336K13_EXECUTE_SHAPE,
        "validate_argument_roles": M336K13_VALIDATE_ARGUMENT_ROLES,
        "execute_argument_roles": M336K13_EXECUTE_ARGUMENT_ROLES,
        "startup_receipt_role_tuple": (
            "VALIDATE_STARTUP_RECEIPT",
            "EXECUTE_STARTUP_RECEIPT",
        ),
        "path_role_tuple": M336K13_PATH_ROLES,
        "path_uniqueness_required": True,
        "same_request_path_required": True,
        "same_validation_receipt_path_required": True,
        "same_plan_file_required": True,
        "plan_write_once_required": True,
        "plan_rewrite_after_freeze_forbidden": True,
        "actual_launcher_attestation_required": True,
    }
    result = M336K13FinalControllerPlanTemplate(
        **body, template_hash=content_hash(body)
    )
    result.verify()
    return result


@dataclass(frozen=True)
class M336K13FinalControllerInvocationPlanV2:
    schema_version: int
    contract_role: str
    execution_scope: str
    public_template_hash: str
    exact_implementation_tip: str
    exact_qualification_sha: str
    active_profile_hash: str
    canonical_plan_body_hash: str
    canonical_plan_bytes_sha256: str
    invocation_plan_hash: str
    private_plan_file_identity_hash: str
    creation_operation: str
    creation_count: int
    write_count: int
    rewrite_count: int
    overwrite_count: int
    post_freeze_modification_count: int
    write_once_result: str
    parent_directory_fsync_result: str
    validate_request_path_identity_hash: str
    execute_request_path_identity_hash: str
    post_freeze_validation_receipt_path_identity_hash: str
    reservation_release_receipt_path_identity_hash: str
    validate_startup_receipt_path_identity_hash: str
    execute_startup_receipt_path_identity_hash: str
    path_uniqueness_count: int
    path_collision_count: int
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_PRIVATE_FINAL_CONTROLLER_INVOCATION_PLAN_V2"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith(("_hash", "_sha256"))
        )
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or not _is_sha(self.exact_implementation_tip)
            or not _is_sha(self.exact_qualification_sha)
            or self.exact_implementation_tip == self.exact_qualification_sha
            or any(not _is_hash(value) for value in hashes)
            or self.creation_operation != "O_CREAT|O_EXCL"
            or (self.creation_count, self.write_count, self.rewrite_count) != (1, 1, 0)
            or self.overwrite_count != 0
            or self.post_freeze_modification_count != 0
            or self.write_once_result != "PASS"
            or self.parent_directory_fsync_result != "PASS"
            or self.path_uniqueness_count != 6
            or self.path_collision_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 private plan lifecycle is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "private plan lifecycle"))
        result.verify()
        return result


def _fsync_parent(path: Path) -> None:
    """Flush the directory entry containing a newly-created plan."""
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x40000000,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    invalid = wintypes.HANDLE(-1).value
    if handle == invalid:
        raise OSError(ctypes.get_last_error(), "CreateFileW directory flush failed")
    try:
        # FlushFileBuffers rejects directory handles.  The user-mode native
        # operation with flags=0 is synchronous and flushes file-system data
        # and metadata; unlike FILE_DATA_SYNC_ONLY it is valid for directories.
        io_status = (ctypes.c_void_p * 2)()
        flush = ctypes.WinDLL("ntdll").NtFlushBuffersFileEx
        flush.argtypes = (
            wintypes.HANDLE,
            wintypes.ULONG,
            wintypes.LPVOID,
            wintypes.ULONG,
            wintypes.LPVOID,
        )
        flush.restype = ctypes.c_long
        status = flush(handle, 0, None, 0, ctypes.byref(io_status))
        if status != 0:
            raise OSError(status & 0xFFFFFFFF, "NtFlushBuffersFileEx directory failed")
    finally:
        kernel32.CloseHandle(handle)


def create_m336k13_final_controller_plan_once(
    *,
    plan: M336K5PythonInvocationPlan,
    plan_path: Path,
    template: M336K13FinalControllerPlanTemplate,
    exact_implementation_tip: str,
    exact_qualification_sha: str,
) -> M336K13FinalControllerInvocationPlanV2:
    """Exclusively create and durably bind the plan used by both operations."""
    template.verify()
    validate_m336k5_python_invocation(plan)
    if (
        not _is_sha(exact_implementation_tip)
        or not _is_sha(exact_qualification_sha)
        or exact_implementation_tip == exact_qualification_sha
    ):
        raise M336K2ProtocolError("M336K13 plan lineage is invalid")
    if (
        (plan.process_role, plan.platform_role, plan.target_kind)
        != (template.process_role, template.platform_role, template.target_kind)
        or plan.expected_target_source_hash != template.target_source_hash
        or plan.expected_bootstrap_source_hash != template.bootstrap_source_hash
        or _normalized_path(plan.target)
        != _normalized_path(Path(plan.repository) / template.target_repository_path)
        or _normalized_path(plan.bootstrap_script)
        != _normalized_path(Path(plan.repository) / template.bootstrap_repository_path)
    ):
        raise M336K2ProtocolError("M336K13 private plan does not match its template")
    target = plan_path.resolve(strict=False)
    if target.exists():
        raise FileExistsError("M336K13 invocation plan output must be fresh")
    roles = _path_roles(plan, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _plan_bytes(plan)
    with target.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_parent(target.parent)
    if target.read_bytes() != payload:
        raise M336K2ProtocolError("M336K13 invocation plan changed after creation")
    profile = m336k_official_profile_registry().profile(M336K13_PROFILE_ID)
    body = {
        "schema_version": 2,
        "contract_role": M336K13FinalControllerInvocationPlanV2.ROLE,
        "execution_scope": template.execution_scope,
        "public_template_hash": template.template_hash,
        "exact_implementation_tip": exact_implementation_tip,
        "exact_qualification_sha": exact_qualification_sha,
        "active_profile_hash": profile.profile_hash,
        "canonical_plan_body_hash": content_hash(plan._body()),
        "canonical_plan_bytes_sha256": bytes_hash(payload),
        "invocation_plan_hash": plan.invocation_plan_hash,
        "private_plan_file_identity_hash": _path_identity(target),
        "creation_operation": "O_CREAT|O_EXCL",
        "creation_count": 1,
        "write_count": 1,
        "rewrite_count": 0,
        "overwrite_count": 0,
        "post_freeze_modification_count": 0,
        "write_once_result": "PASS",
        "parent_directory_fsync_result": "PASS",
        "validate_request_path_identity_hash": _path_identity(roles["FINAL_REQUEST"]),
        "execute_request_path_identity_hash": _path_identity(roles["FINAL_REQUEST"]),
        "post_freeze_validation_receipt_path_identity_hash": _path_identity(
            roles["POST_FREEZE_VALIDATION_RECEIPT"]
        ),
        "reservation_release_receipt_path_identity_hash": _path_identity(
            roles["RESERVATION_RELEASE_RECEIPT"]
        ),
        "validate_startup_receipt_path_identity_hash": _path_identity(
            roles["VALIDATE_STARTUP_RECEIPT"]
        ),
        "execute_startup_receipt_path_identity_hash": _path_identity(
            roles["EXECUTE_STARTUP_RECEIPT"]
        ),
        "path_uniqueness_count": len(roles),
        "path_collision_count": 0,
        "status": "PASS",
    }
    result = M336K13FinalControllerInvocationPlanV2(
        **body, receipt_hash=content_hash(body)
    )
    result.verify()
    return result


@dataclass(frozen=True)
class M336K13FinalControllerPlanBindingReceipt:
    schema_version: int
    contract_role: str
    execution_scope: str
    public_template_hash: str
    exact_implementation_tip: str
    exact_qualification_sha: str
    active_profile_hash: str
    canonical_invocation_plan_hash: str
    canonical_plan_bytes_hash: str
    plan_file_identity_hash: str
    python_executable_binding_hash: str
    git_executable_binding_hash: str
    powershell_executable_binding_hash: str
    repository_identity_hash: str
    working_directory_identity_hash: str
    bootstrap_source_hash: str
    target_source_hash: str
    project_source_identity_hash: str
    startup_policy_hash: str
    sanitized_environment_hash: str
    validate_selected_argument_hash: str
    execute_selected_argument_hash: str
    validate_startup_destination_identity_hash: str
    execute_startup_destination_identity_hash: str
    final_request_destination_identity_hash: str
    post_freeze_validation_destination_identity_hash: str
    release_destination_identity_hash: str
    path_role_manifest_hash: str
    path_collision_count: int
    rewrite_count: int
    parent_directory_fsync_result: str
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_FINAL_CONTROLLER_PLAN_BINDING_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or not _is_sha(self.exact_implementation_tip)
            or not _is_sha(self.exact_qualification_sha)
            or self.exact_implementation_tip == self.exact_qualification_sha
            or any(not _is_hash(value) for value in hashes)
            or self.path_collision_count != 0
            or self.rewrite_count != 0
            or self.parent_directory_fsync_result != "PASS"
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 plan binding receipt is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "plan binding receipt"))
        result.verify()
        return result


def build_m336k13_final_controller_plan_binding(
    *,
    plan: M336K5PythonInvocationPlan,
    plan_path: Path,
    template: M336K13FinalControllerPlanTemplate,
    lifecycle: M336K13FinalControllerInvocationPlanV2,
) -> M336K13FinalControllerPlanBindingReceipt:
    template.verify()
    lifecycle.verify()
    validate_m336k5_python_invocation(plan)
    path = plan_path.resolve(strict=True)
    raw = path.read_bytes()
    roles = _path_roles(plan, path)
    lifecycle_path_relations = (
        lifecycle.validate_request_path_identity_hash
        == _path_identity(roles["FINAL_REQUEST"]),
        lifecycle.execute_request_path_identity_hash
        == _path_identity(roles["FINAL_REQUEST"]),
        lifecycle.post_freeze_validation_receipt_path_identity_hash
        == _path_identity(roles["POST_FREEZE_VALIDATION_RECEIPT"]),
        lifecycle.reservation_release_receipt_path_identity_hash
        == _path_identity(roles["RESERVATION_RELEASE_RECEIPT"]),
        lifecycle.validate_startup_receipt_path_identity_hash
        == _path_identity(roles["VALIDATE_STARTUP_RECEIPT"]),
        lifecycle.execute_startup_receipt_path_identity_hash
        == _path_identity(roles["EXECUTE_STARTUP_RECEIPT"]),
        lifecycle.canonical_plan_body_hash == content_hash(plan._body()),
    )
    if (
        raw != _plan_bytes(plan)
        or bytes_hash(raw) != lifecycle.canonical_plan_bytes_sha256
        or plan.invocation_plan_hash != lifecycle.invocation_plan_hash
        or _path_identity(path) != lifecycle.private_plan_file_identity_hash
        or template.target_source_hash != plan.expected_target_source_hash
        or template.bootstrap_source_hash != plan.expected_bootstrap_source_hash
        or _normalized_path(plan.target)
        != _normalized_path(Path(plan.repository) / template.target_repository_path)
        or _normalized_path(plan.bootstrap_script)
        != _normalized_path(Path(plan.repository) / template.bootstrap_repository_path)
        or template.profile_hash != lifecycle.active_profile_hash
        or template.template_hash != lifecycle.public_template_hash
        or template.execution_scope != lifecycle.execution_scope
        or not all(lifecycle_path_relations)
    ):
        raise M336K2ProtocolError("M336K13 exact private plan binding changed")
    powershell_hash = (
        bytes_hash(Path(plan.powershell_executable).resolve(strict=True).read_bytes())
        if plan.powershell_executable is not None
        else content_hash("NO_POWERSHELL_EXECUTABLE")
    )
    manifest = tuple((role, _path_identity(value)) for role, value in roles.items())
    body = {
        "schema_version": 1,
        "contract_role": M336K13FinalControllerPlanBindingReceipt.ROLE,
        "execution_scope": template.execution_scope,
        "public_template_hash": template.template_hash,
        "exact_implementation_tip": lifecycle.exact_implementation_tip,
        "exact_qualification_sha": lifecycle.exact_qualification_sha,
        "active_profile_hash": lifecycle.active_profile_hash,
        "canonical_invocation_plan_hash": plan.invocation_plan_hash,
        "canonical_plan_bytes_hash": bytes_hash(raw),
        "plan_file_identity_hash": _path_identity(path),
        "python_executable_binding_hash": content_hash(
            {
                "path_and_bytes_binding_hash": _binding_hash(
                    plan.python_executable, plan.expected_python_executable_hash
                ),
                "implementation": plan.expected_python_implementation,
                "version": plan.expected_python_version,
                "environment_prefix_identity_hash": _path_identity(
                    plan.expected_environment_prefix
                ),
            }
        ),
        "git_executable_binding_hash": _binding_hash(
            plan.git_executable,
            bytes_hash(Path(plan.git_executable).resolve(strict=True).read_bytes()),
        ),
        "powershell_executable_binding_hash": _binding_hash(
            plan.powershell_executable, powershell_hash
        )
        if plan.powershell_executable is not None
        else content_hash("NO_POWERSHELL_BINDING"),
        "repository_identity_hash": _path_identity(plan.repository),
        "working_directory_identity_hash": _path_identity(plan.working_directory),
        "bootstrap_source_hash": plan.expected_bootstrap_source_hash,
        "target_source_hash": plan.expected_target_source_hash,
        "project_source_identity_hash": plan.expected_project_source_identity,
        "startup_policy_hash": plan.startup_policy.policy_hash,
        "sanitized_environment_hash": plan.sanitized_environment.environment_hash,
        "validate_selected_argument_hash": content_hash(plan.validate_arguments),
        "execute_selected_argument_hash": content_hash(plan.execute_arguments),
        "validate_startup_destination_identity_hash": _path_identity(
            plan.validate_startup_receipt
        ),
        "execute_startup_destination_identity_hash": _path_identity(
            plan.execute_startup_receipt
        ),
        "final_request_destination_identity_hash": _path_identity(
            roles["FINAL_REQUEST"]
        ),
        "post_freeze_validation_destination_identity_hash": _path_identity(
            roles["POST_FREEZE_VALIDATION_RECEIPT"]
        ),
        "release_destination_identity_hash": _path_identity(
            roles["RESERVATION_RELEASE_RECEIPT"]
        ),
        "path_role_manifest_hash": content_hash(manifest),
        "path_collision_count": 0,
        "rewrite_count": lifecycle.rewrite_count,
        "parent_directory_fsync_result": lifecycle.parent_directory_fsync_result,
        "status": "PASS",
    }
    result = M336K13FinalControllerPlanBindingReceipt(
        **body, receipt_hash=content_hash(body)
    )
    result.verify()
    return result


@dataclass(frozen=True)
class M336K13ActualLauncherPlanReceipt:
    schema_version: int
    contract_role: str
    execution_scope: str
    actual_invocation_plan_hash: str
    actual_plan_bytes_hash: str
    actual_plan_file_identity_hash: str
    selected_operation: str
    selected_target_kind: str
    selected_target_source_hash: str
    selected_operation_argument_hash: str
    startup_receipt_hash: str
    startup_policy_hash: str
    sanitized_environment_hash: str
    project_source_identity_hash: str
    interpreter_binding_hash: str
    outer_invocation_argument_hash: str
    forbidden_variable_occurrence_count: int
    unexpected_variable_count: int
    attestation_before_target_dispatch: bool
    status: str
    receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_ACTUAL_LAUNCHER_PLAN_RECEIPT"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "receipt_hash": self.receipt_hash}

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash")
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or any(not _is_hash(value) for value in hashes)
            or self.selected_operation not in {"validate", "execute"}
            or self.selected_target_kind != "SCRIPT"
            or self.forbidden_variable_occurrence_count != 0
            or self.unexpected_variable_count != 0
            or self.attestation_before_target_dispatch is not True
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 actual launcher receipt is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "actual launcher receipt"))
        result.verify()
        return result


M336K13_ACTUAL_LAUNCHER_RECEIPT_SCHEMA_HASH = content_hash(
    {
        "contract_role": M336K13ActualLauncherPlanReceipt.ROLE,
        "schema_version": 1,
        "fields": tuple(item.name for item in fields(M336K13ActualLauncherPlanReceipt)),
        "producer": M336K13_BOOTSTRAP_REPOSITORY_PATH,
        "write_order": "BEFORE_TARGET_DISPATCH",
    }
)


@dataclass(frozen=True)
class M336K13ActualLauncherPlanReceiptSchema:
    schema_version: int
    contract_role: str
    receipt_contract_role: str
    receipt_fields: tuple[str, ...]
    producer_repository_path: str
    write_order: str
    schema_hash: str

    ROLE: ClassVar[str] = "M336K13_ACTUAL_LAUNCHER_PLAN_RECEIPT_SCHEMA"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("schema_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "schema_hash": self.schema_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.receipt_contract_role != M336K13ActualLauncherPlanReceipt.ROLE
            or self.receipt_fields
            != tuple(item.name for item in fields(M336K13ActualLauncherPlanReceipt))
            or self.producer_repository_path != M336K13_BOOTSTRAP_REPOSITORY_PATH
            or self.write_order != "BEFORE_TARGET_DISPATCH"
            or self.schema_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K13 actual launcher receipt schema is invalid"
            )

    @classmethod
    def build(cls) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "receipt_contract_role": M336K13ActualLauncherPlanReceipt.ROLE,
            "receipt_fields": tuple(
                item.name for item in fields(M336K13ActualLauncherPlanReceipt)
            ),
            "producer_repository_path": M336K13_BOOTSTRAP_REPOSITORY_PATH,
            "write_order": "BEFORE_TARGET_DISPATCH",
        }
        result = cls(**body, schema_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        row = _strict(value, cls, "actual launcher receipt schema")
        row["receipt_fields"] = tuple(row["receipt_fields"])
        result = cls(**row)
        result.verify()
        return result


M336K13_ACTUAL_LAUNCHER_RECEIPT_SCHEMA_HASH = (
    M336K13ActualLauncherPlanReceiptSchema.build().schema_hash
)


@dataclass(frozen=True)
class M336K13FinalControllerPlanLifecyclePolicy:
    schema_version: int
    contract_role: str
    creation_operation: str
    exclusive_create_required: bool
    exact_write_count: int
    maximum_rewrite_count: int
    maximum_overwrite_count: int
    parent_directory_fsync_required: bool
    post_freeze_modification_forbidden: bool
    same_plan_file_for_validate_execute_required: bool
    freeze_sha_in_private_path_forbidden: bool
    policy_hash: str

    ROLE: ClassVar[str] = "M336K13_FINAL_CONTROLLER_PLAN_LIFECYCLE_POLICY"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("policy_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "policy_hash": self.policy_hash}

    def verify(self) -> None:
        required = (
            self.exclusive_create_required,
            self.parent_directory_fsync_required,
            self.post_freeze_modification_forbidden,
            self.same_plan_file_for_validate_execute_required,
            self.freeze_sha_in_private_path_forbidden,
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.creation_operation != "O_CREAT|O_EXCL"
            or (self.exact_write_count, self.maximum_rewrite_count) != (1, 0)
            or self.maximum_overwrite_count != 0
            or any(value is not True for value in required)
            or self.policy_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K13 final-controller plan lifecycle policy is invalid"
            )

    @classmethod
    def build(cls) -> Self:
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "creation_operation": "O_CREAT|O_EXCL",
            "exclusive_create_required": True,
            "exact_write_count": 1,
            "maximum_rewrite_count": 0,
            "maximum_overwrite_count": 0,
            "parent_directory_fsync_required": True,
            "post_freeze_modification_forbidden": True,
            "same_plan_file_for_validate_execute_required": True,
            "freeze_sha_in_private_path_forbidden": True,
        }
        result = cls(**body, policy_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "plan lifecycle policy"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13FinalControllerPlanPathRoleManifest:
    schema_version: int
    contract_role: str
    execution_scope: str
    public_template_hash: str
    plan_lifecycle_receipt_hash: str
    plan_binding_receipt_hash: str
    bound_path_role_identities: tuple[tuple[str, str], ...]
    launcher_receipt_roles: tuple[str, ...]
    bound_path_role_count: int
    path_collision_count: int
    raw_private_path_count: int
    manifest_hash: str

    ROLE: ClassVar[str] = "M336K13_FINAL_CONTROLLER_PLAN_PATH_ROLE_MANIFEST"

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "manifest_hash": self.manifest_hash}

    def verify(self) -> None:
        roles = tuple(role for role, _identity in self.bound_path_role_identities)
        identities = tuple(
            identity for _role, identity in self.bound_path_role_identities
        )
        if (
            self.schema_version != 1
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or roles
            != (
                "PRIVATE_PLAN_FILE",
                "FINAL_REQUEST",
                "POST_FREEZE_VALIDATION_RECEIPT",
                "RESERVATION_RELEASE_RECEIPT",
                "VALIDATE_STARTUP_RECEIPT",
                "EXECUTE_STARTUP_RECEIPT",
            )
            or self.launcher_receipt_roles
            != (
                "VALIDATE_ACTUAL_LAUNCHER_RECEIPT",
                "EXECUTE_ACTUAL_LAUNCHER_RECEIPT",
            )
            or self.bound_path_role_count != len(roles)
            or len(set(identities)) != len(identities)
            or any(not _is_hash(value) for value in identities)
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.path_collision_count != 0
            or self.raw_private_path_count != 0
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError(
                "M336K13 final-controller plan path-role manifest is invalid"
            )

    @classmethod
    def build(
        cls,
        *,
        template: M336K13FinalControllerPlanTemplate,
        lifecycle: M336K13FinalControllerInvocationPlanV2,
        binding: M336K13FinalControllerPlanBindingReceipt,
    ) -> Self:
        template.verify()
        lifecycle.verify()
        binding.verify()
        if (
            template.template_hash != lifecycle.public_template_hash
            or template.template_hash != binding.public_template_hash
            or template.execution_scope != lifecycle.execution_scope
            or template.execution_scope != binding.execution_scope
            or lifecycle.exact_implementation_tip != binding.exact_implementation_tip
            or lifecycle.exact_qualification_sha != binding.exact_qualification_sha
            or lifecycle.active_profile_hash != binding.active_profile_hash
        ):
            raise M336K2ProtocolError("M336K13 plan path-role source closure changed")
        identities = (
            ("PRIVATE_PLAN_FILE", binding.plan_file_identity_hash),
            (
                "FINAL_REQUEST",
                binding.final_request_destination_identity_hash,
            ),
            (
                "POST_FREEZE_VALIDATION_RECEIPT",
                binding.post_freeze_validation_destination_identity_hash,
            ),
            (
                "RESERVATION_RELEASE_RECEIPT",
                binding.release_destination_identity_hash,
            ),
            (
                "VALIDATE_STARTUP_RECEIPT",
                binding.validate_startup_destination_identity_hash,
            ),
            (
                "EXECUTE_STARTUP_RECEIPT",
                binding.execute_startup_destination_identity_hash,
            ),
        )
        if content_hash(identities) != binding.path_role_manifest_hash:
            raise M336K2ProtocolError("M336K13 path-role identity-set hash changed")
        body = {
            "schema_version": 1,
            "contract_role": cls.ROLE,
            "execution_scope": binding.execution_scope,
            "public_template_hash": template.template_hash,
            "plan_lifecycle_receipt_hash": lifecycle.receipt_hash,
            "plan_binding_receipt_hash": binding.receipt_hash,
            "bound_path_role_identities": identities,
            "launcher_receipt_roles": (
                "VALIDATE_ACTUAL_LAUNCHER_RECEIPT",
                "EXECUTE_ACTUAL_LAUNCHER_RECEIPT",
            ),
            "bound_path_role_count": len(identities),
            "path_collision_count": lifecycle.path_collision_count,
            "raw_private_path_count": 0,
        }
        result = cls(**body, manifest_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        row = _strict(value, cls, "plan path-role manifest")
        row["bound_path_role_identities"] = tuple(
            tuple(item) for item in row["bound_path_role_identities"]
        )
        row["launcher_receipt_roles"] = tuple(row["launcher_receipt_roles"])
        result = cls(**row)
        result.verify()
        return result


M336K13_PLAN_BINDING_CONSUMERS = frozenset(
    {
        "effective_environment_binding",
        "controller_executable_binding",
        "official_executable_binding_receipt",
        "native_execution_capsule",
        "native_route_manifest",
        "native_stage_plan_binding",
        "final_authorization",
        "post_freeze_input_bundle",
        "freeze_manifest",
        "final_request",
        "controller_admission_receipt",
        "preledger_receipt",
        "route_context",
    }
)


def verify_m336k13_final_controller_plan_binding(
    *,
    plan_path: Path,
    template: M336K13FinalControllerPlanTemplate,
    lifecycle: M336K13FinalControllerInvocationPlanV2,
    binding: M336K13FinalControllerPlanBindingReceipt,
    actual_launcher_receipt: M336K13ActualLauncherPlanReceipt | None = None,
    selected_operation: str | None = None,
    expected_consumer_binding_hashes: Mapping[str, str] | None = None,
) -> M336K5PythonInvocationPlan:
    """Strong admission gate; deliberately has no equal-lineage-SHA bypass."""
    template.verify()
    lifecycle.verify()
    binding.verify()
    path = plan_path.resolve(strict=True)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError(
            "M336K13 invocation plan bytes are invalid"
        ) from error
    plan = M336K5PythonInvocationPlan.from_dict(value)
    validate_m336k5_python_invocation(plan)
    rebuilt = build_m336k13_final_controller_plan_binding(
        plan=plan, plan_path=path, template=template, lifecycle=lifecycle
    )
    if rebuilt != binding:
        raise M336K2ProtocolError("M336K13 final-controller plan binding changed")
    if expected_consumer_binding_hashes is not None and (
        set(expected_consumer_binding_hashes) != M336K13_PLAN_BINDING_CONSUMERS
        or any(
            value != binding.receipt_hash
            for value in expected_consumer_binding_hashes.values()
        )
    ):
        raise M336K2ProtocolError("M336K13 plan consumer binding changed")
    if actual_launcher_receipt is not None:
        actual_launcher_receipt.verify()
        operation = selected_operation or actual_launcher_receipt.selected_operation
        if operation not in {"validate", "execute"}:
            raise M336K2ProtocolError("M336K13 selected operation changed")
        arguments = (
            plan.validate_arguments
            if operation == "validate"
            else plan.execute_arguments
        )
        startup_path = (
            plan.validate_startup_receipt
            if operation == "validate"
            else plan.execute_startup_receipt
        )
        startup_value = json.loads(Path(startup_path).resolve(strict=True).read_bytes())
        expected_interpreter_binding_hash = content_hash(
            {
                "implementation": plan.expected_python_implementation,
                "version": plan.expected_python_version,
                "executable_hash": plan.expected_python_executable_hash,
                "prefix_hash": bytes_hash(
                    _normalized_path(plan.expected_environment_prefix).encode("utf-8")
                ),
            }
        )
        expected_outer_invocation_argument_hash = content_hash(
            (
                "-s",
                "-B",
                _normalized_path(plan.bootstrap_script),
                "--invocation-plan",
                _normalized_path(path),
                "--operation",
                operation,
            )
        )
        if (
            actual_launcher_receipt.execution_scope != binding.execution_scope
            or actual_launcher_receipt.actual_invocation_plan_hash
            != binding.canonical_invocation_plan_hash
            or actual_launcher_receipt.actual_plan_bytes_hash
            != binding.canonical_plan_bytes_hash
            or actual_launcher_receipt.actual_plan_file_identity_hash
            != binding.plan_file_identity_hash
            or actual_launcher_receipt.selected_operation != operation
            or actual_launcher_receipt.selected_target_kind != plan.target_kind
            or actual_launcher_receipt.selected_target_source_hash
            != binding.target_source_hash
            or actual_launcher_receipt.selected_operation_argument_hash
            != content_hash(arguments)
            or actual_launcher_receipt.startup_receipt_hash
            != startup_value.get("receipt_hash")
            or actual_launcher_receipt.startup_policy_hash
            != binding.startup_policy_hash
            or actual_launcher_receipt.sanitized_environment_hash
            != binding.sanitized_environment_hash
            or actual_launcher_receipt.project_source_identity_hash
            != binding.project_source_identity_hash
            or actual_launcher_receipt.interpreter_binding_hash
            != expected_interpreter_binding_hash
            or actual_launcher_receipt.outer_invocation_argument_hash
            != expected_outer_invocation_argument_hash
        ):
            raise M336K2ProtocolError("M336K13 actual/frozen plan admission changed")
    elif selected_operation is not None:
        raise M336K2ProtocolError("M336K13 actual launcher receipt is absent")
    return plan


@dataclass(frozen=True)
class M336K13PostFreezeInputBundle(M336K12PostFreezeInputBundle):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_POST_FREEZE_INPUT_BUNDLE_V6"

    def verify(self) -> None:
        if (
            self.schema_version != 6
            or self.contract_role != self.ROLE
            or self.acquisition_policy_hash != self.official_acquisition_policy_hash
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.bundle_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 post-freeze bundle is invalid")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = {"schema_version": 6, "contract_role": cls.ROLE, **values}
        if set(body) != {field.name for field in fields(cls)} - {"bundle_hash"}:
            raise M336K2ProtocolError("M336K13 post-freeze bundle inputs changed")
        result = cls(**body, bundle_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "post-freeze bundle"))
        result.verify()
        return result


def _copy_body(value: Any, *, excluded: set[str]) -> dict[str, Any]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(type(value))
        if field.name not in excluded
    }


@dataclass(frozen=True)
class M336K13EffectiveEnvironmentBinding(M336K11EffectiveEnvironmentBinding):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_EFFECTIVE_ENVIRONMENT_BINDING"

    def verify(self) -> None:
        hashes = tuple(
            value
            for name, value in self.canonical_object().items()
            if name.endswith("_hash") or name == "project_source_identity"
        )
        passed = (
            self.expected_sanitized_environment_hash
            == self.actual_startup_receipt_sanitized_environment_hash
            and self.forbidden_variable_occurrence_count == 0
            and self.unexpected_variable_count == 0
            and self.actual_environment_equals_invocation_plan
        )
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or any(not _is_hash(item) for item in hashes)
            or self.status != ("PASS" if passed else "FAIL")
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 effective environment is invalid")

    @classmethod
    def build(
        cls, base: M336K11EffectiveEnvironmentBinding, plan_binding_hash: str
    ) -> Self:
        base.verify()
        body = {
            **_copy_body(
                base, excluded={"schema_version", "contract_role", "receipt_hash"}
            ),
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "final_controller_plan_binding_receipt_hash": plan_binding_hash,
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "effective environment"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13NativeStagePlanBinding(M336K12NativeStagePlanBinding):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_NATIVE_STAGE_PLAN_BINDING"

    def verify(self) -> None:
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or not _is_sha(self.exact_implementation_tip)
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.plan_binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 native stage plan binding is invalid")

    @classmethod
    def build(cls, base: M336K12NativeStagePlanBinding, plan_binding_hash: str) -> Self:
        base.verify()
        body = {
            **_copy_body(
                base, excluded={"schema_version", "contract_role", "plan_binding_hash"}
            ),
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "final_controller_plan_binding_receipt_hash": plan_binding_hash,
        }
        result = cls(**body, plan_binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        row = _strict(value, cls, "native stage plan binding")
        row["event_sequence"] = tuple(row["event_sequence"])
        row["dispatch_hashes"] = tuple(row["dispatch_hashes"])
        result = cls(**row)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13NativeExecutionCapsuleReceipt(M336K12NativeExecutionCapsuleReceipt):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_NATIVE_EXECUTION_CAPSULE_RECEIPT_V4"

    def verify(self) -> None:
        if (
            self.schema_version != 4
            or self.contract_role != self.ROLE
            or self.execution_scope not in M336K13_EXECUTION_SCOPES
            or not _is_sha(self.exact_implementation_tip)
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 native execution capsule is invalid")

    @classmethod
    def build(
        cls, base: M336K12NativeExecutionCapsuleReceipt, plan_binding_hash: str
    ) -> Self:
        base.verify()
        body = {
            **_copy_body(
                base, excluded={"schema_version", "contract_role", "receipt_hash"}
            ),
            "schema_version": 4,
            "contract_role": cls.ROLE,
            "final_controller_plan_binding_receipt_hash": plan_binding_hash,
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "native execution capsule"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13OfficialControllerExecutableBinding(
    M336K12OfficialControllerExecutableBinding
):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_OFFICIAL_CONTROLLER_EXECUTABLE_BINDING"

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        if (
            self.schema_version != 3
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K13_PROFILE_ID
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
            or self.official_profile_hash != profile.profile_hash
            or not _is_sha(self.exact_implementation_tip)
            or self.native_command_contract_hash != self.dispatch_contract_hash
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.binding_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 official executable binding is invalid")

    @classmethod
    def build(
        cls,
        *,
        base_binding: M336K12OfficialControllerExecutableBinding,
        profile: M336KOfficialRouteProfile,
        capsule: M336K13NativeExecutionCapsuleReceipt,
        plan_binding: M336K13NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
        final_controller_plan_binding_receipt_hash: str,
    ) -> Self:
        base_binding.verify()
        profile.verify()
        capsule.verify()
        plan_binding.verify()
        parity.verify()
        body = {
            **_copy_body(
                base_binding,
                excluded={
                    "schema_version",
                    "contract_role",
                    "official_profile_id",
                    "official_profile_hash",
                    "native_stage_plan_binding_hash",
                    "native_execution_capsule_receipt_hash",
                    "binding_hash",
                },
            ),
            "schema_version": 3,
            "contract_role": cls.ROLE,
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "final_controller_plan_binding_receipt_hash": (
                final_controller_plan_binding_receipt_hash
            ),
        }
        result = cls(**body, binding_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "official executable binding"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13NativeRouteManifest(M336K12NativeRouteManifest):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_ACTIVE_NATIVE_ROUTE_MANIFEST"

    def verify(self) -> None:
        profile = m336k_official_profile_registry().profile(self.official_profile_id)
        if (
            self.schema_version != 3
            or self.contract_role != self.ROLE
            or self.execution_scope != OFFICIAL_CONTROLLER
            or self.official_profile_id != M336K13_PROFILE_ID
            or profile.profile_status
            is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
            or self.official_profile_hash != profile.profile_hash
            or self.route_version != profile.route_version
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.status != "PASS"
            or self.manifest_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 active native route is invalid")

    @classmethod
    def build(
        cls,
        *,
        profile: M336KOfficialRouteProfile,
        binding: M336K13OfficialControllerExecutableBinding,
        capsule: M336K13NativeExecutionCapsuleReceipt,
        plan_binding: M336K13NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
        final_controller_plan_binding_receipt_hash: str,
    ) -> Self:
        profile.verify()
        binding.verify()
        capsule.verify()
        plan_binding.verify()
        parity.verify()
        body = {
            "schema_version": 3,
            "contract_role": cls.ROLE,
            "execution_scope": OFFICIAL_CONTROLLER,
            "route_version": profile.route_version,
            "official_profile_id": profile.profile_id,
            "official_profile_hash": profile.profile_hash,
            "route_registry_hash": binding.route_registry_hash,
            "typed_route_manifest_hash": binding.typed_route_manifest_hash,
            "executable_dependency_manifest_hash": (
                binding.executable_dependency_manifest_hash
            ),
            "effective_environment_binding_receipt_hash": (
                binding.effective_environment_binding_receipt_hash
            ),
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "static_startup_policy_hash": binding.static_startup_policy_hash,
            "sanitized_environment_policy_hash": (
                binding.sanitized_environment_policy_hash
            ),
            "expected_windows_sanitized_environment_hash": (
                binding.expected_windows_sanitized_environment_hash
            ),
            "status": "PASS",
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "dispatch_contract_hash": capsule.dispatch_contract_hash,
            "final_controller_plan_binding_receipt_hash": (
                final_controller_plan_binding_receipt_hash
            ),
        }
        result = cls(**body, manifest_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "active native route"))
        result.verify()
        return result


@dataclass(frozen=True)
class M336K13OfficialExecutableBindingReceipt(M336K12OfficialExecutableBindingReceipt):
    final_controller_plan_binding_receipt_hash: str

    ROLE: ClassVar[str] = "M336K13_OFFICIAL_EXECUTABLE_BINDING_RECEIPT"

    def verify(self) -> None:
        if (
            self.schema_version != 2
            or self.contract_role != self.ROLE
            or any(
                not _is_hash(value)
                for name, value in self.canonical_object().items()
                if name.endswith("_hash")
            )
            or self.executable_semantic_mismatch_count != 0
            or self.dispatch_semantic_mismatch_count != 0
            or self.status != "PASS"
            or self.receipt_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K13 executable binding receipt is invalid")

    @classmethod
    def build(
        cls,
        *,
        executable_semantic_anchor_hash: str,
        executable_semantic_mismatch_count: int,
        binding: M336K13OfficialControllerExecutableBinding,
        capsule: M336K13NativeExecutionCapsuleReceipt,
        route: M336K13NativeRouteManifest,
        plan_binding: M336K13NativeStagePlanBinding,
        parity: M336K12ProducerConsumerParityReceipt,
        final_controller_plan_binding_receipt_hash: str,
    ) -> Self:
        binding.verify()
        capsule.verify()
        route.verify()
        plan_binding.verify()
        parity.verify()
        if not _is_hash(executable_semantic_anchor_hash):
            raise M336K2ProtocolError("M336K13 executable semantic anchor is invalid")
        direct_bindings = (
            binding.final_controller_plan_binding_receipt_hash,
            capsule.final_controller_plan_binding_receipt_hash,
            route.final_controller_plan_binding_receipt_hash,
            plan_binding.final_controller_plan_binding_receipt_hash,
        )
        mismatches = sum(
            (
                binding.native_stage_plan_binding_hash
                != plan_binding.plan_binding_hash,
                capsule.native_stage_plan_binding_hash
                != plan_binding.plan_binding_hash,
                route.native_stage_plan_binding_hash != plan_binding.plan_binding_hash,
                binding.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                capsule.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                route.producer_consumer_parity_receipt_hash != parity.receipt_hash,
                binding.dispatch_contract_hash != capsule.dispatch_contract_hash,
                route.dispatch_contract_hash != capsule.dispatch_contract_hash,
                *(
                    value != final_controller_plan_binding_receipt_hash
                    for value in direct_bindings
                ),
            )
        )
        body = {
            "schema_version": 2,
            "contract_role": cls.ROLE,
            "executable_semantic_anchor_hash": executable_semantic_anchor_hash,
            "official_controller_executable_binding_hash": binding.binding_hash,
            "native_execution_capsule_receipt_hash": capsule.receipt_hash,
            "native_route_manifest_hash": route.manifest_hash,
            "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
            "producer_consumer_parity_receipt_hash": parity.receipt_hash,
            "dispatch_contract_hash": capsule.dispatch_contract_hash,
            "executable_semantic_mismatch_count": executable_semantic_mismatch_count,
            "dispatch_semantic_mismatch_count": mismatches,
            "status": (
                "PASS"
                if mismatches == 0 and executable_semantic_mismatch_count == 0
                else "FAIL"
            ),
            "final_controller_plan_binding_receipt_hash": (
                final_controller_plan_binding_receipt_hash
            ),
        }
        result = cls(**body, receipt_hash=content_hash(body))
        result.verify()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        result = cls(**_strict(value, cls, "executable binding receipt"))
        result.verify()
        return result
