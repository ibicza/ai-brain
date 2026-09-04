"""Assemble the public-safe H19 production tree and disclosure append."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DEFAULT_REGISTRY_ROOT,
    append_disclosed_java_entries,
    load_disclosed_java_material_entry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f19-sha", required=True)
    parser.add_argument("--acquisition-public", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--windows-production", type=Path, required=True)
    parser.add_argument("--karina-production", type=Path, required=True)
    parser.add_argument("--production-comparison", type=Path, required=True)
    parser.add_argument("--windows-vault-verification", type=Path, required=True)
    parser.add_argument("--karina-vault-verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh H19 output already exists")
    if len(args.f19_sha) != 40:
        raise ValueError("H19 assembly requires exact F19")
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
    if head != args.f19_sha or status:
        raise ValueError("H19 assembly must start from a clean exact-F19 worktree")
    acquisition = args.acquisition_public.resolve(strict=True)
    windows = args.windows_production.resolve(strict=True)
    karina = args.karina_production.resolve(strict=True)
    comparison = _load(args.production_comparison)
    if (
        comparison["platform_independent_difference_count"]
        or comparison["status"] != "PASS"
    ):
        raise ValueError("production differs before H19")
    for path in (args.windows_vault_verification, args.karina_vault_verification):
        verification = _load(path)
        if (
            verification["difference_count"]
            or not verification["file_count_equal"]
            or not verification["all_file_hashes_equal"]
            or not verification["tree_hash_equal"]
            or not verification["all_files_write_protected"]
        ):
            raise ValueError("vault copy differs before H19")
    args.output.mkdir(parents=True)
    h19 = args.output / "h19"
    h19.mkdir()
    for name in (
        "acquisition_receipts.json",
        "qualification_decisions.json",
        "selector_receipt.json",
        "selected_source_manifest.json",
        "source_overlap.json",
        "vault_manifest.json",
        "disclosure_registry_append.json",
        "acquisition_performance.json",
    ):
        shutil.copyfile(acquisition / name, h19 / name)
    overlap = _load(h19 / "source_overlap.json")
    if overlap["selected_root_overlap_count"] or overlap["status"] != "PASS":
        raise ValueError("freshness overlap blocks H19")
    selected = _load(h19 / "selected_source_manifest.json")
    qualification = _load(h19 / "qualification_decisions.json")
    physical_body = {
        "schema_version": 1,
        "selected_file_count": selected["file_count"],
        "selected_root_count": selected["root_count"],
        "root_distribution": tuple(
            tuple(item) for item in selected["root_distribution"]
        ),
        "eligible_java_entry_count": qualification[
            "analysis_eligible_java_entry_count"
        ],
        "excluded_java_entry_count": sum(
            max(0, item["candidate_eligible_source_set_count"])
            for item in qualification["decisions"]
            if item["knowledge_acquisition_eligibility_decision"]
            != "ELIGIBLE_FOR_ANALYSIS"
        ),
    }
    _write(
        h19 / "physical_census.json",
        {**physical_body, "report_hash": content_hash(physical_body)},
    )
    production = h19 / "production"
    production.mkdir()
    for name in (
        "production_output.json",
        "component_manifest.json",
        "packability_report.json",
        "trust_closure.json",
        "production_counts.json",
        "candidate_replay.json",
        "production_summary.json",
        "m336d_production_seal.json",
        "production_performance.json",
    ):
        shutil.copyfile(windows / name, production / name)
    shutil.copytree(windows / "candidate_pack", production / "candidate_pack")
    shutil.copyfile(
        windows / "production_performance.json",
        production / "production_performance_windows.json",
    )
    shutil.copyfile(
        karina / "production_performance.json",
        production / "production_performance_karina.json",
    )
    windows_summary = _load(windows / "production_summary.json")
    karina_summary = _load(karina / "production_summary.json")
    windows_seal = _load(windows / "m336d_production_seal.json")
    karina_seal = _load(karina / "m336d_production_seal.json")
    if (
        windows_summary["status"] != "PASS"
        or karina_summary["status"] != "PASS"
        or windows_seal["status"] != "PASS"
        or karina_seal["status"] != "PASS"
        or windows_seal["f19_sha"] != args.f19_sha
        or karina_seal["f19_sha"] != args.f19_sha
        or windows_summary["production_evaluator_dependency_count"]
        or karina_summary["production_evaluator_dependency_count"]
        or windows_summary["production_golden_read_count"]
        or karina_summary["production_golden_read_count"]
    ):
        raise ValueError("production seal is not oracle-free exact-F19 PASS")
    audits = {
        "schema_version": 1,
        "windows_process_audit_hash": bytes_hash(
            (windows / "production_process_audit.json").read_bytes()
        ),
        "karina_process_audit_hash": bytes_hash(
            (karina / "production_process_audit.json").read_bytes()
        ),
        "windows_file_audit_hash": bytes_hash(
            (windows / "production_file_access_audit.json").read_bytes()
        ),
        "karina_file_audit_hash": bytes_hash(
            (karina / "production_file_access_audit.json").read_bytes()
        ),
        "production_evaluator_dependency_count": windows_summary[
            "production_evaluator_dependency_count"
        ],
        "production_golden_read_count": windows_summary["production_golden_read_count"],
        "network_access_count": 0,
    }
    audits["report_hash"] = content_hash(audits)
    _write(h19 / "production_process_audits.json", audits)
    shutil.copyfile(args.production_comparison, h19 / "production_comparison.json")
    shutil.copyfile(
        args.windows_vault_verification, h19 / "vault_verification_windows.json"
    )
    shutil.copyfile(
        args.karina_vault_verification, h19 / "vault_verification_karina.json"
    )
    pack_body = {
        "schema_version": 1,
        "candidate_pack_hash": windows_summary["candidate_pack_hash"],
        "candidate_tree_hash": windows_summary["candidate_tree_hash"],
        "compiled": True,
        "replay_passed": windows_summary["candidate_replay_status"] == "PASS",
    }
    _write(
        h19 / "candidate_pack.json",
        {**pack_body, "report_hash": content_hash(pack_body)},
    )
    for logical_path, physical_path in (
        ("h19/acquisition_receipts.json", h19 / "acquisition_receipts.json"),
        ("h19/qualification_decisions.json", h19 / "qualification_decisions.json"),
        ("h19/selector_receipt.json", h19 / "selector_receipt.json"),
        (
            "h19/production/production_summary.json",
            h19 / "production/production_summary.json",
        ),
        ("h19/candidate_pack.json", h19 / "candidate_pack.json"),
        ("h19/vault_manifest.json", h19 / "vault_manifest.json"),
    ):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            logical_path, physical_path.read_bytes()
        )
    append = _load(h19 / "disclosure_registry_append.json")
    if (
        not append["all_downloaded_candidates_included"]
        or append["downloaded_candidate_count"] != overlap["downloaded_candidate_count"]
    ):
        raise ValueError("downloaded-candidate disclosure denominator mismatch")
    entries = tuple(
        load_disclosed_java_material_entry(
            (canonical_json(item) + "\n").encode("utf-8")
        )
        for item in append["entries"]
    )
    registry_root = repository / DEFAULT_REGISTRY_ROOT
    registry = append_disclosed_java_entries(registry_root, entries)
    verify_disclosed_java_registry(registry_root)
    registry_body = {
        "schema_version": 1,
        "appended_entry_count": len(entries),
        "all_downloaded_candidates_appended": len(entries)
        == append["downloaded_candidate_count"],
        "registry_manifest_hash": registry.manifest_hash,
        "entry_hashes": registry.entry_hashes,
    }
    _write(
        h19 / "disclosed_registry_receipt.json",
        {**registry_body, "receipt_hash": content_hash(registry_body)},
    )
    leak = scan_fresh_source_leaks(
        args.vault.resolve(strict=True), (args.output, registry_root)
    )
    _write(h19 / "source_leak_scan.json", leak)
    if leak["fresh_source_leak_count"]:
        raise ValueError("fresh raw source leaked into H19")
    rows = tuple(
        (path.relative_to(args.output).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in args.output.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(args.output).as_posix().encode(),
        )
    )
    seal_body = {
        "schema_version": 1,
        "f19_sha": args.f19_sha,
        "public_payload_file_count": len(rows),
        "public_tree_hash": content_hash(rows),
        "windows_production_hash": windows_summary["production_output_hash"],
        "karina_production_hash": karina_summary["production_output_hash"],
        "platform_difference_count": comparison[
            "platform_independent_difference_count"
        ],
        "production_completed_before_evaluator": True,
        "fresh_source_leak_count": 0,
    }
    _write(
        h19 / "h19_seal.json",
        {**seal_body, "seal_hash": content_hash(seal_body)},
    )
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
        "h19/h19_seal.json", (h19 / "h19_seal.json").read_bytes()
    )


if __name__ == "__main__":
    main()
