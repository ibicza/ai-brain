"""Stage final M-33.6i independent Outcome A evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336h_evaluation import M336HEvaluatorLedger
from ai_brain.stage3.acquisition.m336i_acquisition import M336IFinalAcquisitionLedger
from ai_brain.stage3.acquisition.m336i_readiness import (
    M336I_EXACT_Q23_SHA,
    verify_m336i_quality_receipt,
)
from ai_brain.stage3.acquisition.m336i_route import M336IRouteStateLedger


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I E24 input must be an object")
    return value


def _verified(path: Path, field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I E24 {field} differs from content")
    return value


def _rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode(),
        )
    )


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "repository",
        "final_route_receipt",
        "independent_evaluation",
        "h24_validation_receipt",
        "windows_h24_quality_receipt",
        "karina_h24_quality_receipt",
        "acquisition_ledger",
        "route_state_ledger",
        "selector_ledger",
        "evaluator_ledger",
        "windows_production_seal",
        "karina_production_seal",
        "sealed_vault",
        "h24_public_root",
        "output",
        "validation_output",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--expected-h24-sha", required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    validation_output = args.validation_output.resolve(strict=False)
    if _git(repository, "rev-parse", "HEAD^{commit}") != args.expected_h24_sha or _git(
        repository, "status", "--porcelain=v1"
    ):
        raise ValueError("M336I E24 publisher requires clean exact H24")
    if output.exists() or validation_output.exists():
        raise FileExistsError("M336I E24 destinations must be fresh")
    if not output.is_relative_to(repository) or validation_output.is_relative_to(
        repository
    ):
        raise ValueError("M336I E24 public/external destinations are misplaced")
    final = _verified(args.final_route_receipt, "receipt_hash")
    evaluation = _verified(args.independent_evaluation, "result_hash")
    h24_validation = _verified(args.h24_validation_receipt, "receipt_hash")
    windows_h24_quality = verify_m336i_quality_receipt(
        args.windows_h24_quality_receipt, "WINDOWS", args.expected_h24_sha
    )
    karina_h24_quality = verify_m336i_quality_receipt(
        args.karina_h24_quality_receipt, "KARINA", args.expected_h24_sha
    )
    windows_seal = _verified(args.windows_production_seal, "seal_hash")
    karina_seal = _verified(args.karina_production_seal, "seal_hash")
    acquisition_receipt = _verified(
        args.h24_public_root / "receipts" / "acquisition_receipt.json",
        "receipt_hash",
    )
    if (
        final.get("status") != "OUTCOME A"
        or evaluation.get("status") != "PASS"
        or h24_validation.get("status") != "PASS"
        or windows_h24_quality.get("status") != "PASS"
        or karina_h24_quality.get("status") != "PASS"
        or final.get("contract_role") != "PUBLIC_SAFE_M336I_FINAL_ROUTE_RECEIPT"
        or final.get("f24_sha") != _git(repository, "rev-parse", "HEAD^1")
        or final.get("acquisition_receipt_hash")
        != acquisition_receipt.get("receipt_hash")
        or final.get("windows_production_seal_hash") != windows_seal.get("seal_hash")
        or final.get("karina_production_seal_hash") != karina_seal.get("seal_hash")
        or windows_seal.get("status") != "PASS"
        or karina_seal.get("status") != "PASS"
        or windows_seal.get("public_candidate_pack_hash")
        != karina_seal.get("public_candidate_pack_hash")
        or windows_seal.get("public_candidate_pack_tree_hash")
        != karina_seal.get("public_candidate_pack_tree_hash")
        or evaluation.get("public_candidate_pack_hash")
        != windows_seal.get("public_candidate_pack_hash")
        or evaluation.get("public_candidate_pack_tree_hash")
        != windows_seal.get("public_candidate_pack_tree_hash")
        or evaluation.get("platform_neutral_difference_count") != 0
    ):
        raise ValueError("M336I E24 Outcome A prerequisites failed")
    acquisition = M336IFinalAcquisitionLedger(args.acquisition_ledger).receipt()
    route = M336IRouteStateLedger(args.route_state_ledger).receipt()
    selector = M336FSelectorLedger(args.selector_ledger).receipt()
    evaluator_events = M336HEvaluatorLedger(args.evaluator_ledger).events()
    counters = {
        "global_acquisition_reservations": acquisition.acquisition_reservation_count,
        "global_acquisition_invocations": acquisition.acquisition_start_count,
        "windows_acquisition_invocations": acquisition_receipt[
            "windows_acquisition_invocation_count"
        ],
        "karina_acquisition_invocations": acquisition_receipt[
            "karina_acquisition_invocation_count"
        ],
        "acquisition_reruns": acquisition.acquisition_rerun_count,
        "selector_reservations": selector["selector_reservation_count"],
        "selector_invocations": selector["selector_invocation_count"],
        "selector_reruns": selector["selector_rerun_count"],
        "evaluator_reservations": sum(
            item["event"] == "EVALUATOR_RESERVED" for item in evaluator_events
        ),
        "evaluator_invocations": sum(
            item["event"] == "EVALUATOR_COMPLETED" for item in evaluator_events
        ),
    }
    if (
        tuple(counters.values()) != (1, 1, 1, 0, 0, 1, 1, 0, 1, 1)
        or not route.complete
        or route.final_state != "OUTCOME_A_READY"
    ):
        raise ValueError("M336I E24 one-shot counters are not exact")

    output.mkdir(parents=True)
    shutil.copyfile(args.independent_evaluation, output / "independent_evaluation.json")
    comparison_body = {
        "schema_version": 1,
        "windows_production_seal_hash": windows_seal["seal_hash"],
        "karina_production_seal_hash": karina_seal["seal_hash"],
        "candidate_pack_content_hash": windows_seal["public_candidate_pack_hash"],
        "candidate_pack_tree_hash": windows_seal["public_candidate_pack_tree_hash"],
        "platform_neutral_difference_count": evaluation[
            "platform_neutral_difference_count"
        ],
        "status": "PASS",
    }
    comparison = {**comparison_body, "receipt_hash": content_hash(comparison_body)}
    write_canonical_json(output / "cross_platform_comparison.json", comparison)
    counter_body = {
        "schema_version": 1,
        **counters,
        "acquisition_ledger_receipt_hash": acquisition.receipt_hash,
        "route_state_ledger_receipt_hash": route.receipt_hash,
        "selector_ledger_receipt_hash": selector["receipt_hash"],
        "evaluator_final_event_hash": evaluator_events[-1]["event_hash"],
        "status": "PASS",
    }
    counters_receipt = {**counter_body, "receipt_hash": content_hash(counter_body)}
    write_canonical_json(output / "final_one_shot_counters.json", counters_receipt)
    publication_body = {
        "schema_version": 1,
        "h24_staging_receipt_hash": h24_validation["receipt_hash"],
        "post_scan_mutation_count": h24_validation["post_scan_modified_file_count"],
        "unscanned_intended_file_count": h24_validation[
            "unscanned_committed_file_count"
        ],
        "scanned_file_omission_count": h24_validation[
            "scanned_file_omitted_from_manifest_count"
        ],
        "status": "PASS",
    }
    if any(
        publication_body[name] != 0
        for name in (
            "post_scan_mutation_count",
            "unscanned_intended_file_count",
            "scanned_file_omission_count",
        )
    ):
        raise ValueError("M336I E24 publication boundary counters are not zero")
    publication = {
        **publication_body,
        "report_hash": content_hash(publication_body),
    }
    write_canonical_json(output / "publication_boundary_report.json", publication)
    security_body = {
        "schema_version": 1,
        "wrong_trusted_count": evaluation["wrong_trusted_count"],
        "false_automatic_spdx_identity_count": evaluation[
            "false_automatic_spdx_identity_count"
        ],
        "production_network_access_count": windows_seal[
            "production_network_access_count"
        ]
        + karina_seal["production_network_access_count"],
        "source_bearing_public_entry_count": windows_seal[
            "source_bearing_public_entry_count"
        ],
        "private_role_public_entry_count": windows_seal[
            "private_role_public_entry_count"
        ],
        "unknown_public_entry_count": windows_seal["unknown_public_entry_count"],
        "absolute_path_count": windows_seal["absolute_path_count"],
        "reversible_source_payload_count": windows_seal[
            "reversible_source_payload_count"
        ],
        "status": "PASS",
    }
    if any(
        security_body[name] != 0
        for name in (
            "wrong_trusted_count",
            "false_automatic_spdx_identity_count",
            "production_network_access_count",
            "source_bearing_public_entry_count",
            "private_role_public_entry_count",
            "unknown_public_entry_count",
            "absolute_path_count",
            "reversible_source_payload_count",
        )
    ):
        raise ValueError("M336I E24 security counters are not zero")
    security = {**security_body, "report_hash": content_hash(security_body)}
    write_canonical_json(output / "security_summary.json", security)
    performance_body = {
        "schema_version": 1,
        "platform_private_metrics_location": "EXTERNAL_ONLY",
        "windows_production_response_hash": windows_seal["production_response_hash"],
        "karina_production_response_hash": karina_seal["production_response_hash"],
        "status": "PASS",
    }
    performance = {**performance_body, "report_hash": content_hash(performance_body)}
    write_canonical_json(output / "performance_summary.json", performance)
    merge_count = int(
        _git(
            repository,
            "rev-list",
            "--count",
            "--merges",
            f"{M336I_EXACT_Q23_SHA}..HEAD",
        )
    )
    if merge_count:
        raise ValueError("M336I E24 history contains a merge commit")
    commit_body = {
        "schema_version": 1,
        "h24_sha": args.expected_h24_sha,
        "e24_contains_own_sha": False,
        "f24_sha": final["f24_sha"],
        "merge_commit_count": merge_count,
        "status": "PASS",
    }
    commit = {**commit_body, "report_hash": content_hash(commit_body)}
    write_canonical_json(output / "commit_protocol_report.json", commit)
    leak = scan_fresh_source_leaks(args.sealed_vault, (args.h24_public_root, output))
    if leak["status"] != "PASS":
        raise ValueError("M336I E24 pre-outcome leak scan failed")
    write_canonical_json(output / "source_leak_report.json", leak)
    final_report_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_FINAL_REPORT",
        "h24_sha": args.expected_h24_sha,
        "final_route_receipt_hash": final["receipt_hash"],
        "independent_evaluation_hash": evaluation["result_hash"],
        "cross_platform_comparison_hash": comparison["receipt_hash"],
        "source_leak_report_hash": leak["report_hash"],
        "publication_boundary_report_hash": publication["report_hash"],
        "counter_report_hash": counters_receipt["receipt_hash"],
        "performance_summary_hash": performance["report_hash"],
        "security_summary_hash": security["report_hash"],
        "windows_h24_quality_receipt_hash": windows_h24_quality["receipt_hash"],
        "karina_h24_quality_receipt_hash": karina_h24_quality["receipt_hash"],
        "status": "OUTCOME A",
    }
    final_report = {
        **final_report_body,
        "report_hash": content_hash(final_report_body),
    }
    write_canonical_json(output / "final_m336_report.json", final_report)
    prospective_identity = content_hash(_rows(output))
    outcome_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_FINAL_OUTCOME_A",
        "status": "OUTCOME A",
        "exact_h24_sha": args.expected_h24_sha,
        "prospective_e24_evidence_identity": prospective_identity,
        "prospective_identity_excludes": ["final_outcome_a_receipt.json"],
        "final_report_hash": final_report["report_hash"],
        "independent_evaluation_hash": evaluation["result_hash"],
        "external_route_receipt_hash": final["receipt_hash"],
        "route_state_ledger_receipt_hash": route.receipt_hash,
    }
    outcome = {**outcome_body, "receipt_hash": content_hash(outcome_body)}
    write_canonical_json(output / "final_outcome_a_receipt.json", outcome)
    post_scan = scan_fresh_source_leaks(
        args.sealed_vault, (args.h24_public_root, output)
    )
    if post_scan["status"] != "PASS":
        raise ValueError("M336I E24 final leak scan failed")
    validation_body = {
        "schema_version": 1,
        "contract_role": "EXTERNAL_M336I_E24_VALIDATION",
        "prospective_e24_tree_hash": content_hash(_rows(output)),
        "source_leak_report_hash": post_scan["report_hash"],
        "post_scan_mutation_count": 0,
        "unscanned_intended_file_count": 0,
        "scanned_file_omission_count": 0,
        "status": "PASS",
    }
    write_canonical_json(
        validation_output,
        {**validation_body, "receipt_hash": content_hash(validation_body)},
    )
    print(
        json.dumps(
            {
                "prospective_e24_tree_hash": validation_body[
                    "prospective_e24_tree_hash"
                ],
                "status": "E24_READY_TO_COMMIT",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
