"""Run one exact-R22 disclosed source-free production and sealed replay."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
    m336f_selector_receipt_from_dict,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.m336f_thresholds import (
    M336F_JAVA_ACCEPTANCE_THRESHOLDS,
)


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _require_clean_exact(repository: Path, expected: str) -> None:
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
    if head != expected or len(head) != 40 or status:
        raise ValueError("disclosed production requires a clean exact-R22 worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r22-sha", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--closure-proof", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if not args.development:
        _require_clean_exact(repository, args.r22_sha)
    if args.output.exists() or args.private_root.exists():
        raise FileExistsError("fresh disclosed production output already exists")
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _load(args.closure_proof)
    )
    selected = m336f_selected_source_manifest_from_dict(_load(args.selected_manifest))
    selector = m336f_selector_receipt_from_dict(_load(args.selector_receipt))
    verify_m336f_selection(selected, selector, proof)
    subprocess.run(
        (
            sys.executable,
            str(repository / "scripts/m336_run_oracle_free_production.py"),
            "--source-root",
            str(args.source_root.resolve(strict=True)),
            "--output",
            str(args.output),
            "--platform",
            args.platform,
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--source-entry-bindings",
            str(args.bindings.resolve(strict=True)),
            "--selected-manifest",
            str(args.selected_manifest.resolve(strict=True)),
            "--sealed-vault",
            str(args.vault.resolve(strict=True)),
            "--private-replay-root",
            str(args.private_root),
        ),
        cwd=repository,
        check=True,
    )
    private_manifest = args.private_root / "sealed_java_replay_input_manifest.json"
    replay_receipt = args.output / "sealed_source_replay_receipt.json"
    subprocess.run(
        (
            sys.executable,
            str(repository / "scripts/m336g_run_sealed_replay.py"),
            "--candidate-pack",
            str(args.output / "candidate_pack"),
            "--private-manifest",
            str(private_manifest),
            "--sealed-vault",
            str(args.vault.resolve(strict=True)),
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--output",
            str(replay_receipt),
        ),
        cwd=repository,
        check=True,
    )
    private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform=args.platform,
        java=args.java,
        javac=args.javac,
    )
    _write(args.output / "public_jdk_identity_receipt.json", asdict(public_jdk))
    _write(
        args.private_root / "private_jdk_observation.json",
        {
            "contract_role": private_jdk.contract_role,
            "platform": private_jdk.platform,
            "java_executable": str(private_jdk.java_executable),
            "javac_executable": str(private_jdk.javac_executable),
            "release_file": str(private_jdk.release_file),
            "provider_installation_root": str(private_jdk.provider_installation_root),
            "observed_version_banner": private_jdk.observed_version_banner,
        },
    )
    summary = _load(args.output / "production_summary.json")
    counts = _load(args.output / "production_counts.json")
    replay = _load(replay_receipt)
    integrity = _load(args.output / "public_pack_integrity_receipt.json")
    file_access = _load(args.output / "production_file_access_audit.json")
    if (
        summary["status"] != "PASS"
        or summary["public_pack_integrity_status"] != "PASS"
        or integrity["status"] != "PASS"
        or replay["status"] != "PASS"
        or replay["reconstructed_pack_byte_difference_count"] != 0
        or replay["proposal_count"] != 1587
        or replay["trusted_count"] != 1575
        or replay["withheld_count"] != 12
        or counts["post_trust_pack_failures"]
        != M336F_JAVA_ACCEPTANCE_THRESHOLDS.post_trust_pack_failures
        or counts["trusted_compiler_blocked_target_count"] != 0
        or integrity["absolute_path_count"] != 0
        or integrity["reversible_source_payload_count"] != 0
        or integrity["private_role_entry_count"] != 0
        or integrity["unknown_entry_count"] != 0
        or file_access["status"] != "PASS"
        or file_access["host_path_field_count"] != 0
    ):
        raise ValueError("M-33.6g disclosed production/replay gate failed")
    body = {
        "schema_version": 1,
        "r22_sha": args.r22_sha,
        "qualification_mode": (
            "DEVELOPMENT_NON_AUTHORITATIVE"
            if args.development
            else "EXACT_R22_AUTHORITATIVE"
        ),
        "platform": args.platform,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "compiler_identity_hash": summary["compiler_identity_hash"],
        "compiler_report_hash": summary["compiler_report_hash"],
        "public_candidate_pack_hash": summary["candidate_pack_hash"],
        "public_candidate_pack_tree_hash": integrity["candidate_pack_tree_hash"],
        "public_replay_commitment_hash": summary["public_replay_commitment_hash"],
        "public_pack_integrity_receipt_hash": integrity["receipt_hash"],
        "sealed_source_replay_receipt_hash": replay["receipt_hash"],
        "public_jdk_identity_receipt_hash": public_jdk.receipt_hash,
        "private_manifest_commitment_hash": replay["private_manifest_commitment_hash"],
        "candidate_pack_source_bearing_entry_count": 0,
        "candidate_pack_private_role_entry_count": 0,
        "candidate_pack_unknown_entry_count": 0,
        "reconstructed_pack_byte_difference_count": 0,
        "production_evaluator_read_count": 0,
        "production_golden_read_count": 0,
        "production_network_access_count": 0,
        "production_host_path_field_count": file_access["host_path_field_count"],
        "sealed_replay_evaluator_read_count": replay["evaluator_read_count"],
        "sealed_replay_golden_read_count": replay["golden_read_count"],
        "sealed_replay_network_access_count": replay["network_access_count"],
        "status": "PASS",
    }
    _write(
        args.output / "m336g_production_execution.json",
        {**body, "seal_hash": content_hash(body)},
    )


if __name__ == "__main__":
    main()
