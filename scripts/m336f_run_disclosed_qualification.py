"""Re-qualify the disclosed Java vault on exact R21 without selecting files."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    load_strict_json,
    run_disclosed_full_path_preflight,
)


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
        raise ValueError("disclosed qualification requires a clean exact-R21 worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r21-sha", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--historical-vault-manifest", type=Path, required=True)
    parser.add_argument("--historical-qualification", type=Path, required=True)
    parser.add_argument("--historical-f19-sha", required=True)
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    _require_clean_exact(repository, args.r21_sha)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("fresh exact-R21 qualification output already exists")

    registry_root = args.registry_root.resolve(strict=True)
    verify_disclosed_java_registry(registry_root)
    registry = load_disclosed_java_registry(registry_root)
    if len(registry) != 30:
        raise ValueError("exact-R21 disclosed registry does not contain 30 entries")
    registry_manifest = registry_root / "registry_manifest.json"

    preflight = run_disclosed_full_path_preflight(
        pool=load_strict_json(args.pool.resolve(strict=True)),
        vault_root=args.vault.resolve(strict=True),
        authority_statement=args.authority.resolve(strict=True),
        historical_f19_sha=args.historical_f19_sha,
        historical_public_vault_manifest=load_strict_json(
            args.historical_vault_manifest.resolve(strict=True)
        ),
        expected_historical_qualification=load_strict_json(
            args.historical_qualification.resolve(strict=True)
        ),
    )
    if preflight.status != "PASS":
        raise ValueError("exact-R21 disclosed authority/vault qualification failed")

    output.mkdir(parents=True)
    qualification_body = {
        "schema_version": 1,
        "candidate_count": len(preflight.candidates),
        "candidates": preflight.candidates,
        "historical_qualification_report_hash": preflight.historical_qualification_report[
            "report_hash"
        ],
    }
    qualification = {
        **qualification_body,
        "report_hash": content_hash(preflight.candidates),
    }
    _write(output / "portable_vault_manifest.json", asdict(preflight.vault_manifest))
    _write(output / "candidate_qualification.json", qualification)
    _write(
        output / "source_entry_binding_manifest.json",
        asdict(preflight.source_entry_binding_manifest),
    )
    _write(output / "selectability_census.json", asdict(preflight.selectability_census))
    _write(
        output / "legacy_selector_feasibility.json",
        asdict(preflight.feasibility_proof),
    )
    summary_body = {
        "schema_version": 1,
        "qualification_mode": "EXACT_R21_AUTHORITATIVE",
        "r21_sha": args.r21_sha,
        "preflight_report_hash": preflight.report_hash,
        "candidate_count": len(preflight.candidates),
        "analysis_eligible_root_count": preflight.historical_qualification_report[
            "analysis_eligible_root_count"
        ],
        "analysis_eligible_file_count": (
            preflight.selectability_census.analysis_eligible_file_count
        ),
        "parser_valid_file_count": preflight.selectability_census.parser_valid_file_count,
        "callable_file_count": preflight.selectability_census.callable_file_count,
        "production_supported_file_count": (
            preflight.selectability_census.production_supported_file_count
        ),
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "portable_vault_manifest_hash": preflight.vault_manifest.manifest_hash,
        "portable_vault_tree_hash": preflight.vault_manifest.portable_tree_hash,
        "candidate_qualification_hash": qualification["report_hash"],
        "source_entry_binding_manifest_hash": (
            preflight.source_entry_binding_manifest.manifest_hash
        ),
        "selectability_census_hash": preflight.selectability_census.census_hash,
        "legacy_feasibility_proof_hash": preflight.feasibility_proof.proof_hash,
        "registry_entry_count": len(registry),
        "registry_manifest_bytes_hash": bytes_hash(registry_manifest.read_bytes()),
        "authority_receipt_failure_count": preflight.authority_receipt_failure_count,
        "historical_qualification_equal": preflight.historical_qualification_equal,
        "selector_reservation_count": 0,
        "selector_invocation_count": 0,
        "selector_rerun_count": 0,
        "status": "PASS",
    }
    _write(
        output / "qualification_summary.json",
        {**summary_body, "summary_hash": content_hash(summary_body)},
    )


if __name__ == "__main__":
    main()
