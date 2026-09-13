"""Canonical V3 request and side-effect-free validation for M-33.6k.7."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaRemoteTokenClass,
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336j_registry import build_m336j_route_registry
from ai_brain.stage3.acquisition.m336j_transport import (
    M336J_DEFAULT_TREE_TRANSFER_LIMITS,
    KarinaPrivateSshTransport,
    invoke_karina_command,
    parse_bound_json_response,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    executable_dependency_manifest_from_dict,
    verify_m336k2_executable_handles,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k5_authorization import M336K5FinalAuthorization
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K7_PROTOCOL_RUN_ID,
    M336K5RouteIdentityBundle,
)
from ai_brain.stage3.acquisition.m336k5_registry import build_m336k5_route_registry
from ai_brain.stage3.acquisition.m336k5_request import (
    _verify_destination_set,
    _verify_identity_policy_components,
)
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5StorageReservationReceipt,
    _allocated_size,
    _filesystem_identity,
    _free_inodes,
    _system_memory,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupPolicy,
    M336K5PythonStartupReceipt,
    build_m336k5_karina_invocation,
    build_m336k5_python_startup_policy,
    startup_receipt_from_path,
)
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleLivenessReceipt,
    M336K6PrivateExecutionCapsule,
    M336K6PublicExecutionCapsuleReceipt,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
    M336K7PostFreezeInputBundle,
    M336K7ResourceBudgetPolicy,
    M336K7ResourceGateReceipt,
    M336K7ResourceObservationReceipt,
    M336K7StorageReservationReleaseReceipt,
    storage_reservation_from_dict,
    verify_m336k7_capsule_compatibility_binding,
    verify_m336k7_resource_gate_binding,
)
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7_FREEZE_MANIFEST_CONTRACT_HASH,
    M336K7CommittedFreezeAttestation,
    M336K7FreezeManifest,
)

M336K7_FINAL_REQUEST_CONTRACT = {
    "schema_version": 3,
    "contract_role": "M336K7_CANONICAL_FINAL_ROUTE_REQUEST_V3",
    "identity_derivation": (
        "typed_final_authorization",
        "typed_f32_freeze_manifest",
        "route_identity_bundle",
        "post_freeze_input_bundle",
    ),
    "historical_current_authority_calls": 0,
    "canonical_serialization": "UTF-8/LF/RFC8785-compatible-project-canonical-json",
}
M336K7_FINAL_REQUEST_BUILDER_HASH = content_hash(M336K7_FINAL_REQUEST_CONTRACT)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class M336K7FinalRouteRequestV3:
    schema_version: int
    contract_role: str
    purpose: str
    repository: str
    git_executable: str
    python_executable: str
    exact_implementation_sha: str
    exact_f32_sha: str
    freeze_manifest: str
    f32_attestation: str | None
    final_authorization: str
    route_identity_bundle: str
    post_freeze_input_bundle: str
    resource_budget_policy: str
    resource_observation_receipt: str
    storage_reservation_receipt: str
    storage_reservation_file: str
    resource_gate_receipt: str
    capsule_binding_set: str
    legacy_compatibility_receipt: str
    capsule_liveness_receipt: str
    publication_contract: str
    route_ledger: str
    route_receipt: str
    stage_state: str
    stage_receipt_root: str
    private_root: str
    authority_statement: str
    frozen_spdx_reference: str
    windows_java: str
    windows_javac: str
    final_destinations: dict[str, str]
    karina: dict[str, str]
    executable_handles: dict[str, str]
    builder_identity_hash: str
    request_hash: str

    @property
    def exact_f30_sha(self) -> str:
        """Wire-compatible name consumed by the frozen native controller."""

        return self.exact_f32_sha

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("request_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "request_hash": self.request_hash}

    def verify(self) -> None:
        if (
            self.schema_version != 3
            or self.contract_role != "M336K7_CANONICAL_FINAL_ROUTE_REQUEST_V3"
            or self.purpose not in {"DISPOSABLE", "OFFICIAL", "QUALIFICATION"}
            or _SHA.fullmatch(self.exact_implementation_sha) is None
            or _SHA.fullmatch(self.exact_f32_sha) is None
            or self.builder_identity_hash != M336K7_FINAL_REQUEST_BUILDER_HASH
            or _HASH.fullmatch(self.request_hash) is None
            or self.request_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K7 canonical final request is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K7 final request fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K7PreLedgerInvocationReceipt:
    schema_version: int
    contract_role: str
    exact_implementation_sha: str
    exact_f32_sha: str
    route_identity_bundle_hash: str
    canonical_final_request_hash: str
    freeze_hash: str
    post_freeze_input_bundle_hash: str
    authorization_hash: str
    resource_budget_policy_hash: str
    resource_observation_hash: str
    storage_reservation_receipt_hash: str
    resource_gate_receipt_hash: str
    capsule_binding_set_hash: str
    legacy_compatibility_receipt_hash: str
    capsule_liveness_receipt_hash: str
    startup_receipt_hash: str
    karina_startup_receipt_hash: str
    acquisition_reservations: int
    acquisition_invocations: int
    selector_reservations: int
    selector_invocations: int
    evaluator_reservations: int
    evaluator_invocations: int
    route_ledger_writes: int
    source_requests: int
    vault_files: int
    cleanup_operations_after_f32: int
    karina_host_preflight_hash: str
    karina_storage_preflight_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K7ValidatedInvocation:
    request: M336K7FinalRouteRequestV3
    bundle: M336K5RouteIdentityBundle
    authorization: M336K5FinalAuthorization
    freeze: M336K7FreezeManifest
    post_freeze_inputs: M336K7PostFreezeInputBundle
    resource_policy: M336K7ResourceBudgetPolicy
    resource_observation: M336K7ResourceObservationReceipt
    storage_reservation: M336K5StorageReservationReceipt
    resource_gate: M336K7ResourceGateReceipt
    capsule_binding_set: M336K7PersistentCapsuleBindingSet
    legacy_compatibility: M336K7LegacyCapsuleCompatibilityReceipt
    receipt: M336K7PreLedgerInvocationReceipt


def build_m336k7_final_route_request(**values: Any) -> M336K7FinalRouteRequestV3:
    body = {
        "schema_version": 3,
        "contract_role": "M336K7_CANONICAL_FINAL_ROUTE_REQUEST_V3",
        **values,
        "builder_identity_hash": M336K7_FINAL_REQUEST_BUILDER_HASH,
    }
    if set(body) != set(M336K7FinalRouteRequestV3.__dataclass_fields__) - {
        "request_hash"
    }:
        raise M336K2ProtocolError("M336K7 request builder arguments changed")
    result = M336K7FinalRouteRequestV3(**body, request_hash=content_hash(body))
    result.verify()
    return result


def write_m336k7_final_route_request(
    request: M336K7FinalRouteRequestV3, output: Path
) -> None:
    request.verify()
    if output.exists():
        raise FileExistsError("M336K7 canonical request output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(request.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_m336k7_final_route_request(path: Path) -> M336K7FinalRouteRequestV3:
    raw = path.resolve(strict=True).read_bytes()
    value = _strict_object(raw)
    request = M336K7FinalRouteRequestV3.from_dict(value)
    if raw != (canonical_json(value) + "\n").encode("utf-8"):
        raise M336K2ProtocolError("M336K7 request serialization is not canonical")
    return request


def validate_m336k7_final_invocation(
    request_path: Path,
    *,
    startup_receipt_path: Path,
) -> M336K7ValidatedInvocation:
    """Validate exact committed inputs and live state without a ledger write."""

    request = load_m336k7_final_route_request(request_path)
    startup = startup_receipt_from_path(startup_receipt_path)
    root = Path(request.repository).resolve(strict=True)
    git = Path(request.git_executable).resolve(strict=True)
    freeze_path = Path(request.freeze_manifest).resolve(strict=True)
    freeze = M336K7FreezeManifest.from_dict(_object(freeze_path))
    freeze.verify(root, allow_prospective=True)
    components = {item.name: item for item in freeze.components}
    _verify_request_component_handles(root, components, request)

    bundle = M336K5RouteIdentityBundle.from_dict(
        _object(Path(request.route_identity_bundle).resolve(strict=True))
    )
    authorization = M336K5FinalAuthorization.from_dict(
        _object(Path(request.final_authorization).resolve(strict=True))
    )
    authorization.verify(bundle)
    post_freeze = M336K7PostFreezeInputBundle.from_dict(
        _object(Path(request.post_freeze_input_bundle).resolve(strict=True))
    )
    policy = M336K7ResourceBudgetPolicy.from_dict(
        _object(Path(request.resource_budget_policy).resolve(strict=True))
    )
    observation = M336K7ResourceObservationReceipt.from_dict(
        _object(Path(request.resource_observation_receipt).resolve(strict=True))
    )
    reservation = storage_reservation_from_dict(
        _object(Path(request.storage_reservation_receipt).resolve(strict=True))
    )
    gate = M336K7ResourceGateReceipt.from_dict(
        _object(Path(request.resource_gate_receipt).resolve(strict=True))
    )
    binding = M336K7PersistentCapsuleBindingSet.from_dict(
        _object(Path(request.capsule_binding_set).resolve(strict=True))
    )
    compatibility = M336K7LegacyCapsuleCompatibilityReceipt.from_dict(
        _object(Path(request.legacy_compatibility_receipt).resolve(strict=True))
    )
    verify_m336k7_capsule_compatibility_binding(binding, compatibility)

    if (
        request.exact_implementation_sha != freeze.implementation_tip
        or authorization.exact_implementation_tip != freeze.implementation_tip
        or authorization.exact_q30_sha != freeze.exact_q32_sha
        or bundle.protocol_run_id.value != M336K7_PROTOCOL_RUN_ID
        and request.purpose == "OFFICIAL"
        or bundle.route_version.value.split(".", 1)[0] != "m336k7"
        or freeze.route_identity_bundle_hash != bundle.bundle_hash
        or freeze.authorization_hash != authorization.authorization_hash
        or freeze.route_hash != bundle.route_manifest_hash
        or freeze.canonical_request_builder_hash != request.builder_identity_hash
        or post_freeze.freeze_manifest_contract_hash
        != M336K7_FREEZE_MANIFEST_CONTRACT_HASH
    ):
        raise M336K2ProtocolError("M336K7 request/freeze identity binding changed")

    registry = build_m336k5_route_registry(root, "m336k7")
    if registry.registry_hash != bundle.route_registry_hash:
        raise M336K2ProtocolError("M336K7 executable route registry changed")
    _verify_identity_policy_components(root, components, bundle)
    _verify_post_freeze_bundle(
        root,
        components,
        post_freeze,
        bundle=bundle,
        authorization=authorization,
        policy=policy,
        observation=observation,
        reservation_hash=reservation.receipt_hash,
        gate=gate,
        binding=binding,
        compatibility=compatibility,
    )
    verify_m336k7_resource_gate_binding(policy, observation, reservation, gate)
    _verify_live_windows_resources(
        request,
        policy,
        reservation,
        reservation_released=False,
    )
    _verify_executables_and_startup(
        root,
        request,
        components,
        authorization=authorization,
        startup=startup,
        policy=policy,
    )
    liveness = _strict_liveness(
        _object(Path(request.capsule_liveness_receipt).resolve(strict=True))
    )
    capsule, legacy_public, karina_dependencies, capsule_source_identity = (
        _verify_capsule_bindings(
            root,
            request,
            components,
            freeze=freeze,
            binding=binding,
            compatibility=compatibility,
            liveness=liveness,
        )
    )
    _verify_destination_set(root, git, request)
    _verify_attestation_and_lineage(root, git, request, freeze, bundle, post_freeze)
    host, storage = _verify_live_karina(
        root,
        request,
        freeze=freeze,
        capsule=capsule,
        public=legacy_public,
        dependencies=karina_dependencies,
        capsule_source_identity=capsule_source_identity,
    )
    body = {
        "schema_version": 3,
        "contract_role": "M336K7_SIDE_EFFECT_FREE_PRELEDGER_INVOCATION_RECEIPT",
        "exact_implementation_sha": request.exact_implementation_sha,
        "exact_f32_sha": request.exact_f32_sha,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "canonical_final_request_hash": request.request_hash,
        "freeze_hash": freeze.manifest_hash,
        "post_freeze_input_bundle_hash": post_freeze.bundle_hash,
        "authorization_hash": authorization.authorization_hash,
        "resource_budget_policy_hash": policy.policy_hash,
        "resource_observation_hash": observation.observation_hash,
        "storage_reservation_receipt_hash": reservation.receipt_hash,
        "resource_gate_receipt_hash": gate.receipt_hash,
        "capsule_binding_set_hash": binding.binding_set_hash,
        "legacy_compatibility_receipt_hash": compatibility.receipt_hash,
        "capsule_liveness_receipt_hash": liveness.receipt_hash,
        "startup_receipt_hash": startup.receipt_hash,
        "karina_startup_receipt_hash": host["startup_receipt_hash"],
        "acquisition_reservations": 0,
        "acquisition_invocations": 0,
        "selector_reservations": 0,
        "selector_invocations": 0,
        "evaluator_reservations": 0,
        "evaluator_invocations": 0,
        "route_ledger_writes": 0,
        "source_requests": 0,
        "vault_files": 0,
        "cleanup_operations_after_f32": 0,
        "karina_host_preflight_hash": host["receipt_hash"],
        "karina_storage_preflight_hash": content_hash(
            {
                "required_free_bytes": storage["required_free_bytes"],
                "minimum_free_inodes": 100_000,
                "qualification_margin": True,
                "status": storage["status"],
            }
        ),
        "status": "FINAL_INVOCATION_ACCEPTED_PRE_LEDGER",
    }
    receipt = M336K7PreLedgerInvocationReceipt(**body, receipt_hash=content_hash(body))
    return M336K7ValidatedInvocation(
        request,
        bundle,
        authorization,
        freeze,
        post_freeze,
        policy,
        observation,
        reservation,
        gate,
        binding,
        compatibility,
        receipt,
    )


def build_m336k7_internal_stage_request(validated: M336K7ValidatedInvocation) -> dict:
    request = validated.request
    bundle = validated.bundle
    return {
        "schema_version": 3,
        "repository": request.repository,
        "git_executable": request.git_executable,
        "python_executable": request.python_executable,
        "exact_f28_sha": request.exact_f32_sha,
        "freeze_manifest": request.freeze_manifest,
        "f28_attestation": request.f32_attestation,
        "final_authorization": request.final_authorization,
        "publication_contract": request.publication_contract,
        "route_run_id": bundle.protocol_run_id.value,
        "execution_mode": bundle.execution_mode.value,
        "execution_purpose": request.purpose,
        "route_identity_bundle": request.route_identity_bundle,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "startup_receipt_hash": validated.receipt.startup_receipt_hash,
        "karina_startup_receipt_hash": validated.receipt.karina_startup_receipt_hash,
        "stage_state": request.stage_state,
        "stage_receipt_root": request.stage_receipt_root,
        "private_root": request.private_root,
        "authority_statement": request.authority_statement,
        "frozen_spdx_reference": request.frozen_spdx_reference,
        "windows_java": request.windows_java,
        "windows_javac": request.windows_javac,
        "final_destinations": request.final_destinations,
        "karina": _legacy_stage_karina(request.karina),
        "executable_handles": request.executable_handles,
    }


def _legacy_stage_karina(karina: dict[str, str]) -> dict[str, str]:
    return {
        "private_execution_capsule": karina["private_execution_capsule"],
        "public_execution_capsule_receipt": karina["legacy_public_capsule_receipt"],
        "executable_dependency_manifest": karina["executable_dependency_manifest"],
        "ssh_executable": karina["ssh_executable"],
        "ssh_key": karina["ssh_key"],
        "known_hosts_file": karina["known_hosts_file"],
        "worker_endpoint": karina["worker_endpoint"],
        "repository": karina["repository"],
        "private_root": karina["private_root"],
        "private_capsule_remote": karina["private_capsule_remote"],
        "javac": karina["javac"],
    }


def _verify_request_component_handles(root: Path, components: dict, request) -> None:
    mappings = {
        "final_authorization": request.final_authorization,
        "route_identity_bundle": request.route_identity_bundle,
        "post_freeze_input_bundle": request.post_freeze_input_bundle,
        "resource_budget_policy": request.resource_budget_policy,
        "resource_observation": request.resource_observation_receipt,
        "storage_reservation": request.storage_reservation_receipt,
        "resource_gate": request.resource_gate_receipt,
        "capsule_binding_set": request.capsule_binding_set,
        "legacy_capsule_compatibility": request.legacy_compatibility_receipt,
        "capsule_liveness": request.capsule_liveness_receipt,
    }
    for name, supplied_value in mappings.items():
        component = components[name]
        frozen = root.joinpath(*Path(component.relative_path).parts).resolve(
            strict=True
        )
        supplied = Path(supplied_value).resolve(strict=True)
        if frozen != supplied:
            raise M336K2ProtocolError(f"M336K7 frozen component handle changed: {name}")


def _verify_post_freeze_bundle(
    root: Path,
    components: dict,
    value: M336K7PostFreezeInputBundle,
    *,
    bundle: M336K5RouteIdentityBundle,
    authorization: M336K5FinalAuthorization,
    policy: M336K7ResourceBudgetPolicy,
    observation: M336K7ResourceObservationReceipt,
    reservation_hash: str,
    gate: M336K7ResourceGateReceipt,
    binding: M336K7PersistentCapsuleBindingSet,
    compatibility: M336K7LegacyCapsuleCompatibilityReceipt,
) -> None:
    hashes = {
        "final_authorization_hash": authorization.authorization_hash,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "route_registry_hash": _component_hash(
            root, components, "typed_route_registry", "registry_hash"
        ),
        "route_manifest_hash": _component_hash(
            root, components, "typed_route_manifest", "manifest_hash"
        ),
        "resource_budget_policy_hash": policy.policy_hash,
        "resource_observation_hash": observation.observation_hash,
        "storage_reservation_receipt_hash": reservation_hash,
        "resource_gate_receipt_hash": gate.receipt_hash,
        "capsule_binding_set_hash": binding.binding_set_hash,
        "legacy_compatibility_receipt_hash": compatibility.receipt_hash,
        "liveness_receipt_hash": _component_hash(
            root, components, "capsule_liveness", "receipt_hash"
        ),
        "startup_policy_hash": _component_hash(
            root, components, "python_startup_policy", "policy_hash"
        ),
        "executable_dependency_manifest_hash": _component_hash(
            root, components, "executable_dependency_manifest", "manifest_hash"
        ),
        "windows_jdk_identity_hash": _component_hash(
            root, components, "windows_jdk_identity", "receipt_hash"
        ),
        "karina_jdk_identity_hash": _component_hash(
            root, components, "karina_jdk_identity", "receipt_hash"
        ),
        "karina_host_identity_hash": _component_hash(
            root, components, "karina_stable_host_identity", "receipt_hash"
        ),
        "candidate_pool_hash": _component_hash(
            root, components, "candidate_pool", "pool_hash"
        ),
        "acquisition_policy_hash": _component_hash(
            root, components, "acquisition_policy", "acquisition_policy_hash"
        ),
        "archive_policy_hash": _component_hash(
            root, components, "archive_policy", "policy_hash"
        ),
        "terminal_policy_hash": _component_hash(
            root,
            components,
            "candidate_terminal_policy",
            "policy_hash",
        ),
        "selector_policy_hash": _component_hash(
            root, components, "selector_policy", "policy_hash"
        ),
        "evaluator_policy_hash": _component_hash(
            root, components, "evaluator_policy", "policy_hash"
        ),
        "threshold_manifest_hash": _component_hash(
            root, components, "threshold_manifest", "threshold_manifest_hash"
        ),
        "publication_contract_hash": content_hash(
            (
                _component_hash(
                    root, components, "h28_publication_contract", "contract_hash"
                ),
                _component_hash(
                    root, components, "e28_publication_contract", "contract_hash"
                ),
            )
        ),
    }
    for name, expected in hashes.items():
        if getattr(value, name) != expected:
            raise M336K2ProtocolError(
                f"M336K7 post-freeze input binding changed: {name}"
            )


def _verify_live_windows_resources(
    request, policy, reservation, *, reservation_released: bool
) -> None:
    requested_file = Path(request.storage_reservation_file).resolve(strict=False)
    parent = requested_file.parent.resolve(strict=True)
    available_ram, _used_ram, swap_used = _system_memory()
    disk = shutil.disk_usage(parent)
    free_inodes = _free_inodes(parent)
    if (
        _filesystem_identity(parent) != reservation.filesystem_identity_hash
        or reservation_released
        and (
            requested_file.exists() or disk.free < policy.required_private_storage_bytes
        )
        or not reservation_released
        and (
            not requested_file.is_file()
            or requested_file.stat().st_size != reservation.reservation_bytes
            or _allocated_size(requested_file) < reservation.reservation_bytes
            or _file_sha256(requested_file) != reservation.reservation_content_hash
            or disk.free < policy.required_free_after_reservation_bytes
            or disk.free + reservation.reservation_bytes
            < policy.required_private_storage_bytes
        )
        or free_inodes != 0
        and free_inodes < policy.required_free_inodes
        or available_ram < policy.required_available_ram_bytes
        or swap_used > policy.maximum_allowed_swap_bytes
    ):
        raise M336K2ProtocolError("M336K7 live Windows resource gate failed")


def verify_m336k7_reservation_release(
    path: Path,
    *,
    validated: M336K7ValidatedInvocation,
) -> M336K7StorageReservationReleaseReceipt:
    value = _object(path.resolve(strict=True))
    receipt = M336K7StorageReservationReleaseReceipt.from_dict(value)
    reservation_path = Path(validated.request.storage_reservation_file).resolve(
        strict=False
    )
    if (
        receipt.storage_reservation_receipt_hash
        != validated.resource_gate.storage_reservation_receipt_hash
        or receipt.reservation_file_identity_hash
        != content_hash(os.path.normcase(str(reservation_path)))
        or receipt.released_bytes != validated.resource_policy.storage_reservation_bytes
        or reservation_path.exists()
        or shutil.disk_usage(reservation_path.parent).free
        < validated.resource_policy.required_private_storage_bytes
    ):
        raise M336K2ProtocolError("M336K7 reservation release binding changed")
    return receipt


def verify_m336k7_released_resource_state(
    validated: M336K7ValidatedInvocation,
) -> None:
    _verify_live_windows_resources(
        validated.request,
        validated.resource_policy,
        validated.storage_reservation,
        reservation_released=True,
    )


def load_m336k7_preledger_receipt(path: Path) -> M336K7PreLedgerInvocationReceipt:
    value = _object(path.resolve(strict=True))
    if set(value) != set(M336K7PreLedgerInvocationReceipt.__dataclass_fields__):
        raise M336K2ProtocolError("M336K7 preledger receipt fields changed")
    receipt = M336K7PreLedgerInvocationReceipt(**value)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    counters = (
        receipt.acquisition_reservations,
        receipt.acquisition_invocations,
        receipt.selector_reservations,
        receipt.selector_invocations,
        receipt.evaluator_reservations,
        receipt.evaluator_invocations,
        receipt.route_ledger_writes,
        receipt.source_requests,
        receipt.vault_files,
        receipt.cleanup_operations_after_f32,
    )
    if (
        content_hash(body) != claimed
        or any(counters)
        or receipt.status != "FINAL_INVOCATION_ACCEPTED_PRE_LEDGER"
    ):
        raise M336K2ProtocolError("M336K7 preledger receipt is invalid")
    return receipt


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_executables_and_startup(
    root: Path,
    request,
    components: dict,
    *,
    authorization: M336K5FinalAuthorization,
    startup: M336K5PythonStartupReceipt,
    policy: M336K7ResourceBudgetPolicy,
) -> None:
    dependency = executable_dependency_manifest_from_dict(
        _component_object(root, components, "executable_dependency_manifest")
    )
    handles = {name: Path(value) for name, value in request.executable_handles.items()}
    verify_m336k2_executable_handles(dependency, handles)
    canonical_policy = build_m336k5_python_startup_policy()
    frozen_policy = M336K5PythonStartupPolicy.from_dict(
        _component_object(root, components, "python_startup_policy")
    )
    environment = _component_object(root, components, "python_environment_manifest")
    if (
        handles["git"] != Path(request.git_executable)
        or handles["python"] != Path(request.python_executable)
        or handles["java"] != Path(request.windows_java)
        or handles["javac"] != Path(request.windows_javac)
        or frozen_policy != canonical_policy
        or startup.startup_policy_hash != canonical_policy.policy_hash
        or startup.startup_policy_hash != authorization.python_startup_policy_hash
        or environment["startup_policy_hash"] != canonical_policy.policy_hash
        or environment["project_source_identity_hash"]
        != startup.project_source_identity
        or environment["environment_manifest_hash"]
        != authorization.python_environment_manifest_hash
        or authorization.resource_budget_hash != policy.policy_hash
    ):
        raise M336K2ProtocolError("M336K7 executable/startup binding changed")


def _verify_capsule_bindings(
    root: Path,
    request,
    components: dict,
    *,
    freeze: M336K7FreezeManifest,
    binding: M336K7PersistentCapsuleBindingSet,
    compatibility: M336K7LegacyCapsuleCompatibilityReceipt,
    liveness: M336K6CapsuleLivenessReceipt,
):
    karina = request.karina
    expected = {
        "persistent_private_capsule",
        "private_execution_capsule",
        "persistent_public_capsule_receipt",
        "legacy_public_capsule_receipt",
        "executable_dependency_manifest",
        "python_environment_manifest",
        "capsule_liveness_receipt",
        "ssh_executable",
        "ssh_key",
        "known_hosts_file",
        "worker_endpoint",
        "repository",
        "private_root",
        "private_capsule_remote",
        "javac",
    }
    if set(karina) != expected:
        raise M336K2ProtocolError("M336K7 Karina invocation fields changed")
    private = M336K6PrivateExecutionCapsule.from_dict(
        _object(Path(karina["persistent_private_capsule"]).resolve(strict=True))
    )
    persistent_value = _object(
        Path(karina["persistent_public_capsule_receipt"]).resolve(strict=True)
    )
    if set(persistent_value) != set(
        M336K6PublicExecutionCapsuleReceipt.__dataclass_fields__
    ):
        raise M336K2ProtocolError("M336K7 persistent public receipt fields changed")
    _verify_semantic_hash(persistent_value, "receipt_hash")
    persistent = M336K6PublicExecutionCapsuleReceipt(**persistent_value)
    legacy = public_execution_capsule_receipt_from_dict(
        _object(Path(karina["legacy_public_capsule_receipt"]).resolve(strict=True))
    )
    dependencies = dependency_manifest_from_dict(
        _object(Path(karina["executable_dependency_manifest"]).resolve(strict=True))
    )
    python_environment = _object(
        Path(karina["python_environment_manifest"]).resolve(strict=True)
    )
    _verify_semantic_hash(python_environment, "identity_hash")
    frozen_persistent = _component_object(
        root, components, "persistent_capsule_receipt"
    )
    frozen_liveness = _component_object(root, components, "capsule_liveness")
    content = _component_object(root, components, "capsule_content_manifest")
    lifecycle = _component_object(root, components, "capsule_lifecycle_policy")
    preservation = _component_object(root, components, "preservation_set")
    cutoff = _component_object(root, components, "cleanup_cutoff_state")
    if (
        binding.implementation_tip != private.implementation_sha
        or binding.capsule_identity_hash != private.capsule_identity_hash
        or binding.capsule_root_identity_hash != private.capsule_root_identity_hash
        or binding.capsule_content_manifest_hash != content["manifest_hash"]
        or binding.capsule_lifecycle_policy_hash != lifecycle["policy_hash"]
        or binding.capsule_liveness_receipt_hash != liveness.receipt_hash
        or binding.persistent_capsule_public_receipt_hash != persistent.receipt_hash
        or binding.legacy_public_capsule_receipt_hash != legacy.receipt_hash
        or binding.python_environment_manifest_hash
        != python_environment["environment_manifest_hash"]
        or binding.executable_dependency_manifest_hash != dependencies.manifest_hash
        or binding.startup_policy_hash != private.startup_policy_hash
        or binding.bootstrap_source_hash != private.bootstrap_source_hash
        or binding.launcher_source_hash != private.launcher_source_hash
        or binding.stable_karina_host_identity_hash != legacy.host_identity_receipt_hash
        or binding.preservation_set_hash != preservation["preservation_set_hash"]
        or binding.cleanup_cutoff_receipt_hash != cutoff["receipt_hash"]
        or compatibility.persistent_public_receipt_hash != persistent.receipt_hash
        or compatibility.legacy_public_receipt_hash != legacy.receipt_hash
        or compatibility.executable_dependency_manifest_hash
        != dependencies.manifest_hash
        or compatibility.host_identity_hash != legacy.host_identity_receipt_hash
        or compatibility.python_environment_manifest_hash
        != python_environment["environment_manifest_hash"]
        or persistent_value != frozen_persistent
        or frozen_liveness != asdict(liveness)
        or persistent.implementation_sha != private.implementation_sha
        or persistent.project_source_identity != private.project_source_identity
        or liveness.capsule_identity_hash != private.capsule_identity_hash
        or liveness.status != "PASS"
        or private.legacy_public_receipt_hash != legacy.receipt_hash
        or private.executable_dependency_manifest_hash != dependencies.manifest_hash
        or private.python_environment_manifest_hash
        != python_environment["environment_manifest_hash"]
        or private.legacy_capsule_path != karina["private_capsule_remote"]
        or PurePosixPath(karina["repository"]) != PurePosixPath(private.source_root)
        or not PurePosixPath(karina["private_root"]).is_relative_to(
            PurePosixPath(private.private_route_root)
        )
        or karina["javac"] != private.javac_executable
    ):
        raise M336K2ProtocolError("M336K7 canonical capsule binding changed")
    return (
        _load_legacy_private_capsule(karina["private_execution_capsule"]),
        legacy,
        dependencies,
        private.project_source_identity,
    )


def _load_legacy_private_capsule(path: str):
    from ai_brain.stage3.acquisition.m336j_execution import (
        load_private_execution_capsule,
    )

    return load_private_execution_capsule(Path(path).resolve(strict=True))


def _verify_live_karina(
    root,
    request,
    *,
    freeze,
    capsule,
    public,
    dependencies,
    capsule_source_identity,
):
    karina = request.karina
    transport = KarinaPrivateSshTransport(
        ssh_executable=Path(karina["ssh_executable"]).resolve(strict=True),
        endpoint=karina["worker_endpoint"],
        identity_file=Path(karina["ssh_key"]).resolve(strict=True),
        known_hosts_file=Path(karina["known_hosts_file"]).resolve(strict=True),
    )
    registry = build_m336j_route_registry()
    bootstrap_source_hash = bytes_hash(
        (root / "scripts" / "m336k5_python_bootstrap.py").read_bytes()
    )
    target_source_hash = bytes_hash(
        (root / "scripts" / "m336j_karina_execution.py").read_bytes()
    )
    project_source_identity = capsule_source_identity
    host_component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_HOST_PREFLIGHT"
    )
    host_request_hash = content_hash(
        (freeze.implementation_tip, public.receipt_hash, host_component.binding_hash)
    )
    host = _invoke_karina_preledger(
        transport=transport,
        capsule=capsule,
        public=public,
        dependencies=dependencies,
        component=host_component,
        subcommand="host-preflight",
        remote_capsule=karina["private_capsule_remote"],
        request_hash=host_request_hash,
        options=(),
        bootstrap_source_hash=bootstrap_source_hash,
        target_source_hash=target_source_hash,
        project_source_identity=project_source_identity,
    )
    maximum = M336J_DEFAULT_TREE_TRANSFER_LIMITS.maximum_archive_bytes
    storage_component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_STORAGE_PREFLIGHT"
    )
    storage_request_hash = content_hash(
        (
            maximum,
            "QUALIFICATION_12_GIB",
            public.receipt_hash,
            storage_component.binding_hash,
        )
    )
    storage = _invoke_karina_preledger(
        transport=transport,
        capsule=capsule,
        public=public,
        dependencies=dependencies,
        component=storage_component,
        subcommand="storage-preflight",
        remote_capsule=karina["private_capsule_remote"],
        request_hash=storage_request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--maximum-transfer-bytes"),
            (KarinaRemoteTokenClass.OPAQUE_ARGUMENT, str(maximum)),
            (KarinaRemoteTokenClass.FLAG, "--qualification-margin"),
        ),
        bootstrap_source_hash=bootstrap_source_hash,
        target_source_hash=target_source_hash,
        project_source_identity=project_source_identity,
    )
    if (
        host["execution_capsule_receipt_hash"] != public.receipt_hash
        or host["host_identity_hash"] != public.host_identity_receipt_hash
        or _HASH.fullmatch(host["startup_receipt_hash"]) is None
        or host["startup_receipt_hash"] != storage["startup_receipt_hash"]
        or storage["required_free_bytes"] != 12 * 1024**3
        or storage["available_free_bytes"] < storage["required_free_bytes"]
        or storage["available_free_inodes"] < 100_000
    ):
        raise M336K2ProtocolError("M336K7 Karina live preledger gate failed")
    return host, storage


def _invoke_karina_preledger(
    *,
    transport,
    capsule,
    public,
    dependencies,
    component,
    subcommand,
    remote_capsule,
    request_hash,
    options,
    bootstrap_source_hash,
    target_source_hash,
    project_source_identity,
):
    arguments = (
        (KarinaRemoteTokenClass.SUBCOMMAND, subcommand),
        (KarinaRemoteTokenClass.FLAG, "--private-capsule"),
        (KarinaRemoteTokenClass.PRIVATE_PATH, remote_capsule),
        *options,
        (KarinaRemoteTokenClass.FLAG, "--request-hash"),
        (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
        (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
        (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
    )
    role = {
        "host-preflight": "KARINA_HOST_PREFLIGHT",
        "storage-preflight": "KARINA_STORAGE_PREFLIGHT",
    }[subcommand]
    plan, _inline = build_m336k5_karina_invocation(
        component_id=component.component_id,
        capsule=capsule,
        public_capsule=public,
        process_role=role,
        target=capsule.repository_checkout / "scripts/m336j_karina_execution.py",
        target_arguments=arguments,
        bootstrap_source_hash=bootstrap_source_hash,
        target_source_hash=target_source_hash,
        project_source_identity=project_source_identity,
        startup_receipt=capsule.private_root / "m336k5-startup-receipt.json",
    )
    result = invoke_karina_command(
        transport=transport,
        capsule=capsule,
        plan=plan,
        dependency_manifest=dependencies,
    )
    return parse_bound_json_response(
        result.stdout,
        request_hash=request_hash,
        component_binding_hash=component.binding_hash,
        host_identity_hash=public.host_identity_receipt_hash,
    )


def _verify_attestation_and_lineage(root, git, request, freeze, bundle, inputs) -> None:
    if request.exact_f32_sha == "0" * 40:
        if request.f32_attestation is not None or request.purpose == "OFFICIAL":
            raise M336K2ProtocolError("M336K7 official request lacks exact F32")
        return
    if request.f32_attestation is None:
        raise M336K2ProtocolError("M336K7 exact F32 attestation is absent")
    attestation = M336K7CommittedFreezeAttestation.from_dict(
        _object(Path(request.f32_attestation).resolve(strict=True))
    )
    branch = subprocess.run(
        (str(git), "symbolic-ref", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote_rows = _git(git, root, "ls-remote", "--exit-code", "origin", branch).split()
    remote = remote_rows[0] if remote_rows else ""
    if (
        attestation.exact_f32_sha != request.exact_f32_sha
        or attestation.exact_q32_parent != freeze.exact_q32_sha
        or attestation.route_identity_bundle_hash != bundle.bundle_hash
        or attestation.post_freeze_input_bundle_hash != inputs.bundle_hash
        or head != upstream
        or head != remote
        or head != request.exact_f32_sha
        or branch != authorization_branch_ref(request)
        or _git(git, root, "status", "--porcelain=v1")
    ):
        raise M336K2ProtocolError("M336K7 exact final lineage is not clean/pushed")


def authorization_branch_ref(request: M336K7FinalRouteRequestV3) -> str:
    authorization = M336K5FinalAuthorization.from_dict(
        _object(Path(request.final_authorization).resolve(strict=True))
    )
    return authorization.branch_ref


def _component_object(root: Path, components: dict, name: str) -> dict[str, Any]:
    component = components[name]
    path = root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
    value = _object(path)
    if bytes_hash(path.read_bytes()) != component.bytes_hash:
        raise M336K2ProtocolError(f"M336K7 frozen component bytes changed: {name}")
    return value


def _component_hash(root: Path, components: dict, name: str, field: str) -> str:
    value = _component_object(root, components, name)
    _verify_semantic_hash(value, field)
    return value[field]


def _verify_semantic_hash(value: dict[str, Any], field: str) -> None:
    body = dict(value)
    claimed = body.pop(field)
    if type(claimed) is not str or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K7 component semantic hash changed")


def _strict_liveness(value: dict[str, Any]) -> M336K6CapsuleLivenessReceipt:
    if set(value) != set(M336K6CapsuleLivenessReceipt.__dataclass_fields__):
        raise M336K2ProtocolError("M336K7 capsule liveness fields changed")
    _verify_semantic_hash(value, "receipt_hash")
    result = M336K6CapsuleLivenessReceipt(**value)
    if (
        result.status != "PASS"
        or result.missing_file_count != 0
        or result.changed_file_count != 0
        or result.unexpected_file_count != 0
        or result.mutable_quality_dependency_count != 0
        or result.symlink_target_change_count != 0
        or not result.protected_worktree_locked
    ):
        raise M336K2ProtocolError("M336K7 capsule liveness is not PASS")
    return result


def _strict_object(raw: bytes) -> dict[str, Any]:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise M336K2ProtocolError("M336K7 JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K7 JSON is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K7 JSON is not an object")
    return value


def _object(path: Path) -> dict[str, Any]:
    return _strict_object(path.read_bytes())


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()
