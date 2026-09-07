"""Discoverable native controller for the M-33.6h final Java route."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
    java_compilation_closure_manifest_from_dict,
    verify_java_compilation_closure_feasibility_proof,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    select_compilation_closed_sources_once,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336h_evaluation import (
    evaluation_request_from_dict,
    run_m336h_independent_java_evaluation,
)
from ai_brain.stage3.acquisition.m336h_materialization import (
    materialize_m336f_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336h_production import (
    M336HCompilerAwareProductionRequest,
    build_m336h_count_neutral_production_seal,
    production_seal_from_dict,
    run_m336h_compiler_aware_production,
)
from ai_brain.stage3.acquisition.m336h_registry import (
    build_m336h_final_java_route_manifest,
    build_m336h_final_java_route_registry,
    preflight_m336h_final_java_route,
)
from ai_brain.stage3.acquisition.m336h_route import (
    M336HFinalAcquisitionAuthorizationError,
    build_m336h_no_final_acquisition_receipt,
    derive_m336h_final_java_route_readiness,
    refuse_m336h_unfrozen_final_acquisition,
)


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path.name}")
    return value


def _preflight(args) -> None:
    registry = build_m336h_final_java_route_registry()
    manifest = build_m336h_final_java_route_manifest(registry)
    receipt = preflight_m336h_final_java_route(registry, manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    write_canonical_json(args.output / "route_component_registry.json", registry)
    write_canonical_json(args.output / "route_manifest.json", manifest)
    write_canonical_json(args.output / "route_preflight_receipt.json", receipt)
    policy_body = {
        "schema_version": 1,
        "route_component_id": manifest.selector_route_component_id,
        "selector_algorithm_version": manifest.selector_algorithm_version,
        "selector_seed_hash": manifest.selector_seed_hash,
        "feasibility_before_reservation": True,
        "selector_reservations": 1,
        "selector_invocations": 1,
        "selector_reruns": 0,
    }
    write_canonical_json(
        args.output / "selector_policy.json",
        {**policy_body, "selector_policy_hash": content_hash(policy_body)},
    )
    threshold_body = {
        "schema_version": 1,
        "minimum_metrics": {
            "trust_precision": "1.000000",
            "trust_coverage": "0.950000",
            "location_precision": "1.000000",
            "location_recall": "0.950000",
            "semantic_precision": "1.000000",
            "semantic_recall": "0.950000",
            "field_evidence_exactness": "1.000000",
            "spdx_agreement": "1.000000",
        },
        "maximum_wrong_trusted_count": 0,
        "maximum_false_automatic_spdx_identity_count": 0,
    }
    write_canonical_json(
        args.output / "threshold_manifest.json",
        {**threshold_body, "threshold_manifest_hash": content_hash(threshold_body)},
    )


def _run_rehearsal(args) -> None:
    config = _object(args.config)
    required = {
        "repository",
        "sealed_vault",
        "qualification_report",
        "qualification_summary",
        "bindings",
        "census",
        "closure_manifest",
        "closure_proof",
        "selector_ledger",
        "selected_snapshot",
        "private_replay_root",
        "production_output",
        "javac",
        "preflight_root",
        "publication_boundary_contract_hash",
        "selector_seed",
    }
    if set(config) != required:
        raise ValueError("M336H rehearsal config fields changed")
    repository = Path(config["repository"]).resolve(strict=True)
    preflight = Path(config["preflight_root"]).resolve(strict=True)
    live_registry = build_m336h_final_java_route_registry()
    live_manifest = build_m336h_final_java_route_manifest(live_registry)
    manifest_value = _object(preflight / "route_manifest.json")
    if manifest_value != json.loads(json.dumps(asdict(live_manifest))):
        raise ValueError("M336H rehearsal route manifest differs from executable code")
    bindings = source_entry_binding_manifest_from_dict(
        _object(Path(config["bindings"]))
    )
    census = selectable_source_census_from_dict(_object(Path(config["census"])))
    closure = java_compilation_closure_manifest_from_dict(
        _object(Path(config["closure_manifest"]))
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _object(Path(config["closure_proof"]))
    )
    verify_java_compilation_closure_feasibility_proof(proof, closure, census)
    qualification = _object(Path(config["qualification_report"]))
    summary = _object(Path(config["qualification_summary"]))
    ledger = M336FSelectorLedger(
        Path(config["selector_ledger"]), git_worktrees=(repository,)
    )
    selected, selector = select_compilation_closed_sources_once(
        census=census,
        closure_manifest=closure,
        proof=proof,
        bindings=bindings,
        selector_seed=config["selector_seed"],
        ledger=ledger,
        qualification_report_hash=qualification["report_hash"],
        qualification_summary_hash=summary["summary_hash"],
    )
    args.output.mkdir(parents=True, exist_ok=False)
    selected_path = args.output / "selected_source_manifest.json"
    selector_path = args.output / "selector_receipt.json"
    write_canonical_json(selected_path, selected)
    write_canonical_json(selector_path, selector)
    write_canonical_json(args.output / "selector_ledger_receipt.json", ledger.receipt())
    materialized = materialize_m336f_selected_source_snapshot(
        sealed_vault_root=Path(config["sealed_vault"]),
        bindings=bindings,
        selected_manifest=selected,
        selector_receipt=selector,
        closure_manifest=closure,
        closure_proof=proof,
        destination=Path(config["selected_snapshot"]),
        git_worktrees=(repository,),
        public_roots=(args.output, Path(config["production_output"])),
    )
    write_canonical_json(args.output / "materialization_receipt.json", materialized)
    javac = Path(config["javac"]).resolve(strict=True)
    java = javac.with_name(
        "java.exe" if javac.name.casefold().endswith(".exe") else "java"
    )
    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform=args.platform.casefold(), java=java, javac=javac
    )
    threshold = _object(preflight / "threshold_manifest.json")
    request = M336HCompilerAwareProductionRequest(
        route_manifest_hash=live_manifest.manifest_hash,
        implementation_identity=live_registry.registry_hash,
        platform_role=args.platform,
        source_snapshot_private_handle=Path(config["selected_snapshot"]),
        javac_private_handle=javac,
        public_jdk_identity_receipt_hash=public_jdk.receipt_hash,
        source_entry_bindings=Path(config["bindings"]),
        selected_manifest=selected_path,
        selector_receipt=selector_path,
        closure_manifest=Path(config["closure_manifest"]),
        closure_feasibility_proof=Path(config["closure_proof"]),
        sealed_vault=Path(config["sealed_vault"]),
        private_replay_root=Path(config["private_replay_root"]),
        public_production_destination=Path(config["production_output"]),
        publication_boundary_contract_hash=config["publication_boundary_contract_hash"],
        threshold_manifest_hash=threshold["threshold_manifest_hash"],
    )
    response = run_m336h_compiler_aware_production(request)
    seal = build_m336h_count_neutral_production_seal(
        production_root=Path(config["production_output"]), response=response
    )
    write_canonical_json(args.output / "production_seal.json", seal)
    body = {
        "schema_version": 1,
        "rehearsal_kind": args.command.removeprefix("rehearse-").upper(),
        "platform_role": args.platform,
        "route_manifest_hash": live_manifest.manifest_hash,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "materialization_receipt_hash": materialized.receipt_hash,
        "production_response_hash": response.response_hash,
        "production_seal_hash": seal.seal_hash,
        "selected_file_count": selected.file_count,
        "selected_root_count": selected.root_count,
        "closure_support_file_count": selected.closure_support_file_count,
        "proposal_count": seal.proposal_count,
        "trusted_count": seal.trusted_count,
        "withheld_count": seal.withheld_count,
        "network_access_count": seal.production_network_access_count,
        "status": "PASS",
    }
    write_canonical_json(
        args.output / "rehearsal_receipt.json",
        {**body, "receipt_hash": content_hash(body)},
    )


def _produce_worker(args) -> None:
    value = _object(args.request)
    from ai_brain.stage3.acquisition.m336h_production import (
        compiler_aware_production_request_from_dict,
    )

    response = run_m336h_compiler_aware_production(
        compiler_aware_production_request_from_dict(value)
    )
    write_canonical_json(args.output, response)


def _verify_seals(args) -> None:
    windows = production_seal_from_dict(_object(args.windows))
    karina = production_seal_from_dict(_object(args.karina))
    excluded = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    left = {key: value for key, value in asdict(windows).items() if key not in excluded}
    right = {key: value for key, value in asdict(karina).items() if key not in excluded}
    body = {
        "schema_version": 1,
        "windows_seal_hash": windows.seal_hash,
        "karina_seal_hash": karina.seal_hash,
        "platform_private_field_count": len(excluded),
        "platform_neutral_difference_count": int(left != right),
        "status": "PASS" if left == right else "FAIL",
    }
    if body["status"] != "PASS":
        raise ValueError("M336H production seals differ in platform-neutral fields")
    write_canonical_json(args.output, {**body, "receipt_hash": content_hash(body)})


def _evaluate(args) -> None:
    request = evaluation_request_from_dict(_object(args.request))
    result = run_m336h_independent_java_evaluation(request)
    write_canonical_json(args.output, result)


def _derive_readiness(args) -> None:
    readiness = derive_m336h_final_java_route_readiness(_object(args.evidence))
    write_canonical_json(args.output, readiness)


def _final(args) -> None:
    receipt = build_m336h_no_final_acquisition_receipt()
    if args.output:
        write_canonical_json(args.output, receipt)
    refuse_m336h_unfrozen_final_acquisition()


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--output", type=Path, required=True)
    for name in ("rehearse-disclosed", "rehearse-count-neutral"):
        rehearsal = commands.add_parser(name)
        rehearsal.add_argument("--config", type=Path, required=True)
        rehearsal.add_argument(
            "--platform", choices=("WINDOWS", "KARINA"), required=True
        )
        rehearsal.add_argument("--output", type=Path, required=True)
    worker = commands.add_parser("produce-worker")
    worker.add_argument("--request", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    seals = commands.add_parser("verify-production-seals")
    seals.add_argument("--windows", type=Path, required=True)
    seals.add_argument("--karina", type=Path, required=True)
    seals.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate-rehearsal")
    evaluate.add_argument("--request", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    readiness = commands.add_parser("derive-readiness")
    readiness.add_argument("--evidence", type=Path, required=True)
    readiness.add_argument("--output", type=Path, required=True)
    final = commands.add_parser("final")
    final.add_argument("--output", type=Path)
    args = parser.parse_args()
    handlers = {
        "preflight": _preflight,
        "rehearse-disclosed": _run_rehearsal,
        "rehearse-count-neutral": _run_rehearsal,
        "produce-worker": _produce_worker,
        "verify-production-seals": _verify_seals,
        "evaluate-rehearsal": _evaluate,
        "derive-readiness": _derive_readiness,
        "final": _final,
    }
    try:
        handlers[args.command](args)
    except M336HFinalAcquisitionAuthorizationError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(23) from error


if __name__ == "__main__":
    main()
