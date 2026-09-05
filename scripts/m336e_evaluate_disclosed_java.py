"""Run one platform's disclosed evaluator after both production seals exist."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from m336d_evaluate_final import _evaluate_licenses

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    canonical_public_json,
    produce_m336e_qualification_summary,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
    selected_source_manifest_from_dict,
    selector_feasibility_proof_from_dict,
    selector_receipt_from_dict,
    verify_selector_result_without_invocation,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--feasibility-proof", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--windows-production-root", type=Path, required=True)
    parser.add_argument("--karina-production-root", type=Path, required=True)
    parser.add_argument("--qualification-report", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--f20-sha", required=True)
    parser.add_argument("--h20-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != args.h20_sha or len(head) != 40 or status:
        raise ValueError("independent evaluation requires a clean exact-H20 worktree")
    if args.output.exists():
        raise FileExistsError("fresh disclosed evaluator output already exists")
    ledger = RunProtocolLedger(
        args.ledger.resolve(strict=True), git_worktrees=(repository,)
    )
    protocol = ledger.receipt()
    if (
        protocol.final_event_type != "EVALUATION_RESERVED"
        or protocol.production_seal_count != 2
        or protocol.evaluator_start_count != 1
    ):
        raise ValueError("evaluator requires two seals and one reserved evaluation")
    windows = _load(
        args.windows_production_root.resolve(strict=True) / "production_summary.json"
    )
    karina = _load(
        args.karina_production_root.resolve(strict=True) / "production_summary.json"
    )
    neutral_fields = (
        "production_output_hash",
        "production_batch_hash",
        "component_manifest_hash",
        "candidate_pack_hash",
        "candidate_tree_hash",
        "candidate_replay_hash",
        "candidate_replay_status",
        "production_evaluator_dependency_count",
        "production_golden_read_count",
        "torch_imported",
        "status",
    )
    if any(windows[field] != karina[field] for field in neutral_fields):
        raise ValueError("platform-neutral production seals differ before evaluation")
    if (
        windows["status"] != "PASS"
        or windows["candidate_replay_status"] != "PASS"
        or windows["production_evaluator_dependency_count"] != 0
        or windows["production_golden_read_count"] != 0
    ):
        raise ValueError("production seals are not evaluator-ready")
    production_root = args.production_root.resolve(strict=True)
    expected_root = (
        args.windows_production_root
        if args.platform == "windows"
        else args.karina_production_root
    ).resolve(strict=True)
    if production_root != expected_root:
        raise ValueError("evaluator platform does not match its production root")

    qualification = _load(args.qualification_report.resolve(strict=True))
    bindings = source_entry_binding_manifest_from_dict(
        _load(args.bindings.resolve(strict=True))
    )
    census = selectable_source_census_from_dict(_load(args.census.resolve(strict=True)))
    proof = selector_feasibility_proof_from_dict(
        _load(args.feasibility_proof.resolve(strict=True)), census
    )
    selected = selected_source_manifest_from_dict(
        _load(args.selected_manifest.resolve(strict=True))
    )
    selector = selector_receipt_from_dict(
        _load(args.selector_receipt.resolve(strict=True))
    )
    if selector.f20_sha != args.f20_sha:
        raise ValueError("independent evaluation selector is not bound to exact F20")
    verify_selector_result_without_invocation(
        census, proof, bindings, selected, selector
    )
    source_root = args.source_root.resolve(strict=True)
    binding_by_id = {
        item.source_entry_id.identity_hash: item for item in bindings.bindings
    }
    for row in selected.files:
        binding = binding_by_id[row.source_entry_identity_hash]
        raw = source_root.joinpath(*row.selected_path.split("/")).read_bytes()
        if bytes_hash(raw) != binding.source_entry_id.raw_source_sha256:
            raise ValueError(
                "independent evaluator source snapshot differs from selection"
            )
    selected_families = {item.candidate_root for item in selected.files}
    qualification_summary = produce_m336e_qualification_summary(
        "SUCCESS",
        f20_sha=args.f20_sha,
        qualification=qualification,
        census=asdict(census),
        overlap={"selected_root_overlap_count": 0},
    )
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
        "h20/qualification_summary.json",
        canonical_public_json(qualification_summary),
    )
    decisions = tuple(qualification_summary["candidate_decisions"])
    if selected_families - {item["family_id"] for item in decisions}:
        raise ValueError("selected roots are absent from qualification decisions")
    authority = tuple(
        {
            "family_id": item["family_id"],
            "authority": {
                "source_authenticity": item["source_authenticity_decision"],
                "license_fusion_status": item["scoped_license_decision"],
            },
        }
        for item in decisions
    )
    args.output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="m336e-disclosed-evaluator-") as temporary:
        temporary_root = Path(temporary)
        authority_path = temporary_root / "authority.json"
        _write(authority_path, authority)
        semantic_output = args.output / "semantic"
        subprocess.run(
            (
                sys.executable,
                str(repository / "scripts/m336c_evaluate_disclosed_java.py"),
                "--source-root",
                str(source_root),
                "--production-root",
                str(production_root),
                "--authority-report",
                str(authority_path),
                "--java",
                str(args.java.resolve(strict=True)),
                "--javac",
                str(args.javac.resolve(strict=True)),
                "--platform",
                args.platform,
                "--i18-sha",
                args.h20_sha,
                "--output",
                str(semantic_output),
            ),
            cwd=repository,
            check=True,
        )
        license_report = _evaluate_licenses(
            vault=args.vault.resolve(strict=True),
            selected_families=selected_families,
            java=args.java.resolve(strict=True),
            javac=args.javac.resolve(strict=True),
            temporary=temporary_root,
        )
    _write(args.output / "independent_license_evaluation.json", license_report)
    semantic = _load(args.output / "semantic/evaluation_summary.json")
    runtime = _load(args.output / "semantic/runtime_proof.json")
    body = {
        "schema_version": 2,
        "platform": args.platform,
        "f20_sha": args.f20_sha,
        "h20_sha": args.h20_sha,
        "protocol_ledger_receipt_hash": protocol.receipt_hash,
        "both_production_seals_present_before_evaluator": True,
        "production_reference_license_agreement": license_report[
            "production_reference_agreement"
        ],
        "false_automatic_license_identity_count": license_report[
            "false_automatic_license_identity_count"
        ],
        "selected_root_unresolved_disagreement_count": license_report[
            "selected_root_unresolved_disagreement_count"
        ],
        "location_precision": semantic["location_precision"],
        "location_recall": semantic["location_recall"],
        "semantic_precision": semantic["semantic_precision"],
        "semantic_recall": semantic["semantic_recall"],
        "trust_precision": semantic["trust_precision"],
        "trust_coverage": semantic["trust_coverage"],
        "field_evidence_exactness": semantic["field_evidence_exactness"],
        "resolution_agreement": semantic["resolution_agreement"],
        "wrong_trusted_count": semantic["wrong_trusted_count"],
        "post_trust_pack_failures": semantic["post_trust_pack_failures"],
        "candidate_pack_compiled": semantic["candidate_pack_compiled"],
        "candidate_replay_status": semantic["candidate_replay_status"],
        "runtime_status": runtime["status"],
        "runtime_network_access_count": 0,
        "status": "PASS"
        if semantic["status"] == "PASS"
        and license_report["status"] == "PASS"
        and runtime["status"] == "PASS"
        else "FAIL",
    }
    _write(
        args.output / "evaluation.json",
        {**body, "report_hash": content_hash(body)},
    )
    if body["status"] != "PASS":
        raise SystemExit("M-33.6e disclosed independent evaluation failed")


if __name__ == "__main__":
    main()
