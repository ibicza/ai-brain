"""Single typed controller for rehearsal and official M-33.6k.2 execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_ROUTE_EVENTS,
    M336K2ProtocolError,
    M336K2RouteLedger,
)

M336K2_FINAL_RUN_ID = "m336k2.final-java.outcome-a.v1"
M336K2_ROUTE_STAGES = (
    "COMMITTED_FREEZE_VERIFICATION",
    "WINDOWS_AND_KARINA_HOST_PREFLIGHT",
    "STORAGE_PREFLIGHT",
    "GLOBAL_ACQUISITION",
    "CANDIDATE_TERMINAL_ACCOUNTING",
    "VAULT_SEALING",
    "KARINA_VAULT_TRANSFER_AND_VERIFICATION",
    "QUALIFICATION_AND_SOURCE_BINDING",
    "COMPILATION_CLOSURE_CENSUS",
    "GLOBAL_SELECTOR",
    "SELECTED_SOURCE_SNAPSHOT_SEALING",
    "SELECTED_SOURCE_TRANSFER_AND_VERIFICATION",
    "WINDOWS_COMPILER_AWARE_PRODUCTION",
    "KARINA_COMPILER_AWARE_PRODUCTION",
    "PUBLIC_PACK_VERIFICATION",
    "SEALED_REPLAY",
    "CROSS_PLATFORM_PRODUCTION_COMPARISON",
    "H28_SOURCE_FREE_PUBLICATION",
    "GLOBAL_EVALUATOR_RESERVATION",
    "POST_RESERVATION_GOLDEN_GENERATION",
    "WINDOWS_INDEPENDENT_EVALUATION",
    "KARINA_INDEPENDENT_EVALUATION",
    "SEMANTIC_COMPARISON",
    "INSTALLED_RUNTIME_PROOF",
    "E28_EVIDENCE_ONLY_PUBLICATION",
    "GIT_COMMIT_PROTOCOL_VERIFICATION",
    "FINAL_OUTCOME_DERIVATION",
    "RECOVERY_STATE_FINALIZATION",
)


@dataclass(frozen=True)
class M336K2SchemaBinding:
    schema_version: int
    stage: str
    producer: str
    consumer: str
    request_schema_hash: str
    response_schema_hash: str
    binding_hash: str


@dataclass(frozen=True)
class M336K2SchemaRegistry:
    schema_version: int
    route_version: str
    bindings: tuple[M336K2SchemaBinding, ...]
    incompatible_edge_count: int
    registry_hash: str


@dataclass(frozen=True)
class M336K2PreLedgerProof:
    schema_version: int
    preflight_receipt_hash: str
    freeze_receipt_hash: str
    authorization_receipt_hash: str
    exact_f28_sha: str
    route_registry_hash: str
    status: str
    proof_hash: str


@dataclass(frozen=True)
class M336K2StageRequest:
    schema_version: int
    event: str
    route_run_id: str
    execution_mode: str
    exact_f28_sha: str
    context_hash: str
    previous_operation_hash: str
    request_hash: str


@dataclass(frozen=True)
class M336K2StageReceipt:
    schema_version: int
    event: str
    request_hash: str
    operation_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K2FinalRouteReceipt:
    schema_version: int
    contract_role: str
    route_run_id: str
    execution_mode: str
    exact_f28_sha: str
    route_registry_hash: str
    route_ledger_receipt_hash: str
    final_event: str
    acquisition_count: int
    selector_count: int
    evaluator_reservation_count: int
    retry_count: int
    status: str
    receipt_hash: str


class M336K2StageWorker(Protocol):
    def __call__(self, request: M336K2StageRequest) -> M336K2StageReceipt: ...


def build_m336k2_schema_registry() -> M336K2SchemaRegistry:
    bindings = []
    for stage in M336K2_ROUTE_STAGES:
        request_schema = {
            "schema_version": 1,
            "schema_id": f"m336k2.{stage.casefold()}.request.v1",
            "required": (
                "event",
                "route_run_id",
                "execution_mode",
                "exact_f28_sha",
                "context_hash",
                "previous_operation_hash",
                "request_hash",
            ),
            "additional_properties": False,
        }
        response_schema = {
            "schema_version": 1,
            "schema_id": f"m336k2.{stage.casefold()}.response.v1",
            "required": (
                "event",
                "request_hash",
                "operation_hash",
                "status",
                "receipt_hash",
            ),
            "additional_properties": False,
        }
        body = {
            "schema_version": 1,
            "stage": stage,
            "producer": f"M336K2::{stage}",
            "consumer": "M336K2FinalController",
            "request_schema_hash": content_hash(request_schema),
            "response_schema_hash": content_hash(response_schema),
        }
        bindings.append(M336K2SchemaBinding(**body, binding_hash=content_hash(body)))
    body = {
        "schema_version": 1,
        "route_version": "m336k2.candidate-isolated-java-final-route.v1",
        "bindings": tuple(bindings),
        "incompatible_edge_count": 0,
    }
    return M336K2SchemaRegistry(**body, registry_hash=content_hash(body))


def build_preledger_proof(
    *,
    preflight_receipt_hash: str,
    freeze_receipt_hash: str,
    authorization_receipt_hash: str,
    exact_f28_sha: str,
    route_registry_hash: str,
) -> M336K2PreLedgerProof:
    values = {
        "schema_version": 1,
        "preflight_receipt_hash": preflight_receipt_hash,
        "freeze_receipt_hash": freeze_receipt_hash,
        "authorization_receipt_hash": authorization_receipt_hash,
        "exact_f28_sha": exact_f28_sha,
        "route_registry_hash": route_registry_hash,
        "status": "PASS",
    }
    proof = M336K2PreLedgerProof(**values, proof_hash=content_hash(values))
    _verify_preledger_proof(proof)
    return proof


def run_m336k2_final_controller(
    *,
    route_run_id: str,
    execution_mode: str,
    exact_f28_sha: str,
    route_registry_hash: str,
    ledger: M336K2RouteLedger,
    preledger_guard: Callable[[], M336K2PreLedgerProof],
    worker: M336K2StageWorker,
    output: Path,
) -> M336K2FinalRouteReceipt:
    """Execute the whole route; no operator-selected next script is possible."""

    if output.exists():
        raise FileExistsError("M336K2 final controller receipt must be fresh")
    if ledger.events():
        raise M336K2ProtocolError("M336K2 final controller ledger must be fresh")
    if execution_mode not in {"REHEARSAL", "FINAL"}:
        raise M336K2ProtocolError("M336K2 execution mode is invalid")
    if (execution_mode == "FINAL") != (route_run_id == M336K2_FINAL_RUN_ID):
        raise M336K2ProtocolError("M336K2 final run identity is reserved")
    schema_registry = build_m336k2_schema_registry()
    proof = preledger_guard()
    _verify_preledger_proof(proof)
    if (
        proof.exact_f28_sha != exact_f28_sha
        or proof.route_registry_hash != route_registry_hash
        or schema_registry.incompatible_edge_count != 0
    ):
        raise M336K2ProtocolError("M336K2 pre-ledger proof binding changed")
    context = content_hash(
        (
            route_run_id,
            execution_mode,
            exact_f28_sha,
            route_registry_hash,
            proof.proof_hash,
        )
    )
    initial = (
        ("PREFLIGHT_VERIFIED", proof.preflight_receipt_hash),
        ("FREEZE_VERIFIED", proof.freeze_receipt_hash),
        ("AUTHORIZATION_VALIDATED", proof.authorization_receipt_hash),
    )
    previous = proof.proof_hash
    for event, operation in initial:
        ledger.append(event, context_hash=context, operation_hash=operation)
        previous = operation
    try:
        for event in M336K2_ROUTE_EVENTS[len(initial) :]:
            request_body = {
                "schema_version": 1,
                "event": event,
                "route_run_id": route_run_id,
                "execution_mode": execution_mode,
                "exact_f28_sha": exact_f28_sha,
                "context_hash": context,
                "previous_operation_hash": previous,
            }
            request = M336K2StageRequest(
                **request_body, request_hash=content_hash(request_body)
            )
            receipt = worker(request)
            _verify_stage_receipt(request, receipt)
            ledger.append(
                event,
                context_hash=context,
                operation_hash=receipt.operation_hash,
            )
            previous = receipt.operation_hash
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        try:
            ledger.fail(
                context_hash=context,
                operation_hash=content_hash((type(error).__name__, str(error))),
            )
        except M336K2ProtocolError:
            pass
        raise
    receipt = ledger.receipt()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_FINAL_ROUTE_RECEIPT",
        "route_run_id": route_run_id,
        "execution_mode": execution_mode,
        "exact_f28_sha": exact_f28_sha,
        "route_registry_hash": route_registry_hash,
        "route_ledger_receipt_hash": receipt.receipt_hash,
        "final_event": receipt.final_event,
        "acquisition_count": receipt.acquisition_invocation_count,
        "selector_count": receipt.selector_invocation_count,
        "evaluator_reservation_count": receipt.evaluator_reservation_count,
        "retry_count": receipt.retry_count,
        "status": "OUTCOME A — VERIFIED_GENERALIZATION",
    }
    result = M336K2FinalRouteReceipt(**body, receipt_hash=content_hash(body))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(asdict(result)) + "\n", encoding="utf-8", newline="\n"
    )
    return result


def _verify_preledger_proof(proof: M336K2PreLedgerProof) -> None:
    body = asdict(proof)
    claimed = body.pop("proof_hash")
    hashes = (
        proof.preflight_receipt_hash,
        proof.freeze_receipt_hash,
        proof.authorization_receipt_hash,
        proof.route_registry_hash,
    )
    if (
        proof.schema_version != 1
        or proof.status != "PASS"
        or len(proof.exact_f28_sha) != 40
        or any(len(value) != 64 for value in hashes)
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 pre-ledger proof is invalid")


def _verify_stage_receipt(
    request: M336K2StageRequest, receipt: M336K2StageReceipt
) -> None:
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if (
        receipt.schema_version != 1
        or receipt.event != request.event
        or receipt.request_hash != request.request_hash
        or receipt.status != "PASS"
        or len(receipt.operation_hash) != 64
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 stage receipt is invalid")
