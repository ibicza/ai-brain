"""Canonical external request and side-effect-free pre-ledger validation."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336j_execution import (
    KarinaRemoteTokenClass,
    compute_m336j_project_source_identity,
    dependency_manifest_from_dict,
    load_private_execution_capsule,
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
from ai_brain.stage3.acquisition.m336k5_authorization import (
    M336K5FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k5_freeze import (
    M336K5CommittedFreezeAttestation,
    M336K5FreezeManifest,
    verify_complete_m336k5_freeze,
)
from ai_brain.stage3.acquisition.m336k5_identity import M336K5RouteIdentityBundle
from ai_brain.stage3.acquisition.m336k5_registry import build_m336k5_route_registry
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupPolicy,
    M336K5PythonStartupReceipt,
    build_m336k5_karina_invocation,
    build_m336k5_python_startup_policy,
    startup_receipt_from_path,
)

M336K5_FINAL_REQUEST_CONTRACT = {
    "schema_version": 2,
    "contract_role": "M336K5_CANONICAL_FINAL_ROUTE_REQUEST_V2",
    "forbidden_external_fields": (
        "route_run_id",
        "protocol_run_id",
        "route_version",
        "acquisition_run_id",
        "selector_run_id",
        "evaluator_run_id",
        "execution_mode",
    ),
    "identity_derivation": (
        "typed_final_authorization",
        "typed_freeze_manifest",
        "route_identity_bundle",
    ),
    "canonical_serialization": "UTF-8/LF/RFC8785-compatible-project-canonical-json",
}
M336K5_FINAL_REQUEST_BUILDER_HASH = content_hash(M336K5_FINAL_REQUEST_CONTRACT)
_SHA_OR_ZERO = re.compile(r"(?:[0-9a-f]{40})")
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class M336K5FinalRouteRequestV2:
    schema_version: int
    contract_role: str
    purpose: str
    repository: str
    git_executable: str
    python_executable: str
    exact_implementation_sha: str
    exact_f30_sha: str
    freeze_manifest: str
    f30_attestation: str | None
    final_authorization: str
    route_identity_bundle: str
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

    def _body(self) -> dict:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "request_hash"
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "request_hash": self.request_hash}

    @classmethod
    def from_dict(cls, value: dict) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            forbidden = (
                set(value)
                & set(M336K5_FINAL_REQUEST_CONTRACT["forbidden_external_fields"])
                if isinstance(value, dict)
                else set()
            )
            if forbidden:
                raise M336K2ProtocolError(
                    "M336K5 external request contains a caller-selected identity"
                )
            raise M336K2ProtocolError("M336K5 final request fields changed")
        result = cls(**value)
        result.verify()
        return result

    def verify(self) -> None:
        if (
            self.schema_version != 2
            or self.contract_role != "M336K5_CANONICAL_FINAL_ROUTE_REQUEST_V2"
            or self.purpose not in {"DISPOSABLE", "OFFICIAL", "QUALIFICATION"}
            or _SHA_OR_ZERO.fullmatch(self.exact_implementation_sha) is None
            or _SHA_OR_ZERO.fullmatch(self.exact_f30_sha) is None
            or self.builder_identity_hash != M336K5_FINAL_REQUEST_BUILDER_HASH
            or _HASH.fullmatch(self.request_hash) is None
            or content_hash(self._body()) != self.request_hash
        ):
            raise M336K2ProtocolError("M336K5 canonical final request is invalid")


@dataclass(frozen=True)
class M336K5PreLedgerInvocationReceipt:
    schema_version: int
    contract_role: str
    exact_implementation_sha: str
    prospective_or_exact_f30_sha: str
    protocol_run_id_hash: str
    route_identity_bundle_hash: str
    canonical_final_request_hash: str
    freeze_hash: str
    authorization_hash: str
    route_hash: str
    destination_set_hash: str
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
    karina_host_preflight_hash: str
    karina_storage_preflight_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K5ValidatedInvocation:
    request: M336K5FinalRouteRequestV2
    bundle: M336K5RouteIdentityBundle
    authorization: M336K5FinalAuthorization
    freeze: M336K5FreezeManifest
    receipt: M336K5PreLedgerInvocationReceipt


def build_m336k5_final_route_request(**values) -> M336K5FinalRouteRequestV2:
    """Only tracked constructor for disposable, qualification, and official JSON."""

    forbidden = set(values) & set(
        M336K5_FINAL_REQUEST_CONTRACT["forbidden_external_fields"]
    )
    if forbidden:
        raise M336K2ProtocolError(
            "M336K5 request builder rejects caller-selected route identities"
        )
    body = {
        "schema_version": 2,
        "contract_role": "M336K5_CANONICAL_FINAL_ROUTE_REQUEST_V2",
        **values,
        "builder_identity_hash": M336K5_FINAL_REQUEST_BUILDER_HASH,
    }
    if set(body) != set(M336K5FinalRouteRequestV2.__dataclass_fields__) - {
        "request_hash"
    }:
        raise M336K2ProtocolError("M336K5 request builder arguments changed")
    result = M336K5FinalRouteRequestV2(**body, request_hash=content_hash(body))
    result.verify()
    return result


def write_m336k5_final_route_request(
    request: M336K5FinalRouteRequestV2, output: Path
) -> None:
    request.verify()
    if output.exists():
        raise FileExistsError("M336K5 canonical request output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(request.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_m336k5_final_route_request(path: Path) -> M336K5FinalRouteRequestV2:
    raw = path.resolve(strict=True).read_bytes()
    value = _strict_object(raw)
    request = M336K5FinalRouteRequestV2.from_dict(value)
    if raw != (canonical_json(value) + "\n").encode("utf-8"):
        raise M336K2ProtocolError("M336K5 request serialization is not canonical")
    return request


def validate_m336k5_final_invocation(
    request_path: Path,
    *,
    startup_receipt_path: Path,
) -> M336K5ValidatedInvocation:
    """Run the real loader and all checks, stopping before any one-shot side effect."""

    request = load_m336k5_final_route_request(request_path)
    startup = startup_receipt_from_path(startup_receipt_path)
    root = Path(request.repository).resolve(strict=True)
    bundle_path = Path(request.route_identity_bundle).resolve(strict=True)
    bundle = M336K5RouteIdentityBundle.from_dict(_object(bundle_path))
    authorization_path = Path(request.final_authorization).resolve(strict=True)
    authorization = M336K5FinalAuthorization.from_dict(_object(authorization_path))
    authorization.verify(bundle)
    git = Path(request.git_executable).resolve(strict=True)
    freeze_path = Path(request.freeze_manifest).resolve(strict=True)
    freeze = M336K5FreezeManifest.from_dict(_object(freeze_path))
    verify_complete_m336k5_freeze(root, freeze, allow_prospective_f30=True)
    components = {item.name: item for item in freeze.components}
    _verify_component_handle(root, components, "route_identity_bundle", bundle_path)
    _verify_component_handle(
        root, components, "final_authorization", authorization_path
    )
    if (
        freeze.route_identity_bundle_hash != bundle.bundle_hash
        or freeze.authorization_hash != authorization.authorization_hash
        or freeze.route_hash != bundle.route_manifest_hash
        or freeze.canonical_request_builder_hash != request.builder_identity_hash
        or request.exact_implementation_sha != freeze.implementation_tip
        or authorization.exact_implementation_tip != freeze.implementation_tip
        or authorization.exact_q30_sha != freeze.exact_q30_sha
        or (
            request.purpose == "DISPOSABLE"
            and bundle.protocol_run_id.value == "m336k5.final-java.outcome-a.v1"
        )
        or (
            request.purpose == "OFFICIAL"
            and bundle.protocol_run_id.value != "m336k5.final-java.outcome-a.v1"
        )
    ):
        raise M336K2ProtocolError(
            "M336K5 request/freeze/authorization cross-binding changed"
        )
    registry = build_m336k5_route_registry(root)
    if registry.registry_hash != bundle.route_registry_hash:
        raise M336K2ProtocolError(
            "M336K5 frozen route registry differs from executable source"
        )
    typed_registry = _verified_component_object(
        root, components, "typed_route_registry", "registry_hash"
    )
    typed_route = _verified_component_object(
        root, components, "typed_route_manifest", "manifest_hash"
    )
    if (
        typed_registry.get("registry_hash") != registry.registry_hash
        or typed_route.get("route_registry_hash") != registry.registry_hash
        or typed_route.get("manifest_hash") != bundle.route_manifest_hash
        or typed_route.get("route_version") != bundle.route_version.canonical_object()
    ):
        raise M336K2ProtocolError("M336K5 route registry/manifest verification failed")
    _verify_identity_policy_components(root, components, bundle)
    _verify_executables_and_environment(
        root, request, components, authorization=authorization, startup=startup
    )
    _verify_destination_set(root, git, request)
    _verify_attestation_and_lineage(root, git, request, freeze, bundle)
    host, storage = _verify_karina_host_and_storage(
        request=request,
        bundle=bundle,
        freeze=freeze,
        root=root,
        components=components,
    )
    destination_hash = content_hash(
        tuple(
            sorted(
                (
                    name,
                    content_hash(str(Path(value).resolve(strict=False))),
                )
                for name, value in request.final_destinations.items()
            )
        )
    )
    body = {
        "schema_version": 2,
        "contract_role": "M336K5_SIDE_EFFECT_FREE_PRELEDGER_INVOCATION_RECEIPT",
        "exact_implementation_sha": request.exact_implementation_sha,
        "prospective_or_exact_f30_sha": request.exact_f30_sha,
        "protocol_run_id_hash": bundle.protocol_run_id.identity_hash,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "canonical_final_request_hash": request.request_hash,
        "freeze_hash": freeze.manifest_hash,
        "authorization_hash": authorization.authorization_hash,
        "route_hash": bundle.route_manifest_hash,
        "destination_set_hash": destination_hash,
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
    receipt = M336K5PreLedgerInvocationReceipt(**body, receipt_hash=content_hash(body))
    return M336K5ValidatedInvocation(request, bundle, authorization, freeze, receipt)


def build_m336k5_internal_stage_request(
    validated: M336K5ValidatedInvocation,
) -> dict:
    request = validated.request
    bundle = validated.bundle
    return {
        "schema_version": 3,
        "repository": request.repository,
        "git_executable": request.git_executable,
        "python_executable": request.python_executable,
        "exact_f28_sha": request.exact_f30_sha,
        "freeze_manifest": request.freeze_manifest,
        "f28_attestation": request.f30_attestation,
        "final_authorization": request.final_authorization,
        "publication_contract": request.publication_contract,
        "route_run_id": bundle.protocol_run_id.value,
        "execution_mode": bundle.execution_mode.value,
        "execution_purpose": request.purpose,
        "route_identity_bundle": request.route_identity_bundle,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "startup_receipt_hash": validated.receipt.startup_receipt_hash,
        "karina_startup_receipt_hash": (validated.receipt.karina_startup_receipt_hash),
        "stage_state": request.stage_state,
        "stage_receipt_root": request.stage_receipt_root,
        "private_root": request.private_root,
        "authority_statement": request.authority_statement,
        "frozen_spdx_reference": request.frozen_spdx_reference,
        "windows_java": request.windows_java,
        "windows_javac": request.windows_javac,
        "final_destinations": request.final_destinations,
        "karina": request.karina,
        "executable_handles": request.executable_handles,
    }


def _verify_identity_policy_components(root: Path, components: dict, bundle) -> None:
    acquisition = _verified_component_object(
        root, components, "acquisition_policy", "acquisition_policy_hash"
    )
    selector = _verified_component_object(
        root, components, "selector_policy", "policy_hash"
    )
    evaluator = _verified_component_object(
        root, components, "evaluator_policy", "policy_hash"
    )
    if (
        acquisition.get("acquisition_run_id") != bundle.acquisition_run_id.value
        or selector.get("selector_run_id") != bundle.selector_run_id.value
        or evaluator.get("evaluator_run_id") != bundle.evaluator_run_id.value
        or acquisition["acquisition_policy_hash"] != bundle.acquisition_policy_hash
        or selector["policy_hash"] != bundle.selector_policy_hash
        or evaluator["policy_hash"] != bundle.evaluator_policy_hash
    ):
        raise M336K2ProtocolError("M336K5 one-shot policy identity binding changed")


def _verify_executables_and_environment(
    root: Path,
    request,
    components: dict,
    *,
    authorization: M336K5FinalAuthorization,
    startup: M336K5PythonStartupReceipt,
) -> None:
    dependency = executable_dependency_manifest_from_dict(
        _verified_component_object(
            root, components, "executable_dependency_manifest", "manifest_hash"
        )
    )
    handles = {name: Path(value) for name, value in request.executable_handles.items()}
    verify_m336k2_executable_handles(dependency, handles)
    if (
        handles.get("git", Path()) != Path(request.git_executable)
        or handles.get("python", Path()) != Path(request.python_executable)
        or handles.get("java", Path()) != Path(request.windows_java)
        or handles.get("javac", Path()) != Path(request.windows_javac)
    ):
        raise M336K2ProtocolError("M336K5 executable aliases changed")
    environment = _verified_component_object(
        root, components, "python_environment_manifest", "environment_manifest_hash"
    )
    policy = _verified_component_object(
        root, components, "python_startup_policy", "policy_hash"
    )
    canonical_policy = build_m336k5_python_startup_policy()
    frozen_policy = M336K5PythonStartupPolicy.from_dict(policy)
    sanitized = _verified_component_object(
        root, components, "sanitized_environment_policy", "receipt_hash"
    )
    resource_budget = _verified_component_object(
        root, components, "resource_budget", "receipt_hash"
    )
    reservation = _verified_component_object(
        root, components, "storage_reservation", "receipt_hash"
    )
    bootstrap_component = _verified_component_object(
        root, components, "python_startup_bootstrap", "receipt_hash"
    )
    windows_launcher_component = _verified_component_object(
        root, components, "windows_python_launcher", "receipt_hash"
    )
    karina_launcher = _verified_component_object(
        root, components, "karina_python_launcher", "launcher_hash"
    )
    startup_schema = _verified_component_object(
        root, components, "startup_receipt_schema", "schema_hash"
    )
    resource_monitor_component = _verified_component_object(
        root, components, "resource_monitor", "receipt_hash"
    )
    cleanup_component = _verified_component_object(
        root, components, "cleanup_policy", "receipt_hash"
    )
    recovery_component = _verified_component_object(
        root, components, "recovery_checkpoint_policy", "receipt_hash"
    )
    if (
        environment.get("startup_policy_hash") != canonical_policy.policy_hash
        or environment.get("project_source_identity_hash")
        != startup.project_source_identity
        or frozen_policy != canonical_policy
        or startup.startup_policy_hash != canonical_policy.policy_hash
        or startup.startup_policy_hash != authorization.python_startup_policy_hash
        or environment.get("environment_manifest_hash")
        != authorization.python_environment_manifest_hash
        or sanitized.get("windows_environment_hash")
        != startup.sanitized_environment_hash
        or sanitized.get("receipt_hash") != authorization.sanitized_environment_hash
        or resource_budget.get("receipt_hash") != authorization.resource_budget_hash
        or reservation.get("receipt_hash")
        != authorization.storage_reservation_receipt_hash
        or resource_budget.get("status") != "PASS"
        or reservation.get("status") != "PASS"
        or reservation.get("sparse") is not False
        or bootstrap_component.get("source_bytes_hash")
        != authorization.bootstrap_source_hash
        or windows_launcher_component.get("source_bytes_hash")
        != authorization.windows_launcher_source_hash
        or karina_launcher.get("launcher_hash") != authorization.karina_launcher_hash
        or startup_schema.get("schema_hash")
        != authorization.startup_receipt_schema_hash
        or resource_monitor_component.get("source_bytes_hash")
        != authorization.resource_monitor_hash
        or cleanup_component.get("source_bytes_hash")
        != authorization.cleanup_policy_hash
        or recovery_component.get("source_bytes_hash")
        != authorization.recovery_policy_hash
    ):
        raise M336K2ProtocolError("M336K5 frozen startup/resource binding changed")
    for name in (
        "windows_jdk_identity",
        "karina_jdk_identity",
        "karina_stable_host_identity",
        "execution_capsule_receipt",
    ):
        _verified_component_object(root, components, name, _primary_hash_field(name))
    parent = _nearest_existing_parent(Path(request.private_root))
    required = int(resource_budget.get("required_pre_f30_private_storage_bytes", 0))
    if required <= 0 or shutil.disk_usage(parent).free < required:
        raise M336K2ProtocolError("M336K5 Windows storage preflight failed")


def _verify_destination_set(root: Path, git: Path, request) -> None:
    expected = {
        "acquisition_ledger",
        "selector_ledger",
        "evaluator_ledger",
        "route_state_ledger",
        "vault",
        "selected_source_snapshot",
        "windows_production",
        "karina_production",
        "evaluator_root",
    }
    if set(request.final_destinations) != expected:
        raise M336K2ProtocolError("M336K5 final destination fields changed")
    raw = subprocess.run(
        (str(git), "worktree", "list", "--porcelain", "-z"),
        cwd=root,
        check=True,
        capture_output=True,
        env=m336k2_minimal_environment(),
    ).stdout
    worktrees = tuple(
        Path(item.removeprefix(b"worktree ").decode("utf-8")).resolve(strict=True)
        for item in raw.split(b"\0")
        if item.startswith(b"worktree ")
    )
    destinations = tuple(
        Path(value).resolve(strict=False)
        for value in request.final_destinations.values()
    ) + (
        Path(request.route_receipt).resolve(strict=False),
        Path(request.stage_state).resolve(strict=False),
        Path(request.stage_receipt_root).resolve(strict=False),
        Path(request.private_root).resolve(strict=False),
    )
    if (
        len(set(destinations)) != len(destinations)
        or any(path.exists() for path in destinations)
        or any(
            path.is_relative_to(worktree)
            for path in destinations
            for worktree in worktrees
        )
        or Path(request.route_ledger).resolve(strict=False)
        != Path(request.final_destinations["route_state_ledger"]).resolve(strict=False)
    ):
        raise M336K2ProtocolError(
            "M336K5 final destinations are stale, aliased, or inside Git"
        )


def _verify_attestation_and_lineage(root, git, request, freeze, bundle) -> None:
    if request.exact_f30_sha == "0" * 40:
        if request.f30_attestation is not None or request.purpose == "OFFICIAL":
            raise M336K2ProtocolError("M336K5 official request lacks exact F30")
        return
    if request.f30_attestation is None:
        raise M336K2ProtocolError("M336K5 exact F30 attestation is absent")
    value = _object(Path(request.f30_attestation).resolve(strict=True))
    if set(value) != set(M336K5CommittedFreezeAttestation.__dataclass_fields__):
        raise M336K2ProtocolError("M336K5 F30 attestation fields changed")
    attestation = M336K5CommittedFreezeAttestation(**value)
    body = dict(value)
    claimed = body.pop("attestation_hash")
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
        content_hash(body) != claimed
        or attestation.exact_f30_sha != request.exact_f30_sha
        or attestation.exact_q30_parent != freeze.exact_q30_sha
        or attestation.route_identity_bundle_hash != bundle.bundle_hash
        or not attestation.prospective_tree_matches
        or attestation.status != "PASS"
        or head != upstream
        or head != remote
        or head != request.exact_f30_sha
    ):
        raise M336K2ProtocolError("M336K5 exact F30 attestation is invalid")
    if branch != request_branch_ref(request) or _git(
        git, root, "status", "--porcelain=v1"
    ):
        raise M336K2ProtocolError("M336K5 exact final lineage is not clean/pushed")


def _verify_karina_host_and_storage(*, request, bundle, freeze, root, components):
    expected_karina_fields = {
        "private_execution_capsule",
        "public_execution_capsule_receipt",
        "executable_dependency_manifest",
        "ssh_executable",
        "ssh_key",
        "known_hosts_file",
        "worker_endpoint",
        "repository",
        "private_root",
        "private_capsule_remote",
        "javac",
    }
    karina = request.karina
    if set(karina) != expected_karina_fields:
        raise M336K2ProtocolError("M336K5 Karina invocation fields changed")
    capsule = load_private_execution_capsule(
        Path(karina["private_execution_capsule"]).resolve(strict=True)
    )
    public = public_execution_capsule_receipt_from_dict(
        _object(Path(karina["public_execution_capsule_receipt"]).resolve(strict=True))
    )
    dependencies = dependency_manifest_from_dict(
        _object(Path(karina["executable_dependency_manifest"]).resolve(strict=True))
    )
    frozen_capsule = _verified_component_object(
        root, components, "execution_capsule_receipt", "receipt_hash"
    )
    stable_host = _verified_component_object(
        root, components, "karina_stable_host_identity", "receipt_hash"
    )
    capsule_root = capsule.private_root
    route_root = PurePosixPath(karina["private_root"])
    if (
        capsule.repository_checkout.as_posix() != karina["repository"]
        or capsule.expected_head != freeze.implementation_tip
        or capsule.expected_public_receipt_hash != public.receipt_hash
        or capsule.javac_executable.as_posix() != karina["javac"]
        or not route_root.is_relative_to(capsule_root)
        or route_root == capsule_root
        or public.executable_dependency_manifest_hash != dependencies.manifest_hash
        or frozen_capsule.get("karina_public_execution_capsule_receipt_hash")
        != public.receipt_hash
        or frozen_capsule.get("karina_executable_dependency_manifest_hash")
        != dependencies.manifest_hash
        or stable_host.get("receipt_hash") != public.host_identity_receipt_hash
    ):
        raise M336K2ProtocolError("M336K5 Karina capsule/freeze binding changed")
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
    project_source_identity = compute_m336j_project_source_identity(
        root, Path(request.git_executable).resolve(strict=True)
    )
    host_component = next(
        item
        for item in registry.components
        if item.route_role == "REMOTE_HOST_PREFLIGHT"
    )
    host_request_hash = content_hash(
        (
            freeze.implementation_tip,
            public.receipt_hash,
            host_component.binding_hash,
        )
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
        host.get("execution_capsule_receipt_hash") != public.receipt_hash
        or host.get("host_identity_hash") != public.host_identity_receipt_hash
        or not isinstance(host.get("startup_receipt_hash"), str)
        or _HASH.fullmatch(host["startup_receipt_hash"]) is None
        or host.get("startup_receipt_hash") != storage.get("startup_receipt_hash")
        or storage.get("required_free_bytes") != 12 * 1024**3
        or storage.get("available_free_bytes", 0) < storage["required_free_bytes"]
        or storage.get("available_free_inodes", 0) < 100_000
    ):
        raise M336K2ProtocolError("M336K5 Karina live preledger gate failed")
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


def request_branch_ref(request: M336K5FinalRouteRequestV2) -> str:
    authorization = M336K5FinalAuthorization.from_dict(
        _object(Path(request.final_authorization).resolve(strict=True))
    )
    return authorization.branch_ref


def _verify_component_handle(
    root: Path, components: dict, name: str, supplied: Path
) -> None:
    component = components.get(name)
    if (
        component is None
        or root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
        != supplied
    ):
        raise M336K2ProtocolError(f"M336K5 frozen component handle changed: {name}")


def _verified_component_object(
    root: Path, components: dict, name: str, field: str
) -> dict:
    component = components.get(name)
    if component is None:
        raise M336K2ProtocolError(f"M336K5 frozen component is missing: {name}")
    path = root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
    value = _object(path)
    body = dict(value)
    claimed = body.pop(field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError(f"M336K5 component semantic hash changed: {name}")
    return value


def _primary_hash_field(name: str) -> str:
    return {
        "windows_jdk_identity": "receipt_hash",
        "karina_jdk_identity": "receipt_hash",
        "karina_stable_host_identity": "receipt_hash",
        "execution_capsule_receipt": "receipt_hash",
    }[name]


def _nearest_existing_parent(path: Path) -> Path:
    value = path.resolve(strict=False)
    while not value.exists():
        if value.parent == value:
            raise M336K2ProtocolError("M336K5 destination has no existing ancestor")
        value = value.parent
    return value


def _strict_object(raw: bytes) -> dict:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise M336K2ProtocolError(
                    "M336K5 request contains a duplicate JSON key"
                )
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K5 final request JSON is invalid") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K5 final request is not an object")
    return value


def _object(path: Path) -> dict:
    value = _strict_object(path.read_bytes())
    return value


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
