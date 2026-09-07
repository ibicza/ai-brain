"""Native M-33.6h final Java route state, guard, and readiness authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336h_evaluation import M336HEvaluatorLedger

FRESH_FREEZE_AUTHORIZATION_REQUIRED = "FRESH_FREEZE_AUTHORIZATION_REQUIRED"

M336H_ROUTE_STATES = (
    "INITIAL",
    "PREFLIGHT_PASSED",
    "ACQUISITION_INPUT_BOUND",
    "QUALIFICATION_SEALED",
    "CENSUS_SEALED",
    "COMPILATION_CLOSURE_SEALED",
    "CLOSURE_FEASIBILITY_PASSED",
    "SELECTOR_RESERVED",
    "SELECTION_COMPLETED",
    "SOURCE_SNAPSHOT_MATERIALIZED",
    "WINDOWS_PRODUCTION_SEALED",
    "KARINA_PRODUCTION_SEALED",
    "PUBLIC_PACK_VERIFIED",
    "SEALED_REPLAY_VERIFIED",
    "EVALUATOR_RESERVED",
    "EVALUATION_COMPLETED",
    "PUBLIC_STAGING_VALIDATED",
    "READY_FOR_FRESH_FREEZE",
)


@dataclass(frozen=True)
class M336HJavaRouteStateReceipt:
    schema_version: int
    state: str
    ordinal: int
    previous_receipt_hash: str | None
    context_hash: str
    receipt_hash: str


class M336HJavaRouteStateMachine:
    """In-memory monotonic state machine; one-shot ledgers remain external."""

    def __init__(self, *, context_hash: str) -> None:
        if len(context_hash) != 64:
            raise ValueError("M336H state-machine context must be a SHA-256 hash")
        body = {
            "schema_version": 1,
            "state": "INITIAL",
            "ordinal": 0,
            "previous_receipt_hash": None,
            "context_hash": context_hash,
        }
        self._receipts = [
            M336HJavaRouteStateReceipt(**body, receipt_hash=content_hash(body))
        ]

    @property
    def state(self) -> str:
        return self._receipts[-1].state

    @property
    def receipts(self) -> tuple[M336HJavaRouteStateReceipt, ...]:
        return tuple(self._receipts)

    def advance(self, state: str) -> M336HJavaRouteStateReceipt:
        expected = M336H_ROUTE_STATES[len(self._receipts)]
        if state != expected:
            raise ValueError(
                f"M336H route state is skipped or repeated: expected {expected}"
            )
        previous = self._receipts[-1]
        body = {
            "schema_version": 1,
            "state": state,
            "ordinal": len(self._receipts),
            "previous_receipt_hash": previous.receipt_hash,
            "context_hash": previous.context_hash,
        }
        receipt = M336HJavaRouteStateReceipt(**body, receipt_hash=content_hash(body))
        self._receipts.append(receipt)
        return receipt


@dataclass(frozen=True)
class M336HNoFinalAcquisitionReceipt:
    schema_version: int
    contract_role: str
    authorization_status: str
    final_acquisition_reservation_count: int
    final_acquisition_invocation_count: int
    new_final_source_body_byte_count: int
    final_selector_reservation_count: int
    final_selector_invocation_count: int
    final_evaluator_reservation_count: int
    final_evaluator_invocation_count: int
    network_access_count: int
    ledger_write_count: int
    vault_mutation_count: int
    receipt_hash: str


class M336HFinalAcquisitionAuthorizationError(RuntimeError):
    def __init__(self, receipt: M336HNoFinalAcquisitionReceipt) -> None:
        super().__init__(FRESH_FREEZE_AUTHORIZATION_REQUIRED)
        self.receipt = receipt


@dataclass(frozen=True)
class KarinaHostIdentityReceipt:
    schema_version: int
    contract_role: str
    role: str
    hostname_hash: str
    ssh_host_key_fingerprint_hash: str
    os_family: str
    architecture: str
    public_jdk_identity_receipt_hash: str
    repository_identity_hash: str
    verification_status: str
    receipt_hash: str


def build_karina_host_identity_receipt(
    *,
    hostname_hash: str,
    ssh_host_key_fingerprint_hash: str,
    os_family: str,
    architecture: str,
    public_jdk_identity_receipt_hash: str,
    repository_identity_hash: str,
) -> KarinaHostIdentityReceipt:
    hashes = (
        hostname_hash,
        ssh_host_key_fingerprint_hash,
        public_jdk_identity_receipt_hash,
        repository_identity_hash,
    )
    if any(
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in hashes
    ):
        raise ValueError("Karina public identity contains an invalid hash")
    if not os_family or not architecture:
        raise ValueError("Karina public platform identity is incomplete")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_PLATFORM_IDENTITY",
        "role": "KARINA_BUILD_HOST",
        "hostname_hash": hostname_hash,
        "ssh_host_key_fingerprint_hash": ssh_host_key_fingerprint_hash,
        "os_family": os_family,
        "architecture": architecture,
        "public_jdk_identity_receipt_hash": public_jdk_identity_receipt_hash,
        "repository_identity_hash": repository_identity_hash,
        "verification_status": "PASS",
    }
    return KarinaHostIdentityReceipt(**body, receipt_hash=content_hash(body))


def verify_karina_host_identity_consistency(
    left: KarinaHostIdentityReceipt, right: KarinaHostIdentityReceipt
) -> None:
    for value in (left, right):
        body = asdict(value)
        claimed = body.pop("receipt_hash")
        if content_hash(body) != claimed or value.verification_status != "PASS":
            raise ValueError("Karina host identity receipt is invalid")
    if left != right:
        raise ValueError("Karina endpoints identify different machines")


def build_m336h_no_final_acquisition_receipt() -> M336HNoFinalAcquisitionReceipt:
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_RECEIPT",
        "authorization_status": FRESH_FREEZE_AUTHORIZATION_REQUIRED,
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "new_final_source_body_byte_count": 0,
        "final_selector_reservation_count": 0,
        "final_selector_invocation_count": 0,
        "final_evaluator_reservation_count": 0,
        "final_evaluator_invocation_count": 0,
        "network_access_count": 0,
        "ledger_write_count": 0,
        "vault_mutation_count": 0,
    }
    return M336HNoFinalAcquisitionReceipt(**body, receipt_hash=content_hash(body))


def validate_m336h_empty_acquisition_ledger(path: Path) -> dict:
    resolved = path.resolve(strict=False)
    if resolved.exists() and resolved.stat().st_size:
        raise ValueError("M336H final acquisition ledger is not empty")
    return {
        "reservation_count": 0,
        "invocation_count": 0,
        "ledger_bytes_hash": bytes_hash(b""),
        "status": "PASS",
    }


def refuse_m336h_unfrozen_final_acquisition(
    *,
    future_f23_manifest: dict | None = None,
    future_m336i_authorization: dict | None = None,
    acquisition_ledger: Path | None = None,
    frozen_candidate_pool_hash: str | None = None,
    frozen_acquisition_policy_hash: str | None = None,
) -> None:
    """Refuse before ledger, network, source, or vault access until M-33.6i."""

    receipt = build_m336h_no_final_acquisition_receipt()
    if (
        future_f23_manifest is None
        or future_m336i_authorization is None
        or acquisition_ledger is None
        or frozen_candidate_pool_hash is None
        or frozen_acquisition_policy_hash is None
    ):
        raise M336HFinalAcquisitionAuthorizationError(receipt)
    raise M336HFinalAcquisitionAuthorizationError(receipt)


def load_m336h_metadata_pool(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336H metadata pool must be an object")
    return value


def open_m336h_selector_ledger(
    path: Path, *, git_worktrees: tuple[Path, ...] = ()
) -> M336FSelectorLedger:
    return M336FSelectorLedger(path, git_worktrees=git_worktrees)


def open_m336h_evaluator_ledger(
    path: Path, *, git_worktrees: tuple[Path, ...] = ()
) -> M336HEvaluatorLedger:
    return M336HEvaluatorLedger(path, git_worktrees=git_worktrees)


@dataclass(frozen=True)
class M336HFinalJavaRouteReadiness:
    schema_version: int
    contract_role: str
    r23_implementation_identity: str
    q23_evidence_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    selector_policy_hash: str
    selector_algorithm_version: str
    selector_seed_hash: str
    request_response_schema_hashes: tuple[str, ...]
    publication_boundary_hash: str
    threshold_manifest_hash: str
    disclosed_rehearsal_receipt_hash: str
    count_neutral_rehearsal_receipt_hash: str
    windows_quality_receipt_hash: str
    karina_quality_receipt_hash: str
    cross_platform_comparison_receipt_hash: str
    no_final_acquisition_receipt_hash: str
    resolved_component_count: int
    unresolved_component_count: int
    route_edge_count: int
    incompatible_route_edge_count: int
    schema_edge_count: int
    incompatible_schema_edge_count: int
    legacy_selector_reachable_from_final_route: bool
    disclosed_wrapper_reachable_from_final_route: bool
    compiler_aware_inputs_mandatory: bool
    disclosed_rehearsal_status: str
    count_neutral_rehearsal_status: str
    windows_production_status: str
    karina_production_status: str
    independent_evaluation_status: str
    public_pack_integrity_status: str
    sealed_replay_status: str
    platform_neutral_difference_count: int
    source_leak_count: int
    absolute_path_count: int
    private_role_public_count: int
    final_acquisition_reservation_count: int
    final_acquisition_invocation_count: int
    final_selector_reservation_count: int
    final_selector_invocation_count: int
    status: str
    readiness_hash: str


_READINESS_INPUT_FIELDS = {
    item
    for item in M336HFinalJavaRouteReadiness.__dataclass_fields__
    if item not in {"schema_version", "contract_role", "status", "readiness_hash"}
}


def derive_m336h_final_java_route_readiness(
    evidence: dict,
) -> M336HFinalJavaRouteReadiness:
    if not isinstance(evidence, dict) or set(evidence) != _READINESS_INPUT_FIELDS:
        raise ValueError("M336H readiness evidence set is incomplete or substituted")
    hash_fields = {
        name
        for name in _READINESS_INPUT_FIELDS
        if name.endswith(("_hash", "_identity"))
    }
    for name in hash_fields:
        value = evidence[name]
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"M336H readiness binding is invalid: {name}")
    passed = (
        evidence["resolved_component_count"] > 0
        and evidence["unresolved_component_count"] == 0
        and evidence["route_edge_count"] > 0
        and evidence["incompatible_route_edge_count"] == 0
        and evidence["schema_edge_count"] > 0
        and evidence["incompatible_schema_edge_count"] == 0
        and evidence["legacy_selector_reachable_from_final_route"] is False
        and evidence["disclosed_wrapper_reachable_from_final_route"] is False
        and evidence["compiler_aware_inputs_mandatory"] is True
        and all(
            evidence[name] == "PASS"
            for name in (
                "disclosed_rehearsal_status",
                "count_neutral_rehearsal_status",
                "windows_production_status",
                "karina_production_status",
                "independent_evaluation_status",
                "public_pack_integrity_status",
                "sealed_replay_status",
            )
        )
        and all(
            evidence[name] == 0
            for name in (
                "platform_neutral_difference_count",
                "source_leak_count",
                "absolute_path_count",
                "private_role_public_count",
                "final_acquisition_reservation_count",
                "final_acquisition_invocation_count",
                "final_selector_reservation_count",
                "final_selector_invocation_count",
            )
        )
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_READINESS",
        **evidence,
        "request_response_schema_hashes": tuple(
            evidence["request_response_schema_hashes"]
        ),
        "status": "READY_FOR_FRESH_FREEZE" if passed else "REPAIR_BLOCKED",
    }
    readiness = M336HFinalJavaRouteReadiness(**body, readiness_hash=content_hash(body))
    if readiness.status != "READY_FOR_FRESH_FREEZE":
        raise ValueError("M336H final Java route is not ready for fresh freeze")
    return readiness


def readiness_from_dict(value: dict) -> M336HFinalJavaRouteReadiness:
    if set(value) != set(M336HFinalJavaRouteReadiness.__dataclass_fields__):
        raise ValueError("M336H readiness schema changed")
    result = M336HFinalJavaRouteReadiness(
        **{
            **value,
            "request_response_schema_hashes": tuple(
                value["request_response_schema_hashes"]
            ),
        }
    )
    body = asdict(result)
    claimed = body.pop("readiness_hash")
    if content_hash(body) != claimed:
        raise ValueError("M336H readiness hash mismatch")
    recomputed = derive_m336h_final_java_route_readiness(
        {name: getattr(result, name) for name in _READINESS_INPUT_FIELDS}
    )
    if recomputed != result:
        raise ValueError("M336H readiness evidence changed")
    return result
