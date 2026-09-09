"""Run one exact disclosed compiler-aware production seal."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    frozen_m336_jdk_provider_manifest,
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    java_production_compilation_probe_from_dict,
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
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _field_evidence_is_exact(manifest: dict) -> bool:
    required = manifest.get("required_field_count")
    return (
        isinstance(required, int)
        and required >= 0
        and manifest.get("evidence_count") == required
        and manifest.get("exact_count") == required
        and manifest.get("missing_count") == 0
        and manifest.get("extra_count") == 0
        and manifest.get("duplicate_count") == 0
        and manifest.get("wrong_count") == 0
        and manifest.get("completeness_ratio")
        == ("N/A" if required == 0 else "1.000000")
        and manifest.get("exactness_ratio") == ("N/A" if required == 0 else "1.000000")
    )


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
        raise ValueError("production requires a clean exact worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r21-sha", required=True)
    parser.add_argument("--exact-phase", choices=("R21", "R27"), default="R21")
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
    parser.add_argument(
        "--development",
        action="store_true",
        help="allow a dirty worktree and mark output non-authoritative",
    )
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if not args.development:
        _require_clean_exact(repository, args.r21_sha)
    if args.output.exists() or args.private_root.exists():
        raise FileExistsError("fresh production output already exists")
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
    field_evidence = _load(args.output / "field_evidence_manifest.json")
    replay = _load(replay_receipt)
    integrity = verify_java_public_candidate_pack(args.output / "candidate_pack")
    persisted_integrity = _load(args.output / "public_pack_integrity_receipt.json")
    process = _load(args.output / "production_process_audit.json")
    files = _load(args.output / "production_file_access_audit.json")
    state = _load(args.output / "production_state_audit.json")
    compiler = _load(args.output / "compiler_report.json")
    compiler_probe = java_production_compilation_probe_from_dict(
        _load(args.output / "compiler_probe.json")
    )
    expected_javac = next(
        item.javac_sha256
        for item in frozen_m336_jdk_provider_manifest().platforms
        if item.platform == args.platform
    )
    if (
        summary["status"] != "PASS"
        or not _field_evidence_is_exact(field_evidence)
        or summary["public_pack_integrity_status"] != "PASS"
        or integrity.status != "PASS"
        or persisted_integrity != asdict(integrity)
        or replay["status"] != "PASS"
        or replay["reconstructed_pack_byte_difference_count"] != 0
        or replay["proposal_count"] != counts["proposal_count"]
        or replay["trusted_count"] != counts["trusted_count"]
        or replay["withheld_count"] != counts["withheld_count"]
        or summary["production_evaluator_dependency_count"] != 0
        or summary["production_golden_read_count"] != 0
        or counts["post_trust_pack_failures"]
        != M336F_JAVA_ACCEPTANCE_THRESHOLDS.post_trust_pack_failures
        or counts["trusted_compiler_blocked_target_count"] != 0
        or counts["trusted_header_blocking_target_count"] != 0
        or counts["trusted_enclosing_type_blocking_target_count"] != 0
        or compiler["source_unit_unbound_count"] != 0
        or compiler["malformed_output_count"] != 0
        or compiler_probe.javac_sha256 != expected_javac
        or compiler_probe.compiler_identity_hash != compiler["compiler_identity_hash"]
        or process["subprocess_invocation_count"] != 1
        or process["unexpected_subprocess_count"] != 0
        or process["socket_attempts"] != 0
        or process["os_system_attempts"] != 0
        or files["forbidden_read_count"] != 0
        or files.get("host_path_field_count", 0) != 0
        or integrity.absolute_path_count != 0
        or integrity.reversible_source_payload_count != 0
        or integrity.private_role_entry_count != 0
        or integrity.unknown_entry_count != 0
        or any(
            replay[name] != 0
            for name in (
                "evaluator_read_count",
                "golden_read_count",
                "network_access_count",
            )
        )
        or any(
            value
            for name, value in state.items()
            if name.endswith(("count", "attempts")) and isinstance(value, int)
        )
    ):
        raise ValueError("compiler-aware production isolation gate failed")
    body = {
        "schema_version": 1,
        "r21_sha": args.r21_sha,
        "qualification_mode": (
            "DEVELOPMENT_NON_AUTHORITATIVE"
            if args.development
            else f"EXACT_{args.exact_phase}_AUTHORITATIVE"
        ),
        "platform": args.platform,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "compiler_identity_hash": summary["compiler_identity_hash"],
        "compiler_probe_hash": compiler_probe.probe_hash,
        "compiler_javac_sha256": compiler_probe.javac_sha256,
        "compiler_report_hash": summary["compiler_report_hash"],
        "field_evidence_manifest_hash": field_evidence["manifest_hash"],
        "field_evidence_required_count": field_evidence["required_field_count"],
        "field_evidence_exact_count": field_evidence["exact_count"],
        "field_evidence_wrong_count": field_evidence["wrong_count"],
        "compiler_diagnostic_count": counts["compiler_diagnostic_count"],
        "compiler_blocked_declaration_count": counts[
            "compiler_blocked_declaration_count"
        ],
        "trusted_compiler_blocked_target_count": counts[
            "trusted_compiler_blocked_target_count"
        ],
        "trusted_header_blocking_target_count": counts[
            "trusted_header_blocking_target_count"
        ],
        "trusted_enclosing_type_blocking_target_count": counts[
            "trusted_enclosing_type_blocking_target_count"
        ],
        "public_candidate_pack_hash": summary["candidate_pack_hash"],
        "public_candidate_pack_tree_hash": integrity.candidate_pack_tree_hash,
        "public_replay_commitment_hash": summary["public_replay_commitment_hash"],
        "public_pack_integrity_receipt_hash": integrity.receipt_hash,
        "sealed_source_replay_receipt_hash": replay["receipt_hash"],
        "public_jdk_identity_receipt_hash": public_jdk.receipt_hash,
        "private_manifest_commitment_hash": replay["private_manifest_commitment_hash"],
        "candidate_pack_source_bearing_entry_count": 0,
        "candidate_pack_private_role_entry_count": 0,
        "candidate_pack_unknown_entry_count": 0,
        "reconstructed_pack_byte_difference_count": 0,
        "production_completed_before_evaluator": True,
        "production_evaluator_read_count": 0,
        "production_golden_read_count": 0,
        "production_network_access_count": 0,
        "production_host_path_field_count": files.get("host_path_field_count", 0),
        "sealed_replay_evaluator_read_count": replay["evaluator_read_count"],
        "sealed_replay_golden_read_count": replay["golden_read_count"],
        "sealed_replay_network_access_count": replay["network_access_count"],
        "post_trust_pack_failure_count": counts["post_trust_pack_failures"],
        "status": "PASS",
    }
    _write(
        args.output / "m336f_production_execution.json",
        {**body, "seal_hash": content_hash(body)},
    )


if __name__ == "__main__":
    main()
