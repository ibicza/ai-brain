"""Assemble and contract-validate the exact public-safe H20 tree shape."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    produce_m336e_acquisition_receipts,
    produce_m336e_candidate_pack_receipt,
    produce_m336e_h20_seal,
    produce_m336e_portable_vault_summary,
    produce_m336e_production_summary,
    produce_m336e_protocol_ledger_receipt,
    produce_m336e_qualification_summary,
    produce_m336e_registry_append_receipt,
    produce_m336e_selectability_summary,
    produce_m336e_selector_receipt,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> bytes:
    raw = (canonical_json(value) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-f20", required=True)
    parser.add_argument("--f20-sha", required=True)
    parser.add_argument("--acquisition-receipts", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--source-overlap", type=Path, required=True)
    parser.add_argument("--vault-manifest", type=Path, required=True)
    parser.add_argument("--vault-comparison", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--feasibility-proof", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--registry-append-receipt", type=Path, required=True)
    parser.add_argument("--protocol-ledger-receipt", type=Path, required=True)
    parser.add_argument("--windows-production-root", type=Path, required=True)
    parser.add_argument("--karina-production-root", type=Path, required=True)
    parser.add_argument("--production-comparison", type=Path, required=True)
    parser.add_argument("--contract-gate", type=Path, required=True)
    parser.add_argument("--leak-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
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
    if head != args.expected_f20 or args.f20_sha != head or len(head) != 40 or status:
        raise ValueError("H20 assembly requires a clean exact-F20 worktree")
    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("fresh H20 assembly outputs must not exist")

    acquisition = _load(args.acquisition_receipts.resolve(strict=True))
    qualification = _load(args.qualification.resolve(strict=True))
    overlap = _load(args.source_overlap.resolve(strict=True))
    vault_manifest = _load(args.vault_manifest.resolve(strict=True))
    vault_comparison = _load(args.vault_comparison.resolve(strict=True))
    census = _load(args.census.resolve(strict=True))
    proof = _load(args.feasibility_proof.resolve(strict=True))
    selector = _load(args.selector_receipt.resolve(strict=True))
    registry_append = _load(args.registry_append_receipt.resolve(strict=True))
    protocol = _load(args.protocol_ledger_receipt.resolve(strict=True))
    windows_root = args.windows_production_root.resolve(strict=True)
    karina_root = args.karina_production_root.resolve(strict=True)
    windows = _load(windows_root / "production_summary.json")
    karina = _load(karina_root / "production_summary.json")
    production_comparison = _load(args.production_comparison.resolve(strict=True))
    counts = _load(windows_root / "production_counts.json")
    process = _load(windows_root / "production_process_audit.json")
    contract_gate = _load(args.contract_gate.resolve(strict=True))
    leak = _load(args.leak_report.resolve(strict=True))
    source_leak_count = leak.get(
        "fresh_source_leak_count", leak.get("source_leak_count")
    )
    if source_leak_count is None:
        raise ValueError("leak report lacks a source-leak denominator")
    if (
        contract_gate["status"] != "PASS"
        or contract_gate["uncontracted_produced_artifact_count"] != 0
        or source_leak_count != 0
        or overlap["status"] != "PASS"
        or overlap["selected_root_overlap_count"] != 0
        or vault_comparison["status"] != "PASS"
        or vault_comparison["physical_difference_count"] != 0
        or vault_comparison["canonical_manifest_difference_count"] != 0
        or vault_comparison["portable_tree_hash_difference_count"] != 0
        or not proof["hard_requirements_satisfied"]
        or selector["selector_invocation_count"] != 1
        or selector["selector_rerun_count"] != 0
        or selector["selected_file_count"] != 180
        or selector["maximum_one_root_count"] > 63
        or protocol["global_acquisition_count"] != 1
        or protocol["selectability_census_count"] != 1
        or protocol["selector_invocation_count"] != 1
        or protocol["selector_rerun_count"] != 0
        or protocol["production_seal_count"] != 2
        or production_comparison["status"] != "PASS"
        or production_comparison["platform_independent_difference_count"] != 0
        or windows["status"] != "PASS"
        or karina["status"] != "PASS"
    ):
        raise ValueError("H20 public tree is not producer/leak ready")

    values = {
        "h20/acquisition_receipts.json": produce_m336e_acquisition_receipts(
            acquisition, f20_sha=args.f20_sha, variant="SUCCESS"
        ),
        "h20/qualification_summary.json": produce_m336e_qualification_summary(
            "SUCCESS",
            f20_sha=args.f20_sha,
            qualification=qualification,
            census=census,
            overlap=overlap,
        ),
        "h20/portable_vault_summary.json": produce_m336e_portable_vault_summary(
            "SUCCESS", manifest=vault_manifest, comparison=vault_comparison
        ),
        "h20/selectability_summary.json": produce_m336e_selectability_summary(
            "SUCCESS", census=census, proof=proof
        ),
        "h20/selector_receipt.json": produce_m336e_selector_receipt(
            "SUCCESS", selector=selector
        ),
        "h20/disclosure_registry_append_receipt.json": produce_m336e_registry_append_receipt(
            "SUCCESS", append_receipt=registry_append
        ),
        "h20/protocol_ledger_receipt.json": produce_m336e_protocol_ledger_receipt(
            "SUCCESS", ledger_receipt=protocol
        ),
        "h20/production_summary.json": produce_m336e_production_summary(
            "SUCCESS",
            windows=windows,
            karina=karina,
            comparison=production_comparison,
            production_counts=counts,
            process_audit=process,
        ),
        "h20/candidate_pack_receipt.json": produce_m336e_candidate_pack_receipt(
            "SUCCESS", production_summary=windows
        ),
    }
    args.output.mkdir(parents=True)
    validations = []
    for logical_path, value in values.items():
        raw = _write(args.output / Path(logical_path).name, value)
        validation = M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            logical_path, raw
        )
        validations.append((logical_path, validation.validation_hash))
    tree_rows = tuple(
        sorted(
            (
                logical_path,
                bytes_hash((args.output / Path(logical_path).name).read_bytes()),
            )
            for logical_path in values
        )
    )
    seal = produce_m336e_h20_seal(
        "SUCCESS",
        f20_sha=args.f20_sha,
        public_payload_file_count=len(values),
        public_tree_hash=content_hash(tree_rows),
        producer_contract_failure_count=0,
        source_leak_count=source_leak_count,
    )
    raw = _write(args.output / "h20_seal.json", seal)
    validation = M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
        "h20/h20_seal.json", raw
    )
    validations.append(("h20/h20_seal.json", validation.validation_hash))
    body = {
        "schema_version": 1,
        "artifact_count": len(values) + 1,
        "contract_validation_count": len(validations),
        "contract_failure_count": 0,
        "validations": tuple(validations),
        "public_tree_hash_excluding_self_seal": content_hash(tree_rows),
        "h20_seal_hash": seal["seal_hash"],
        "status": "PASS",
    }
    _write(args.receipt, {**body, "receipt_hash": content_hash(body)})


if __name__ == "__main__":
    main()
