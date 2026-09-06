"""Build source-safe R21 publication-boundary forensic artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _sealed_rows(rows):
    result = []
    for row in rows:
        result.append({**row, "row_hash": content_hash(row)})
    return tuple(result)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leak-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.leak_report.resolve(strict=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = {
        "base64_or_hex_source_body_count": 2,
        "local_vault_absolute_path_count": 1,
        "fresh_source_leak_count": 3,
        "status": "FAIL",
    }
    if any(report.get(name) != value for name, value in expected.items()):
        raise ValueError("input is not the exact disclosed R21 leak report")
    source_rows = _sealed_rows(
        (
            {
                "field_family": "raw_source_blobs",
                "defining_module": "src/ai_brain/stage3/acquisition/java_production_replay.py",
                "producer": "build_java_production_replay_artifact",
                "consumer": "verify_compiled_java_production_standalone",
                "artifact_path": "candidate_pack/java_production_closure.json",
                "current_role": "PUBLIC_CANDIDATE_PACK_DEPENDENCY",
                "required_role": "PRIVATE_SOURCE_INPUT",
                "classification": "PRIVATE_SOURCE_INPUT",
                "copy_install_propagation": "compile_provisional_pack -> InstalledDomainRegistry.install",
                "contract_coverage": "LEGACY_FILENAME_ALLOWLIST_ONLY",
                "leak_scan_coverage": "BASE64_COMPLETE_SOURCE",
            },
            {
                "field_family": "canonical_text_blobs",
                "defining_module": "src/ai_brain/stage3/acquisition/java_production_replay.py",
                "producer": "build_java_production_replay_artifact",
                "consumer": "verify_compiled_java_production_standalone",
                "artifact_path": "candidate_pack/java_production_closure.json",
                "current_role": "PUBLIC_CANDIDATE_PACK_DEPENDENCY",
                "required_role": "PRIVATE_SOURCE_INPUT",
                "classification": "PRIVATE_SOURCE_INPUT",
                "copy_install_propagation": "compile_provisional_pack -> InstalledDomainRegistry.install",
                "contract_coverage": "LEGACY_FILENAME_ALLOWLIST_ONLY",
                "leak_scan_coverage": "BASE64_COMPLETE_SOURCE",
            },
            {
                "field_family": "source_paths",
                "defining_module": "src/ai_brain/stage3/acquisition/java_production_replay.py",
                "producer": "build_java_production_replay_artifact",
                "consumer": "_verify_source_closure",
                "artifact_path": "candidate_pack/java_production_closure.json",
                "current_role": "PUBLIC_REPLAY_METADATA_WITH_SOURCE_BODY",
                "required_role": "PRIVATE_SOURCE_INPUT",
                "classification": "PRIVATE_SOURCE_INPUT",
                "copy_install_propagation": "candidate pack and installed candidate-pack copy",
                "contract_coverage": "NO_RECURSIVE_PACK_ENTRY_CONTRACT",
                "leak_scan_coverage": "ABSOLUTE_VAULT_ONLY",
            },
            {
                "field_family": "legacy_evidence_source_blobs",
                "defining_module": "src/ai_brain/stage3/acquisition/java_replay.py",
                "producer": "build_java_replay_artifact",
                "consumer": "verify_compiled_java_evidence_standalone",
                "artifact_path": "candidate_pack/java_evidence_closure.json",
                "current_role": "HISTORICAL_READ_ONLY_COMPATIBILITY",
                "required_role": "PRIVATE_SOURCE_INPUT",
                "classification": "PRIVATE_SOURCE_INPUT",
                "copy_install_propagation": "legacy candidate-pack writer",
                "contract_coverage": "LEGACY_FILENAME_ALLOWLIST_ONLY",
                "leak_scan_coverage": "BASE64_COMPLETE_SOURCE",
            },
        )
    )
    host_rows = _sealed_rows(
        (
            {
                "field_family": "java_path",
                "defining_module": "src/ai_brain/stage3/acquisition/java_jdk_provider.py",
                "producer": "verify_m336_jdk_provider",
                "consumer": "m336f_evaluate_disclosed_java.main",
                "artifact_path": "evaluation/jdk_provider_receipt.json",
                "current_role": "PUBLIC_EVALUATION_RECEIPT",
                "required_role": "PRIVATE_HOST_OBSERVATION",
                "classification": "PRIVATE_HOST_OBSERVATION",
                "copy_install_propagation": "evaluation public root",
                "contract_coverage": "NOT_REGISTERED_AS_PATH_FREE_TELEMETRY",
                "leak_scan_coverage": "ABSOLUTE_PATH",
            },
            {
                "field_family": "javac_path",
                "defining_module": "src/ai_brain/stage3/acquisition/java_jdk_provider.py",
                "producer": "verify_m336_jdk_provider",
                "consumer": "m336f_evaluate_disclosed_java.main",
                "artifact_path": "evaluation/jdk_provider_receipt.json",
                "current_role": "PUBLIC_EVALUATION_RECEIPT",
                "required_role": "PRIVATE_HOST_OBSERVATION",
                "classification": "PRIVATE_HOST_OBSERVATION",
                "copy_install_propagation": "evaluation public root",
                "contract_coverage": "NOT_REGISTERED_AS_PATH_FREE_TELEMETRY",
                "leak_scan_coverage": "ABSOLUTE_PATH",
            },
            {
                "field_family": "release_path",
                "defining_module": "src/ai_brain/stage3/acquisition/java_jdk_provider.py",
                "producer": "verify_m336_jdk_provider",
                "consumer": "m336f_evaluate_disclosed_java.main",
                "artifact_path": "evaluation/jdk_provider_receipt.json",
                "current_role": "PUBLIC_EVALUATION_RECEIPT",
                "required_role": "PRIVATE_HOST_OBSERVATION",
                "classification": "PRIVATE_HOST_OBSERVATION",
                "copy_install_propagation": "evaluation public root",
                "contract_coverage": "NOT_REGISTERED_AS_PATH_FREE_TELEMETRY",
                "leak_scan_coverage": "ABSOLUTE_PATH",
            },
        )
    )
    flow_body = {
        "schema_version": 1,
        "r21_sha": "e82083123f78c7ce952303914773e4b5da848ed5",
        "leak_report_content_hash": bytes_hash(report_path.read_bytes()),
        "leak_report_hash": report["report_hash"],
        "source_bearing_public_artifact_count": 2,
        "host_path_public_artifact_count": 1,
        "fresh_source_leak_count": 3,
        "producer_consumer_rows": (*source_rows, *host_rows),
    }
    _write(
        args.output / "r21_publication_flow_map.json",
        {**flow_body, "report_hash": content_hash(flow_body)},
    )
    private_body = {
        "schema_version": 1,
        "r21_sha": flow_body["r21_sha"],
        "source_bearing_file_count": 2,
        "raw_source_blob_count": 180,
        "canonical_text_blob_count": 180,
        "rows": source_rows,
    }
    _write(
        args.output / "r21_private_payload_inventory.json",
        {**private_body, "report_hash": content_hash(private_body)},
    )
    host_body = {
        "schema_version": 1,
        "r21_sha": flow_body["r21_sha"],
        "host_path_file_count": 1,
        "host_path_field_count": 3,
        "rows": host_rows,
    }
    _write(
        args.output / "r21_host_path_inventory.json",
        {**host_body, "report_hash": content_hash(host_body)},
    )


if __name__ == "__main__":
    main()
