"""Typed M-33.6k.5 controller with no caller-selected final identity."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2StageReceipt,
    M336K2StageRequest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_ROUTE_EVENTS,
    M336K2ProtocolError,
    M336K2RouteLedger,
)
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5_PROTOCOL_RUN_ID,
    M336K5RouteIdentityBundle,
)
from ai_brain.stage3.acquisition.m336k5_request import M336K5ValidatedInvocation
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger


class M336K5StageWorker(Protocol):
    def __call__(self, request: M336K2StageRequest) -> M336K2StageReceipt: ...


@dataclass(frozen=True)
class M336K5FinalRouteReceipt:
    schema_version: int
    contract_role: str
    protocol_run_id: dict
    route_identity_bundle_hash: str
    exact_f30_sha: str
    route_registry_hash: str
    route_ledger_receipt_hash: str
    final_event: str
    acquisition_count: int
    selector_count: int
    evaluator_reservation_count: int
    retry_count: int
    status: str
    receipt_hash: str


def run_m336k5_final_controller(
    *,
    validated: M336K5ValidatedInvocation,
    ledger: M336K2RouteLedger,
    preledger_guard: Callable[[], object],
    worker: M336K5StageWorker,
    output: Path,
) -> M336K5FinalRouteReceipt:
    request = validated.request
    bundle = validated.bundle
    if output.exists() or ledger.events():
        raise M336K2ProtocolError("M336K5 final controller destinations are not fresh")
    _verify_final_identity(request.purpose, bundle)
    proof = preledger_guard()
    if proof != validated.receipt:
        raise M336K2ProtocolError(
            "M336K5 pre-ledger proof differs from exact validation"
        )
    context = content_hash(
        (
            bundle.protocol_run_id.canonical_object(),
            bundle.bundle_hash,
            request.exact_f30_sha,
            bundle.route_registry_hash,
            validated.receipt.receipt_hash,
        )
    )
    initial = (
        ("PREFLIGHT_VERIFIED", validated.receipt.receipt_hash),
        ("FREEZE_VERIFIED", validated.freeze.manifest_hash),
        ("AUTHORIZATION_VALIDATED", validated.authorization.authorization_hash),
    )
    previous = validated.receipt.receipt_hash
    for event, operation in initial:
        ledger.append(event, context_hash=context, operation_hash=operation)
        previous = operation
    try:
        for event in M336K2_ROUTE_EVENTS[len(initial) :]:
            body = {
                "schema_version": 1,
                "event": event,
                "route_run_id": bundle.protocol_run_id.value,
                "execution_mode": bundle.execution_mode.value,
                "exact_f28_sha": request.exact_f30_sha,
                "context_hash": context,
                "previous_operation_hash": previous,
            }
            stage_request = M336K2StageRequest(**body, request_hash=content_hash(body))
            receipt = worker(stage_request)
            _verify_worker_receipt(stage_request, receipt)
            ledger.append(
                event, context_hash=context, operation_hash=receipt.operation_hash
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
    ledger_receipt = ledger.receipt()
    body = {
        "schema_version": 2,
        "contract_role": "PUBLIC_SAFE_M336K5_FINAL_ROUTE_RECEIPT",
        "protocol_run_id": bundle.protocol_run_id.canonical_object(),
        "route_identity_bundle_hash": bundle.bundle_hash,
        "exact_f30_sha": request.exact_f30_sha,
        "route_registry_hash": bundle.route_registry_hash,
        "route_ledger_receipt_hash": ledger_receipt.receipt_hash,
        "final_event": ledger_receipt.final_event,
        "acquisition_count": ledger_receipt.acquisition_invocation_count,
        "selector_count": ledger_receipt.selector_invocation_count,
        "evaluator_reservation_count": ledger_receipt.evaluator_reservation_count,
        "retry_count": ledger_receipt.retry_count,
        "status": "OUTCOME A — VERIFIED_GENERALIZATION",
    }
    result = M336K5FinalRouteReceipt(**body, receipt_hash=content_hash(body))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json({**body, "receipt_hash": result.receipt_hash}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


class M336K5IdentityCheckingWorker:
    """Verify native stage identity observations after every frozen command."""

    def __init__(
        self,
        worker: M336K5StageWorker,
        *,
        receipt_root: Path,
        bundle: M336K5RouteIdentityBundle,
        expected_startup_receipt_hash: str,
    ) -> None:
        self._worker = worker
        self._receipt_root = receipt_root
        self._bundle = bundle
        self._expected_startup_receipt_hash = expected_startup_receipt_hash

    def __call__(self, request: M336K2StageRequest) -> M336K2StageReceipt:
        if request.route_run_id != self._bundle.protocol_run_id.value:
            raise M336K2ProtocolError("M336K5 stage request changed final identity")
        result = self._worker(request)
        path = self._receipt_root / f"{request.event}.json"
        try:
            value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise M336K2ProtocolError(
                "M336K5 native stage response is invalid"
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("route_run_id") != self._bundle.protocol_run_id.value
            or value.get("route_identity_bundle_hash") != self._bundle.bundle_hash
            or value.get("startup_receipt_hash") != self._expected_startup_receipt_hash
        ):
            raise M336K2ProtocolError("M336K5 worker response changed final identity")
        return result


def verify_m336k5_route_ledger_identity(
    ledger: M336K2RouteLedger,
    *,
    bundle: M336K5RouteIdentityBundle,
    exact_f30_sha: str,
    preledger_receipt_hash: str,
) -> str:
    context = content_hash(
        (
            bundle.protocol_run_id.canonical_object(),
            bundle.bundle_hash,
            exact_f30_sha,
            bundle.route_registry_hash,
            preledger_receipt_hash,
        )
    )
    events = ledger.events()
    if not events or any(event.context_hash != context for event in events):
        raise M336K2ProtocolError("M336K5 route ledger context changed final identity")
    return context


def verify_m336k5_acquisition_ledger_identity(
    ledger: M336KAcquisitionLedger,
    *,
    bundle: M336K5RouteIdentityBundle,
    exact_f30_sha: str,
    authorization_hash: str,
    candidate_pool_hash: str,
) -> str:
    context = content_hash(
        (
            exact_f30_sha,
            authorization_hash,
            candidate_pool_hash,
            bundle.bundle_hash,
        )
    )
    events = ledger.events()
    if not events or any(event.context_hash != context for event in events):
        raise M336K2ProtocolError(
            "M336K5 acquisition ledger context changed final identity"
        )
    return context


def verify_m336k5_selector_ledger_identity(
    ledger: M336FSelectorLedger,
    *,
    bundle: M336K5RouteIdentityBundle,
    qualification_report_hash: str,
    qualification_summary_hash: str,
    census_hash: str,
    closure_manifest_hash: str,
    feasibility_proof_hash: str,
    binding_manifest_hash: str,
) -> str:
    context = content_hash(
        (
            qualification_report_hash,
            qualification_summary_hash,
            census_hash,
            closure_manifest_hash,
            feasibility_proof_hash,
            binding_manifest_hash,
            bundle.bundle_hash,
        )
    )
    events = ledger.events()
    if not events or any(event["context_hash"] != context for event in events):
        raise M336K2ProtocolError(
            "M336K5 selector ledger context changed final identity"
        )
    return context


def verify_m336k5_evaluator_ledger_identity(
    path: Path,
    *,
    bundle: M336K5RouteIdentityBundle,
    exact_h29_sha: str,
    windows_production_seal_hash: str,
    karina_production_seal_hash: str,
) -> str:
    events = _evaluator_events(path)
    expected = content_hash(
        (
            exact_h29_sha,
            windows_production_seal_hash,
            karina_production_seal_hash,
            bundle.bundle_hash,
        )
    )
    if not events or events[0]["operation_hash"] != expected:
        raise M336K2ProtocolError(
            "M336K5 evaluator ledger context changed final identity"
        )
    return expected


def _evaluator_events(path: Path) -> tuple[dict, ...]:
    order = (
        "EVALUATOR_RESERVED",
        "GOLDENS_CREATED",
        "WINDOWS_EVALUATION_COMPLETED",
        "KARINA_EVALUATION_COMPLETED",
        "EVALUATION_COMPARISON_PASSED",
    )
    if not path.exists():
        return ()
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise M336K2ProtocolError("M336K5 evaluator ledger is not canonical")
    result = []
    previous = None
    for ordinal, line in enumerate(raw.splitlines(), start=1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise M336K2ProtocolError("M336K5 evaluator ledger is invalid") from error
        body = dict(value) if isinstance(value, dict) else {}
        claimed = body.pop("event_hash", None)
        if (
            ordinal > len(order)
            or not isinstance(value, dict)
            or set(value)
            != {
                "schema_version",
                "ordinal",
                "event",
                "operation_hash",
                "previous_event_hash",
                "event_hash",
            }
            or value.get("schema_version") != 1
            or value.get("ordinal") != ordinal
            or value.get("event") != order[ordinal - 1]
            or value.get("previous_event_hash") != previous
            or content_hash(body) != claimed
        ):
            raise M336K2ProtocolError("M336K5 evaluator ledger chain changed")
        result.append(value)
        previous = claimed
    return tuple(result)


def _verify_final_identity(purpose: str, bundle: M336K5RouteIdentityBundle) -> None:
    bundle.verify()
    if purpose not in {"DISPOSABLE", "OFFICIAL"}:
        raise M336K2ProtocolError("M336K5 qualification request is not executable")
    if bundle.execution_mode.value != "FINAL":
        raise M336K2ProtocolError("M336K5 controller execution mode is not FINAL")
    if purpose == "OFFICIAL" and bundle.protocol_run_id.value != M336K5_PROTOCOL_RUN_ID:
        raise M336K2ProtocolError("M336K5 official protocol run ID is not canonical")


def _verify_worker_receipt(
    request: M336K2StageRequest, receipt: M336K2StageReceipt
) -> None:
    body = {
        "schema_version": receipt.schema_version,
        "event": receipt.event,
        "request_hash": receipt.request_hash,
        "operation_hash": receipt.operation_hash,
        "status": receipt.status,
    }
    if (
        receipt.schema_version != 1
        or receipt.event != request.event
        or receipt.request_hash != request.request_hash
        or receipt.status != "PASS"
        or content_hash(body) != receipt.receipt_hash
    ):
        raise M336K2ProtocolError("M336K5 typed worker receipt is invalid")
