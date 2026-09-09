"""Compare exact-R27 Windows/Karina disclosed rehearsal evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)

NEUTRAL_QUALIFICATION_FILES = (
    "archive_policy_v2.json",
    "archive_mutation_campaign.json",
    "mixed_candidate_fault_campaign.json",
    "f26_candidate_inventory.json",
    "f26_failed_run_recovery.json",
    "f26_duplicate_path_forensics.json",
    "f26_candidate_terminal_matrix.json",
    "f26_global_acquisition_receipt.json",
    "f26_acquisition_ledger_receipt.json",
    "f26_disclosure_recovery.json",
    "f26_disclosure_registry_append_receipt.json",
    "candidate_qualification.json",
    "source_entry_binding_manifest.json",
    "selectability_census.json",
    "selector_feasibility.json",
    "disclosed_rehearsal_summary.json",
)


def _load(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _sealed(value: dict, field: str) -> str:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed is None or content_hash(body) != claimed:
        raise ValueError(f"invalid exact-R27 artifact: {field}")
    return claimed


def _tree_rows(root: Path):
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _metrics(root: Path) -> dict:
    semantic = _load(root / "semantic_evaluation.json")
    _sealed(semantic, "artifact_hash")
    counts = dict(semantic["counts"])
    ratios = dict(semantic["ratios"])
    decisions = dict(semantic["decisions"])
    return {
        "readiness": semantic["readiness_result"],
        "wrong_trusted": counts["wrong_trusted"],
        "trusted_compiler_blocked_targets": counts["trusted_compiler_blocked_targets"],
        "trusted_header_blocking_targets": counts["trusted_header_blocking_targets"],
        "trusted_enclosing_type_blocking_targets": counts[
            "trusted_enclosing_type_blocking_targets"
        ],
        "post_trust_pack_failures": counts["post_trust_pack_failures"],
        "field_missing": counts["field_missing"],
        "field_extra": counts["field_extra"],
        "field_duplicate": counts["field_duplicate"],
        "field_wrong": counts["field_wrong"],
        "false_automatic_spdx_identities": counts["license_false_automatic_identities"],
        "producer_contract_failures": counts["producer_contract_failures"],
        "trust_precision": ratios["trust_precision"],
        "safe_trust_coverage": ratios["safe_trust_coverage"],
        "location_precision": ratios["location_precision"],
        "location_recall": ratios["location_recall"],
        "semantic_precision": ratios["semantic_precision"],
        "semantic_recall": ratios["semantic_recall"],
        "field_evidence_exactness": ratios["field_evidence_exactness"],
        "spdx_agreement": ratios["spdx_agreement"],
        "resolution_agreement": ratios["resolution_agreement"],
        "runtime": decisions["runtime"],
        "producer_contracts": decisions["producer_contracts"],
    }


def _required_metrics(metrics: dict) -> bool:
    return (
        metrics["readiness"] == "PASS"
        and metrics["wrong_trusted"] == 0
        and metrics["trusted_compiler_blocked_targets"] == 0
        and metrics["trusted_header_blocking_targets"] == 0
        and metrics["trusted_enclosing_type_blocking_targets"] == 0
        and metrics["post_trust_pack_failures"] == 0
        and metrics["field_missing"]
        == metrics["field_extra"]
        == metrics["field_duplicate"]
        == metrics["field_wrong"]
        == 0
        and metrics["false_automatic_spdx_identities"] == 0
        and metrics["producer_contract_failures"] == 0
        and metrics["trust_precision"] == "1.000000"
        and metrics["location_precision"] == "1.000000"
        and metrics["semantic_precision"] == "1.000000"
        and metrics["field_evidence_exactness"] == "1.000000"
        and metrics["spdx_agreement"] == "1.000000"
        and metrics["runtime"] == "PASS"
        and metrics["producer_contracts"] == "PASS"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r27-sha", required=True)
    parser.add_argument("--windows-qualification", type=Path, required=True)
    parser.add_argument("--karina-qualification", type=Path, required=True)
    parser.add_argument("--windows-closure", type=Path, required=True)
    parser.add_argument("--karina-closure", type=Path, required=True)
    parser.add_argument("--windows-production", type=Path, required=True)
    parser.add_argument("--karina-production", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K comparison output must be fresh")
    roots = {
        "windows": {
            "qualification": args.windows_qualification.resolve(strict=True),
            "closure": args.windows_closure.resolve(strict=True),
            "production": args.windows_production.resolve(strict=True),
            "evaluation": args.windows_evaluation.resolve(strict=True),
        },
        "karina": {
            "qualification": args.karina_qualification.resolve(strict=True),
            "closure": args.karina_closure.resolve(strict=True),
            "production": args.karina_production.resolve(strict=True),
            "evaluation": args.karina_evaluation.resolve(strict=True),
        },
    }
    qualification_differences = []
    for name in NEUTRAL_QUALIFICATION_FILES:
        windows = (roots["windows"]["qualification"] / name).read_bytes()
        karina = (roots["karina"]["qualification"] / name).read_bytes()
        if windows != karina:
            qualification_differences.append(name)

    selected = {}
    ledgers = {}
    executions = {}
    integrities = {}
    metrics = {}
    runtimes = {}
    pack_rows = {}
    for platform in ("windows", "karina"):
        values = roots[platform]
        selected[platform] = _load(values["closure"] / "selected_source_manifest.json")
        _sealed(selected[platform], "manifest_hash")
        ledgers[platform] = _load(values["closure"] / "selector_ledger_receipt.json")
        executions[platform] = _load(
            values["production"] / "m336f_production_execution.json"
        )
        _sealed(executions[platform], "seal_hash")
        integrities[platform] = verify_java_public_candidate_pack(
            values["production"] / "candidate_pack"
        )
        metrics[platform] = _metrics(values["evaluation"])
        runtimes[platform] = _load(values["evaluation"] / "runtime_proof.json")
        pack_rows[platform] = _tree_rows(values["production"] / "candidate_pack")
        selected_paths = tuple(
            item["selected_path"] for item in selected[platform]["files"]
        )
        selected_roots = {item.partition("/")[0] for item in selected_paths}
        maximum_root = max(
            sum(path.startswith(root + "/") for path in selected_paths)
            for root in selected_roots
        )
        if (
            len(selected_paths) != 180
            or len(selected_roots) < 3
            or maximum_root > 63
            or ledgers[platform]["selector_reservation_count"] != 1
            or ledgers[platform]["selector_invocation_count"] != 1
            or ledgers[platform]["selector_rerun_count"] != 0
            or executions[platform]["r21_sha"] != args.r27_sha
            or executions[platform]["qualification_mode"] != "EXACT_R27_AUTHORITATIVE"
            or executions[platform]["status"] != "PASS"
            or integrities[platform].status != "PASS"
            or runtimes[platform]["status"] != "PASS"
            or not _required_metrics(metrics[platform])
        ):
            raise ValueError(f"{platform} exact-R27 full-route rehearsal failed")

    selected_difference_count = int(
        (roots["windows"]["closure"] / "selected_source_manifest.json").read_bytes()
        != (roots["karina"]["closure"] / "selected_source_manifest.json").read_bytes()
    )
    pack_difference_count = len(set(pack_rows["windows"]) ^ set(pack_rows["karina"]))
    metric_difference_count = len(
        set(metrics["windows"].items()) ^ set(metrics["karina"].items())
    )
    leak = scan_fresh_source_leaks(
        args.vault.resolve(strict=True),
        tuple(
            values[role]
            for values in roots.values()
            for role in ("qualification", "closure", "production", "evaluation")
        ),
    )
    difference_count = (
        len(qualification_differences)
        + selected_difference_count
        + pack_difference_count
        + metric_difference_count
    )
    status = "PASS" if difference_count == 0 and leak["status"] == "PASS" else "FAIL"
    output.mkdir(parents=True)
    cross_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_R27_CROSS_PLATFORM_REPORT",
        "exact_r27_sha": args.r27_sha,
        "qualification_file_count": len(NEUTRAL_QUALIFICATION_FILES),
        "qualification_byte_difference_count": len(qualification_differences),
        "qualification_difference_names": tuple(qualification_differences),
        "selected_manifest_byte_difference_count": selected_difference_count,
        "candidate_pack_byte_difference_count": pack_difference_count,
        "independent_metric_difference_count": metric_difference_count,
        "platform_neutral_difference_count": difference_count,
        "windows_candidate_pack_tree_hash": content_hash(pack_rows["windows"]),
        "karina_candidate_pack_tree_hash": content_hash(pack_rows["karina"]),
        "status": status,
    }
    route_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_DISCLOSED_FULL_ROUTE_REHEARSAL",
        "exact_r27_sha": args.r27_sha,
        "selected_file_count": len(selected["windows"]["files"]),
        "selected_root_count": len(
            {
                item["selected_path"].partition("/")[0]
                for item in selected["windows"]["files"]
            }
        ),
        "selector_invocation_count": ledgers["windows"]["selector_invocation_count"],
        "selector_rerun_count": ledgers["windows"]["selector_rerun_count"],
        "windows_candidate_pack_hash": integrities[
            "windows"
        ].candidate_pack_content_hash,
        "karina_candidate_pack_hash": integrities["karina"].candidate_pack_content_hash,
        "windows_metrics": tuple(sorted(metrics["windows"].items())),
        "karina_metrics": tuple(sorted(metrics["karina"].items())),
        "source_leak_count": leak["fresh_source_leak_count"],
        "platform_neutral_difference_count": difference_count,
        "status": status,
    }
    _write(
        output / "cross_platform_report.json",
        {**cross_body, "report_hash": content_hash(cross_body)},
    )
    _write(
        output / "disclosed_full_route_rehearsal.json",
        {**route_body, "report_hash": content_hash(route_body)},
    )
    _write(output / "source_leak_report.json", leak)
    if status != "PASS":
        raise ValueError("M336K exact-R27 cross-platform comparison failed")


if __name__ == "__main__":
    main()
