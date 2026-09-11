from __future__ import annotations

from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2StageReceipt,
    M336K2StageRequest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
)
from ai_brain.stage3.acquisition.m336k4_controller import (
    M336K4IdentityCheckingWorker,
    verify_m336k4_acquisition_ledger_identity,
    verify_m336k4_evaluator_ledger_identity,
    verify_m336k4_route_ledger_identity,
    verify_m336k4_selector_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k4_identity import (
    M336K4AcquisitionRunId,
    M336K4EvaluatorRunId,
    M336K4ExecutionMode,
    M336K4ProtocolRunId,
    M336K4RouteIdentityBundle,
    M336K4RouteVersion,
    M336K4SelectorRunId,
    build_m336k4_official_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k4_request import (
    build_m336k4_final_route_request,
    load_m336k4_final_route_request,
    validate_m336k4_final_invocation,
    write_m336k4_final_route_request,
)
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger

HASHES = {
    "route_registry_hash": "1" * 64,
    "route_manifest_hash": "2" * 64,
    "acquisition_policy_hash": "3" * 64,
    "selector_policy_hash": "4" * 64,
    "evaluator_policy_hash": "5" * 64,
}


def _bundle() -> M336K4RouteIdentityBundle:
    return build_m336k4_official_identity_bundle(**HASHES)


def _write(path: Path, value: dict) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _request_values(tmp_path: Path, bundle_path: Path) -> dict:
    destination = tmp_path / "fresh"
    return {
        "purpose": "QUALIFICATION",
        "repository": str(Path.cwd()),
        "git_executable": str(Path("C:/Program Files/Git/cmd/git.exe")),
        "python_executable": str(Path("C:/Python/python.exe")),
        "exact_implementation_sha": "a" * 40,
        "exact_f29_sha": "0" * 40,
        "freeze_manifest": str(tmp_path / "freeze.json"),
        "f29_attestation": None,
        "final_authorization": str(tmp_path / "authorization.json"),
        "route_identity_bundle": str(bundle_path),
        "publication_contract": str(tmp_path / "publication.json"),
        "route_ledger": str(destination / "route.jsonl"),
        "route_receipt": str(destination / "route.json"),
        "stage_state": str(destination / "state.json"),
        "stage_receipt_root": str(destination / "receipts"),
        "private_root": str(destination / "private"),
        "authority_statement": str(tmp_path / "authority.txt"),
        "frozen_spdx_reference": str(tmp_path / "spdx.json"),
        "windows_java": str(Path("C:/Java/bin/java.exe")),
        "windows_javac": str(Path("C:/Java/bin/javac.exe")),
        "final_destinations": {
            "acquisition_ledger": str(destination / "acquisition.jsonl"),
            "selector_ledger": str(destination / "selector.jsonl"),
            "evaluator_ledger": str(destination / "evaluator.jsonl"),
            "route_state_ledger": str(destination / "route.jsonl"),
            "vault": str(destination / "vault"),
            "selected_source_snapshot": str(destination / "selected"),
            "windows_production": str(destination / "windows"),
            "karina_production": str(destination / "karina"),
            "evaluator_root": str(destination / "evaluator"),
        },
        "karina": {"opaque": "fixture"},
        "executable_handles": {"opaque": "fixture"},
    }


def _request_path(tmp_path: Path, bundle_value: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, bundle_value)
    request = build_m336k4_final_route_request(**_request_values(tmp_path, bundle_path))
    path = tmp_path / "request.json"
    write_m336k4_final_route_request(request, path)
    return path


def _mutated_identity(identity, *, value: str | None = None, kind: str | None = None):
    body = identity.canonical_object()
    body["value"] = value if value is not None else body["value"]
    body["identity_kind"] = kind if kind is not None else body["identity_kind"]
    identity_body = {
        name: body[name] for name in ("schema_version", "identity_kind", "value")
    }
    body["identity_hash"] = content_hash(identity_body)
    return body


def _mutated_bundle(
    bundle: M336K4RouteIdentityBundle, field: str, identity: dict
) -> dict:
    value = bundle.canonical_object()
    value[field] = identity
    body = dict(value)
    body.pop("bundle_hash")
    value["bundle_hash"] = content_hash(body)
    return value


@pytest.mark.parametrize(
    ("field", "identity"),
    (
        (
            "protocol_run_id",
            M336K4RouteVersion("m336k4.candidate-isolated-java-final-route.v1"),
        ),
        ("route_version", M336K4ProtocolRunId("m336k4.final-java.outcome-a.v1")),
        (
            "protocol_run_id",
            M336K4AcquisitionRunId("m336k4.final-java.global-acquisition.v1"),
        ),
        ("evaluator_run_id", M336K4SelectorRunId("m336k4.final-java.selector.v1")),
        ("selector_run_id", M336K4EvaluatorRunId("m336k4.final-java.evaluator.v1")),
    ),
)
def test_real_preflight_rejects_cross_type_identity(
    tmp_path: Path, field: str, identity
) -> None:
    path = _request_path(
        tmp_path, _mutated_bundle(_bundle(), field, identity.canonical_object())
    )
    with pytest.raises(M336K2ProtocolError):
        validate_m336k4_final_invocation(path)


@pytest.mark.parametrize(
    "value",
    (
        "m336k2.final-java.route.v1",
        "unknown.protocol.v1",
        " m336k4.final-java.outcome-a.v1",
        "m336k4.final-java.outcome-a.v1 ",
        "M336K4.final-java.outcome-a.v1",
        "m336k4.final-java.outcome-а.v1",
        "",
        "m336k4.final-java.operator-choice.v1",
    ),
)
def test_real_preflight_rejects_noncanonical_protocol_id(
    tmp_path: Path, value: str
) -> None:
    identity = _mutated_identity(_bundle().protocol_run_id, value=value)
    path = _request_path(
        tmp_path, _mutated_bundle(_bundle(), "protocol_run_id", identity)
    )
    with pytest.raises(M336K2ProtocolError):
        validate_m336k4_final_invocation(path)


def test_semantic_identity_equality_is_type_strict() -> None:
    protocol = M336K4ProtocolRunId("m336k4.final-java.outcome-a.v1")
    route = M336K4RouteVersion("m336k4.candidate-isolated-java-final-route.v1")
    assert protocol == M336K4ProtocolRunId(protocol.value)
    assert protocol != route
    assert protocol.canonical_json() == canonical_json(protocol.canonical_object())


def test_external_request_rejects_historical_route_run_id(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, _bundle().canonical_object())
    request = build_m336k4_final_route_request(**_request_values(tmp_path, bundle_path))
    value = request.canonical_object()
    value["route_run_id"] = "m336k2.final-java.route.v1"
    body = dict(value)
    body.pop("request_hash")
    value["request_hash"] = content_hash(body)
    path = tmp_path / "request.json"
    _write(path, value)
    with pytest.raises(M336K2ProtocolError, match="caller-selected identity"):
        load_m336k4_final_route_request(path)


def test_wrong_execution_mode_rejected_by_real_preflight(tmp_path: Path) -> None:
    identity = _mutated_identity(_bundle().execution_mode, value="REHEARSAL")
    path = _request_path(
        tmp_path, _mutated_bundle(_bundle(), "execution_mode", identity)
    )
    with pytest.raises(M336K2ProtocolError):
        validate_m336k4_final_invocation(path)


def test_missing_and_wrong_bundle_rejected_by_real_preflight(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    request = build_m336k4_final_route_request(**_request_values(tmp_path, missing))
    path = tmp_path / "request.json"
    write_m336k4_final_route_request(request, path)
    with pytest.raises(FileNotFoundError):
        validate_m336k4_final_invocation(path)
    wrong = _bundle().canonical_object()
    wrong["bundle_hash"] = "0" * 64
    path = _request_path(tmp_path / "wrong", wrong)
    with pytest.raises(M336K2ProtocolError):
        validate_m336k4_final_invocation(path)


def test_canonical_serialized_request_rejects_manual_edit(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, _bundle().canonical_object())
    request = build_m336k4_final_route_request(**_request_values(tmp_path, bundle_path))
    path = tmp_path / "request.json"
    write_m336k4_final_route_request(request, path)
    path.write_text(
        path.read_text(encoding="utf-8").replace('"QUALIFICATION"', '"OFFICIAL"')
    )
    with pytest.raises(M336K2ProtocolError):
        load_m336k4_final_route_request(path)


def test_disposable_and_official_use_same_builder_function(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, _bundle().canonical_object())
    values = _request_values(tmp_path, bundle_path)
    first = build_m336k4_final_route_request(**values)
    second = build_m336k4_final_route_request(**values)
    assert first == second


def test_worker_response_identity_mutation_is_rejected(tmp_path: Path) -> None:
    bundle = _bundle()
    event = "ACQUISITION_RESERVED"
    native_body = {
        "schema_version": 2,
        "contract_role": "M336K2_PRIVATE_NATIVE_STAGE_RECEIPT",
        "event": event,
        "route_run_id": "m336k2.final-java.route.v1",
        "exact_f28_sha": "a" * 40,
        "operation_hash": "1" * 64,
        "state_hash": "2" * 64,
        "status": "PASS",
        "route_identity_bundle_hash": bundle.bundle_hash,
    }
    _write(
        tmp_path / f"{event}.json",
        {**native_body, "receipt_hash": content_hash(native_body)},
    )
    request_body = {
        "schema_version": 1,
        "event": event,
        "route_run_id": bundle.protocol_run_id.value,
        "execution_mode": "FINAL",
        "exact_f28_sha": "a" * 40,
        "context_hash": "3" * 64,
        "previous_operation_hash": "4" * 64,
    }
    request = M336K2StageRequest(
        **request_body, request_hash=content_hash(request_body)
    )
    receipt_body = {
        "schema_version": 1,
        "event": event,
        "request_hash": request.request_hash,
        "operation_hash": "5" * 64,
        "status": "PASS",
    }
    receipt = M336K2StageReceipt(
        **receipt_body, receipt_hash=content_hash(receipt_body)
    )
    worker = M336K4IdentityCheckingWorker(
        lambda _request: receipt, receipt_root=tmp_path, bundle=bundle
    )
    with pytest.raises(M336K2ProtocolError, match="worker response"):
        worker(request)


def test_route_ledger_context_identity_mutation_is_rejected(tmp_path: Path) -> None:
    ledger = M336K2RouteLedger(tmp_path / "route.jsonl", git_worktrees=())
    ledger.append("PREFLIGHT_VERIFIED", context_hash="a" * 64, operation_hash="b" * 64)
    with pytest.raises(M336K2ProtocolError, match="ledger context"):
        verify_m336k4_route_ledger_identity(
            ledger,
            bundle=_bundle(),
            exact_f29_sha="c" * 40,
            preledger_receipt_hash="d" * 64,
        )


def test_one_shot_ledger_identity_context_mutations_are_rejected(
    tmp_path: Path,
) -> None:
    bundle = _bundle()
    acquisition = M336KAcquisitionLedger(
        tmp_path / "acquisition.jsonl", git_worktrees=()
    )
    acquisition_context = content_hash(
        ("a" * 40, "b" * 64, "c" * 64, bundle.bundle_hash)
    )
    for event in (
        "AUTHORIZATION_VALIDATED",
        "ACQUISITION_RESERVED",
        "ACQUISITION_STARTED",
        "ALL_CANDIDATES_TERMINAL",
        "ACQUISITION_COMPLETED",
    ):
        acquisition.append(
            event, context_hash=acquisition_context, operation_hash="d" * 64
        )
    assert (
        verify_m336k4_acquisition_ledger_identity(
            acquisition,
            bundle=bundle,
            exact_f29_sha="a" * 40,
            authorization_hash="b" * 64,
            candidate_pool_hash="c" * 64,
        )
        == acquisition_context
    )
    with pytest.raises(M336K2ProtocolError, match="acquisition ledger context"):
        verify_m336k4_acquisition_ledger_identity(
            acquisition,
            bundle=bundle,
            exact_f29_sha="e" * 40,
            authorization_hash="b" * 64,
            candidate_pool_hash="c" * 64,
        )

    selector = M336FSelectorLedger(tmp_path / "selector.jsonl", git_worktrees=())
    selector_values = {
        "qualification_report_hash": "1" * 64,
        "qualification_summary_hash": "2" * 64,
        "census_hash": "3" * 64,
        "closure_manifest_hash": "4" * 64,
        "feasibility_proof_hash": "5" * 64,
        "binding_manifest_hash": "6" * 64,
    }
    selector_context = content_hash((*selector_values.values(), bundle.bundle_hash))
    for event in ("CENSUS_SEALED", "SELECTOR_RESERVED", "SELECTOR_COMPLETED"):
        selector.append(event, context_hash=selector_context)
    assert (
        verify_m336k4_selector_ledger_identity(
            selector, bundle=bundle, **selector_values
        )
        == selector_context
    )
    with pytest.raises(M336K2ProtocolError, match="selector ledger context"):
        verify_m336k4_selector_ledger_identity(
            selector,
            bundle=bundle,
            **{**selector_values, "binding_manifest_hash": "7" * 64},
        )

    evaluator = tmp_path / "evaluator.jsonl"
    operation = content_hash(("f" * 40, "8" * 64, "9" * 64, bundle.bundle_hash))
    previous = None
    rows = []
    for ordinal, event in enumerate(
        (
            "EVALUATOR_RESERVED",
            "GOLDENS_CREATED",
            "WINDOWS_EVALUATION_COMPLETED",
            "KARINA_EVALUATION_COMPLETED",
            "EVALUATION_COMPARISON_PASSED",
        ),
        start=1,
    ):
        body = {
            "schema_version": 1,
            "ordinal": ordinal,
            "event": event,
            "operation_hash": operation if ordinal == 1 else "0" * 64,
            "previous_event_hash": previous,
        }
        value = {**body, "event_hash": content_hash(body)}
        rows.append(canonical_json(value))
        previous = value["event_hash"]
    evaluator.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    assert (
        verify_m336k4_evaluator_ledger_identity(
            evaluator,
            bundle=bundle,
            exact_h29_sha="f" * 40,
            windows_production_seal_hash="8" * 64,
            karina_production_seal_hash="9" * 64,
        )
        == operation
    )
    with pytest.raises(M336K2ProtocolError, match="evaluator ledger context"):
        verify_m336k4_evaluator_ledger_identity(
            evaluator,
            bundle=bundle,
            exact_h29_sha="0" * 40,
            windows_production_seal_hash="8" * 64,
            karina_production_seal_hash="9" * 64,
        )


def test_identity_bundle_hash_mutation_cannot_be_replaced() -> None:
    bundle = _bundle()
    with pytest.raises(M336K2ProtocolError):
        M336K4RouteIdentityBundle.from_dict(
            {**bundle.canonical_object(), "bundle_hash": "f" * 64}
        )


def test_execution_mode_has_no_untyped_escape() -> None:
    with pytest.raises(M336K2ProtocolError):
        M336K4ExecutionMode("final")
