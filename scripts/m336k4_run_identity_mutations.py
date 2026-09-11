"""Execute the exact public-safe M-33.6k.4 identity mutation matrix."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
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
    verify_m336k4_route_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k4_identity import (
    M336K4AcquisitionRunId,
    M336K4EvaluatorRunId,
    M336K4ProtocolRunId,
    M336K4RouteIdentityBundle,
    M336K4RouteVersion,
    M336K4SelectorRunId,
)
from ai_brain.stage3.acquisition.m336k4_request import (
    build_m336k4_final_route_request,
    load_m336k4_final_route_request,
    validate_m336k4_final_invocation,
    write_m336k4_final_route_request,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request_path = args.request.resolve(strict=True)
    workspace = args.workspace.resolve(strict=False)
    output = args.output.resolve(strict=False)
    if workspace.exists() or output.exists() or output.is_relative_to(workspace):
        raise M336K2ProtocolError("M336K4 mutation destinations are not fresh")
    workspace.mkdir(parents=True)
    try:
        receipt = run_mutation_matrix(request_path, workspace)
        _write(output, receipt)
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    print(canonical_json(receipt))


def run_mutation_matrix(request_path: Path, workspace: Path) -> dict:
    request_value = _object(request_path)
    request = load_m336k4_final_route_request(request_path)
    bundle_value = _object(Path(request.route_identity_bundle))
    bundle = M336K4RouteIdentityBundle.from_dict(bundle_value)
    cases: list[dict] = []

    def rejected(
        case_id: int,
        name: str,
        layer: str,
        operation,
        expected_text: str,
    ) -> None:
        accepted = False
        observed_layer = layer
        error_class = None
        try:
            operation()
            accepted = True
            observed_layer = "ACCEPTED_INVALID"
        except (M336K2ProtocolError, FileNotFoundError) as error:
            error_class = type(error).__name__
            if expected_text not in str(error):
                observed_layer = "WRONG_REJECTION_LAYER"
        cases.append(
            {
                "case_id": case_id,
                "case": name,
                "expected_rejection_layer": layer,
                "observed_rejection_layer": observed_layer,
                "accepted_invalid": accepted,
                "error_class": error_class,
                "status": "FAIL"
                if accepted or observed_layer == "WRONG_REJECTION_LAYER"
                else "PASS",
            }
        )

    def mutated_request(
        name: str,
        *,
        changes: dict | None = None,
        add: dict | None = None,
        rehash: bool = True,
    ) -> Path:
        value = dict(request_value)
        value.update(changes or {})
        value.update(add or {})
        if rehash:
            body = dict(value)
            body.pop("request_hash", None)
            value["request_hash"] = content_hash(body)
        path = workspace / f"{name}.json"
        _write(path, value)
        return path

    def mutated_bundle(name: str, field: str, identity: dict) -> Path:
        value = dict(bundle_value)
        value[field] = identity
        body = dict(value)
        body.pop("bundle_hash", None)
        value["bundle_hash"] = content_hash(body)
        path = workspace / f"{name}-bundle.json"
        _write(path, value)
        return mutated_request(name, changes={"route_identity_bundle": str(path)})

    def identity_value(identity, value: str) -> dict:
        result = identity.canonical_object()
        result["value"] = value
        body = {
            key: result[key] for key in ("schema_version", "identity_kind", "value")
        }
        result["identity_hash"] = content_hash(body)
        return result

    rejected(
        1,
        "historical_f28_wrong_request",
        "EXTERNAL_REQUEST_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "01-historical-f28",
                add={"route_run_id": "m336k2.final-java.route.v1"},
            )
        ),
        "caller-selected identity",
    )
    cross_types = (
        (
            2,
            "route_version_in_protocol_field",
            "protocol_run_id",
            M336K4RouteVersion(
                "m336k4.candidate-isolated-java-final-route.v1"
            ).canonical_object(),
        ),
        (
            3,
            "protocol_id_in_route_version_field",
            "route_version",
            M336K4ProtocolRunId("m336k4.final-java.outcome-a.v1").canonical_object(),
        ),
        (
            4,
            "acquisition_id_in_protocol_field",
            "protocol_run_id",
            M336K4AcquisitionRunId(
                "m336k4.final-java.global-acquisition.v1"
            ).canonical_object(),
        ),
        (
            5,
            "selector_id_in_evaluator_field",
            "evaluator_run_id",
            M336K4SelectorRunId("m336k4.final-java.selector.v1").canonical_object(),
        ),
        (
            6,
            "evaluator_id_in_selector_field",
            "selector_run_id",
            M336K4EvaluatorRunId("m336k4.final-java.evaluator.v1").canonical_object(),
        ),
    )
    for case_id, name, field, identity in cross_types:
        rejected(
            case_id,
            name,
            "TYPED_BUNDLE_LOADER",
            lambda name=name, field=field, identity=identity: (
                validate_m336k4_final_invocation(mutated_bundle(name, field, identity))
            ),
            "type was confused",
        )
    rejected(
        7,
        "external_request_contains_route_run_id",
        "EXTERNAL_REQUEST_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "07-external-route-run-id",
                add={"route_run_id": bundle.protocol_run_id.value},
            )
        ),
        "caller-selected identity",
    )
    protocol_mutations = (
        (8, "old_wrong_id", "m336k2.final-java.route.v1"),
        (14, "case_mutation", bundle.protocol_run_id.value.upper()),
        (15, "whitespace_mutation", f" {bundle.protocol_run_id.value}"),
        (
            16,
            "unicode_confusable",
            bundle.protocol_run_id.value.replace("a.v1", "а.v1"),
        ),
    )
    for case_id, name, value in protocol_mutations:
        rejected(
            case_id,
            name,
            "TYPED_BUNDLE_LOADER",
            lambda name=name, value=value: validate_m336k4_final_invocation(
                mutated_bundle(
                    name,
                    "protocol_run_id",
                    identity_value(bundle.protocol_run_id, value),
                )
            ),
            "M336K4",
        )
    rejected(
        9,
        "wrong_execution_mode",
        "TYPED_BUNDLE_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_bundle(
                "09-wrong-mode",
                "execution_mode",
                identity_value(bundle.execution_mode, "REHEARSAL"),
            )
        ),
        "namespace is invalid",
    )

    authorization_value = _object(Path(request.final_authorization))
    changed_authorization = dict(authorization_value)
    changed_authorization["protocol_run_id_typed"] = M336K4ProtocolRunId(
        "m336k4.disposable.authorization-mismatch.v1"
    ).canonical_object()
    authorization_body = dict(changed_authorization)
    authorization_body.pop("authorization_hash", None)
    changed_authorization["authorization_hash"] = content_hash(authorization_body)
    authorization_path = workspace / "10-authorization-mismatch.json"
    _write(authorization_path, changed_authorization)
    rejected(
        10,
        "authorization_freeze_final_id_mismatch",
        "AUTHORIZATION_BUNDLE_CROSS_BINDING",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "10-authorization-mismatch-request",
                changes={"final_authorization": str(authorization_path)},
            )
        ),
        "authorization/identity bundle mismatch",
    )

    event = "ACQUISITION_RESERVED"
    stage_body = {
        "schema_version": 1,
        "event": event,
        "route_run_id": "m336k2.final-java.route.v1",
        "execution_mode": "FINAL",
        "exact_f28_sha": request.exact_f29_sha,
        "context_hash": "1" * 64,
        "previous_operation_hash": "2" * 64,
    }
    stage_request = M336K2StageRequest(
        **stage_body, request_hash=content_hash(stage_body)
    )
    rejected(
        11,
        "stage_request_changes_final_id",
        "CONTROLLER_STAGE_PREFLIGHT",
        lambda: M336K4IdentityCheckingWorker(
            lambda _request: (_ for _ in ()).throw(AssertionError("worker invoked")),
            receipt_root=workspace,
            bundle=bundle,
        )(stage_request),
        "stage request changed final identity",
    )

    valid_stage_body = {**stage_body, "route_run_id": bundle.protocol_run_id.value}
    valid_stage_request = M336K2StageRequest(
        **valid_stage_body, request_hash=content_hash(valid_stage_body)
    )
    native_body = {
        "schema_version": 2,
        "contract_role": "M336K2_PRIVATE_NATIVE_STAGE_RECEIPT",
        "event": event,
        "route_run_id": "m336k2.final-java.route.v1",
        "exact_f28_sha": request.exact_f29_sha,
        "operation_hash": "3" * 64,
        "state_hash": "4" * 64,
        "status": "PASS",
        "route_identity_bundle_hash": bundle.bundle_hash,
    }
    _write(
        workspace / f"{event}.json",
        {**native_body, "receipt_hash": content_hash(native_body)},
    )
    receipt_body = {
        "schema_version": 1,
        "event": event,
        "request_hash": valid_stage_request.request_hash,
        "operation_hash": "5" * 64,
        "status": "PASS",
    }
    stage_receipt = M336K2StageReceipt(
        **receipt_body, receipt_hash=content_hash(receipt_body)
    )
    rejected(
        12,
        "worker_response_changes_final_id",
        "CONTROLLER_WORKER_RESPONSE_PREFLIGHT",
        lambda: M336K4IdentityCheckingWorker(
            lambda _request: stage_receipt,
            receipt_root=workspace,
            bundle=bundle,
        )(valid_stage_request),
        "worker response changed final identity",
    )

    ledger = M336K2RouteLedger(workspace / "13-route-ledger.jsonl", git_worktrees=())
    ledger.append("PREFLIGHT_VERIFIED", context_hash="6" * 64, operation_hash="7" * 64)
    rejected(
        13,
        "ledger_context_changes_final_id",
        "ROUTE_LEDGER_IDENTITY_PREFLIGHT",
        lambda: verify_m336k4_route_ledger_identity(
            ledger,
            bundle=bundle,
            exact_f29_sha=request.exact_f29_sha,
            preledger_receipt_hash="8" * 64,
        ),
        "route ledger context changed final identity",
    )

    rejected(
        17,
        "missing_route_identity_bundle",
        "TYPED_BUNDLE_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "17-missing-bundle",
                changes={"route_identity_bundle": str(workspace / "absent.json")},
            )
        ),
        "",
    )
    stale_bundle = dict(bundle_value)
    stale_bundle["route_registry_hash"] = "9" * 64
    stale_body = dict(stale_bundle)
    stale_body.pop("bundle_hash", None)
    stale_bundle["bundle_hash"] = content_hash(stale_body)
    stale_path = workspace / "18-stale-bundle.json"
    _write(stale_path, stale_bundle)
    rejected(
        18,
        "stale_route_identity_bundle",
        "AUTHORIZATION_BUNDLE_CROSS_BINDING",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "18-stale-bundle-request",
                changes={"route_identity_bundle": str(stale_path)},
            )
        ),
        "authorization/identity bundle mismatch",
    )
    wrong_hash_bundle = {**bundle_value, "bundle_hash": "f" * 64}
    wrong_hash_path = workspace / "19-wrong-bundle-hash.json"
    _write(wrong_hash_path, wrong_hash_bundle)
    rejected(
        19,
        "wrong_bundle_hash",
        "TYPED_BUNDLE_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "19-wrong-bundle-hash-request",
                changes={"route_identity_bundle": str(wrong_hash_path)},
            )
        ),
        "route identity bundle is invalid",
    )
    rejected(
        20,
        "disposable_and_official_builder_differ",
        "CANONICAL_REQUEST_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "20-builder-identity",
                changes={"builder_identity_hash": "a" * 64},
            )
        ),
        "canonical final request is invalid",
    )
    rejected(
        21,
        "serialized_request_manually_edited",
        "CANONICAL_REQUEST_LOADER",
        lambda: validate_m336k4_final_invocation(
            mutated_request(
                "21-manual-edit",
                changes={"purpose": "OFFICIAL"},
                rehash=False,
            )
        ),
        "canonical final request is invalid",
    )

    # Invoke the canonical tracked builder as part of the executable matrix.
    builder_values = {
        name: value
        for name, value in request._body().items()
        if name
        not in {
            "schema_version",
            "contract_role",
            "builder_identity_hash",
        }
    }
    rebuilt = build_m336k4_final_route_request(**builder_values)
    rebuilt_path = workspace / "canonical-rebuilt-request.json"
    write_m336k4_final_route_request(rebuilt, rebuilt_path)
    if rebuilt != request:
        raise M336K2ProtocolError("M336K4 canonical request builder is not stable")

    validated = validate_m336k4_final_invocation(rebuilt_path)
    destination_paths = tuple(
        Path(value) for value in validated.request.final_destinations.values()
    )
    no_ledgers = all(
        not Path(validated.request.final_destinations[name]).exists()
        for name in (
            "route_state_ledger",
            "acquisition_ledger",
            "selector_ledger",
            "evaluator_ledger",
        )
    )
    side_effect_cases = (
        (
            22,
            "preledger_creates_a_ledger",
            no_ledgers and validated.receipt.route_ledger_writes == 0,
        ),
        (
            23,
            "preledger_creates_a_vault",
            not Path(validated.request.final_destinations["vault"]).exists()
            and validated.receipt.vault_files == 0,
        ),
        (
            24,
            "preledger_performs_a_source_get",
            validated.receipt.source_requests == 0,
        ),
        (
            25,
            "preledger_reserves_selector_or_evaluator",
            not Path(validated.request.final_destinations["selector_ledger"]).exists()
            and not Path(
                validated.request.final_destinations["evaluator_ledger"]
            ).exists()
            and validated.receipt.selector_reservations == 0
            and validated.receipt.selector_invocations == 0
            and validated.receipt.evaluator_reservations == 0
            and validated.receipt.evaluator_invocations == 0,
        ),
    )
    for case_id, name, passed in side_effect_cases:
        cases.append(
            {
                "case_id": case_id,
                "case": name,
                "expected_rejection_layer": "SIDE_EFFECT_FREE_PRELEDGER",
                "observed_rejection_layer": "SIDE_EFFECT_FREE_PRELEDGER",
                "accepted_invalid": False,
                "error_class": None,
                "status": "PASS" if passed else "FAIL",
            }
        )
    if any(path.exists() for path in destination_paths):
        raise M336K2ProtocolError("M336K4 mutation preflight created a destination")

    cases.sort(key=lambda item: item["case_id"])
    accepted = sum(item["accepted_invalid"] for item in cases)
    wrong_layer = sum(
        item["observed_rejection_layer"] == "WRONG_REJECTION_LAYER" for item in cases
    )
    failed = sum(item["status"] != "PASS" for item in cases)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_IDENTITY_MUTATION_MATRIX",
        "canonical_final_request_hash": request.request_hash,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "preledger_invocation_receipt_hash": validated.receipt.receipt_hash,
        "case_count": len(cases),
        "invalid_case_count": 21,
        "side_effect_case_count": 4,
        "accepted_invalid_case_count": accepted,
        "wrong_rejection_layer_count": wrong_layer,
        "failed_case_count": failed,
        "cases": tuple(cases),
        "status": "PASS"
        if len(cases) == 25 and accepted == wrong_layer == failed == 0
        else "FAIL",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    if receipt["status"] != "PASS":
        raise M336K2ProtocolError("M336K4 identity mutation matrix failed")
    return receipt


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K4 mutation input is not an object")
    return value


if __name__ == "__main__":
    main()
