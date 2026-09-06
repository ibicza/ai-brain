"""Assemble the exact-R22 disclosed M-33.6g qualification evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336g_publication import (
    ArtifactConfidentialityRole,
    audit_publication_boundary,
    public_artifact_inventory_identity,
    selected_source_entry_identities,
    verify_java_public_candidate_pack,
)


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _sealed(value: dict, field: str) -> str:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed is None or content_hash(body) != claimed:
        raise ValueError(f"invalid disclosed artifact {field}")
    return claimed


def _file_rows(root: Path):
    root = root.resolve(strict=True)
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


def _installed_pack(evaluation_root: Path) -> Path:
    installation = _load(evaluation_root / "installation.json")
    return evaluation_root / "installed_pack" / installation["pack_root"]


def _pairs(value: dict, name: str) -> dict:
    return dict(value[name])


def _semantic_metrics(evaluation_root: Path) -> dict:
    semantic = _load(evaluation_root / "semantic_evaluation.json")
    _sealed(semantic, "artifact_hash")
    counts = _pairs(semantic, "counts")
    ratios = _pairs(semantic, "ratios")
    decisions = _pairs(semantic, "decisions")
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
        "artifact_hash": semantic["artifact_hash"],
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
        and metrics["safe_trust_coverage"] == "0.957447"
        and metrics["location_precision"] == "1.000000"
        and metrics["location_recall"] == "0.964156"
        and metrics["semantic_precision"] == "1.000000"
        and metrics["semantic_recall"] == "0.964156"
        and metrics["field_evidence_exactness"] == "1.000000"
        and metrics["spdx_agreement"] == "1.000000"
        and metrics["resolution_agreement"] == "1.000000"
        and metrics["runtime"] == "PASS"
        and metrics["producer_contracts"] == "PASS"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r22-sha", required=True)
    parser.add_argument("--windows-production", type=Path, required=True)
    parser.add_argument("--karina-production", type=Path, required=True)
    parser.add_argument("--windows-evaluation", type=Path, required=True)
    parser.add_argument("--karina-evaluation", type=Path, required=True)
    parser.add_argument("--closure-root", type=Path, required=True)
    parser.add_argument("--r21-production", type=Path, required=True)
    parser.add_argument("--r21-selected-manifest", type=Path, required=True)
    parser.add_argument("--r21-evaluation", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh disclosed qualification output already exists")
    roots = {
        "windows": (
            args.windows_production.resolve(strict=True),
            args.windows_evaluation.resolve(strict=True),
        ),
        "karina": (
            args.karina_production.resolve(strict=True),
            args.karina_evaluation.resolve(strict=True),
        ),
    }
    closure = args.closure_root.resolve(strict=True)
    ledger = _load(closure / "selector_ledger_receipt.json")
    selected = _load(closure / "selected_source_manifest.json")
    selected_paths = [item["selected_path"] for item in selected["files"]]
    selected_roots = {item.partition("/")[0] for item in selected_paths}
    max_root = max(
        sum(path.startswith(root + "/") for path in selected_paths)
        for root in selected_roots
    )
    _sealed(selected, "manifest_hash")
    selected_source_entry_identity_set = selected_source_entry_identities(selected)
    r21_selected = _load(args.r21_selected_manifest)
    _sealed(r21_selected, "manifest_hash")
    r21_selected_source_entry_identity_set = selected_source_entry_identities(
        r21_selected
    )
    selected_source_entry_difference_count = len(
        selected_source_entry_identity_set ^ r21_selected_source_entry_identity_set
    )
    if (
        ledger["selector_reservation_count"] != 1
        or ledger["selector_invocation_count"] != 1
        or ledger["selector_rerun_count"] != 0
        or len(selected_paths) != 180
        or len(selected_roots) != 5
        or max_root != 63
        or selected_source_entry_difference_count
    ):
        raise ValueError("exact-R22 selector ledger/selection regression")
    r21_execution = _load(args.r21_production / "m336f_production_execution.json")
    _sealed(r21_execution, "seal_hash")

    executions = {}
    integrities = {}
    replays = {}
    metrics = {}
    runtimes = {}
    contracts = {}
    public_jdk_identities = {}
    candidate_rows = {}
    installed_rows = {}
    for platform, (production, evaluation) in roots.items():
        executions[platform] = _load(production / "m336g_production_execution.json")
        _sealed(executions[platform], "seal_hash")
        integrities[platform] = verify_java_public_candidate_pack(
            production / "candidate_pack"
        )
        replays[platform] = _load(production / "sealed_source_replay_receipt.json")
        _sealed(replays[platform], "receipt_hash")
        metrics[platform] = _semantic_metrics(evaluation)
        runtimes[platform] = _load(evaluation / "runtime_proof.json")
        contracts[platform] = _load(evaluation / "producer_contract_compatibility.json")
        _sealed(contracts[platform], "report_hash")
        public_jdk_identities[platform] = _load(
            production / "public_jdk_identity_receipt.json"
        )
        _sealed(public_jdk_identities[platform], "receipt_hash")
        candidate_rows[platform] = _file_rows(production / "candidate_pack")
        installed_rows[platform] = _file_rows(_installed_pack(evaluation))
        if (
            executions[platform]["r22_sha"] != args.r22_sha
            or executions[platform]["platform"] != platform
            or executions[platform]["qualification_mode"] != "EXACT_R22_AUTHORITATIVE"
            or executions[platform]["status"] != "PASS"
            or replays[platform]["status"] != "PASS"
            or replays[platform]["reconstructed_pack_byte_difference_count"] != 0
            or integrities[platform].status != "PASS"
            or runtimes[platform]["status"] != "PASS"
            or contracts[platform]["status"] != "PASS"
            or public_jdk_identities[platform]["platform_role"] != platform
            or public_jdk_identities[platform]["verification_status"] != "PASS"
            or not _required_metrics(metrics[platform])
            or candidate_rows[platform] != installed_rows[platform]
        ):
            raise ValueError(f"{platform} disclosed publication qualification failed")

    public_pack_differences = len(
        set(candidate_rows["windows"]) ^ set(candidate_rows["karina"])
    )
    installed_pack_differences = len(
        set(installed_rows["windows"]) ^ set(installed_rows["karina"])
    )
    neutral_metric_differences = len(
        set(metrics["windows"].items()) ^ set(metrics["karina"].items())
    )
    production_regression_differences = sum(
        execution["production_output_hash"] != r21_execution["production_output_hash"]
        for execution in executions.values()
    )
    r21_metrics = _semantic_metrics(args.r21_evaluation.resolve(strict=True))
    regression_differences = len(
        {
            key
            for key, value in r21_metrics.items()
            if key != "artifact_hash" and metrics["windows"].get(key) != value
        }
    )
    leak = scan_fresh_source_leaks(
        args.vault.resolve(strict=True),
        tuple(root for values in roots.values() for root in values),
    )
    classified = tuple(
        (
            public_artifact_inventory_identity(
                platform_role=platform,
                root_role=root_role,
                relative_path=path.relative_to(root).as_posix(),
                sha256=bytes_hash(path.read_bytes()),
            ),
            (
                ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
                if "candidate_pack" in path.parts or "installed_pack" in path.parts
                else ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT
            ),
            True,
        )
        for platform, values in roots.items()
        for root_role, root in zip(("production", "evaluation"), values, strict=True)
        for path in root.rglob("*")
        if path.is_file()
    )
    boundary_audit, boundary_receipt = audit_publication_boundary(classified)
    status = (
        "PASS"
        if not (
            public_pack_differences
            + installed_pack_differences
            + neutral_metric_differences
            + regression_differences
            + production_regression_differences
            + leak["fresh_source_leak_count"]
        )
        and boundary_receipt.status == "PASS"
        else "FAIL"
    )
    if status != "PASS":
        raise ValueError("cross-platform disclosed qualification failed")
    args.output.mkdir(parents=True)
    cross_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_RECEIPT",
        "windows_candidate_pack_tree_hash": content_hash(candidate_rows["windows"]),
        "karina_candidate_pack_tree_hash": content_hash(candidate_rows["karina"]),
        "public_candidate_pack_byte_difference_count": public_pack_differences,
        "installed_pack_byte_difference_count": installed_pack_differences,
        "platform_neutral_semantic_difference_count": neutral_metric_differences,
        "r21_semantic_regression_difference_count": regression_differences,
        "r21_production_output_regression_difference_count": (
            production_regression_differences
        ),
        "r21_selected_source_entry_difference_count": (
            selected_source_entry_difference_count
        ),
        "status": "PASS",
    }
    qualification_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_RECEIPT",
        "r22_sha": args.r22_sha,
        "selector_reservation_count": 1,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "selected_file_count": len(selected_paths),
        "selected_root_count": len(selected_roots),
        "maximum_root_contribution": max_root,
        "r21_selected_source_entry_difference_count": (
            selected_source_entry_difference_count
        ),
        "proposal_count": 1587,
        "trusted_count": 1575,
        "withheld_count": 12,
        "compiler_blocked_declaration_count": 12,
        "windows_metrics": tuple(sorted(metrics["windows"].items())),
        "karina_metrics": tuple(sorted(metrics["karina"].items())),
        "source_leak_report_hash": leak["report_hash"],
        "publication_boundary_receipt_hash": boundary_receipt.receipt_hash,
        "cross_platform_report_hash": content_hash(cross_body),
        "status": status,
    }
    _write(
        args.output / "cross_platform_report.json",
        {**cross_body, "report_hash": content_hash(cross_body)},
    )
    _write(args.output / "source_leak_report.json", leak)
    _write(args.output / "publication_boundary_audit.json", vars(boundary_audit))
    _write(args.output / "publication_boundary_receipt.json", vars(boundary_receipt))
    _write(
        args.output / "disclosed_qualification.json",
        {**qualification_body, "report_hash": content_hash(qualification_body)},
    )
    for platform in ("windows", "karina"):
        _write(
            args.output / f"{platform}_production_execution.json", executions[platform]
        )
        _write(
            args.output / f"{platform}_semantic_evaluation.json",
            _load(roots[platform][1] / "semantic_evaluation.json"),
        )
        _write(args.output / f"{platform}_runtime_proof.json", runtimes[platform])
        _write(
            args.output / f"{platform}_recursive_pack_contract.json",
            contracts[platform],
        )
        _write(
            args.output / f"{platform}_public_pack_integrity.json",
            vars(integrities[platform]),
        )
        _write(
            args.output / f"{platform}_public_jdk_identity.json",
            public_jdk_identities[platform],
        )
        _write(args.output / f"{platform}_sealed_source_replay.json", replays[platform])


if __name__ == "__main__":
    main()
