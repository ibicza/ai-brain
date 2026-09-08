"""Stage source-free M-33.6i H24 production evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336g_publication import (
    ArtifactConfidentialityRole,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336g_staging import validate_public_staging
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_acquisition import M336IFinalAcquisitionLedger
from ai_brain.stage3.acquisition.m336i_route import M336IRouteStateLedger


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I H24 input must be an object")
    return value


def _verified(path: Path, field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I H24 {field} differs from content")
    return value


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "repository",
        "final_route_receipt",
        "acquisition_receipt",
        "acquisition_ledger",
        "route_state_ledger",
        "selector_ledger",
        "windows_production_root",
        "karina_production_root",
        "sealed_vault",
        "output",
        "validation_output",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--expected-f24-sha", required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    validation = args.validation_output.resolve(strict=False)
    if _git(repository, "rev-parse", "HEAD^{commit}") != args.expected_f24_sha or _git(
        repository, "status", "--porcelain=v1"
    ):
        raise ValueError("M336I H24 publisher requires clean exact F24")
    if output.exists() or validation.exists():
        raise FileExistsError("M336I H24 destinations must be fresh")
    if not output.is_relative_to(repository) or validation.is_relative_to(repository):
        raise ValueError("M336I H24 public/external destinations are misplaced")
    final = _verified(args.final_route_receipt, "receipt_hash")
    acquisition = _verified(args.acquisition_receipt, "receipt_hash")
    if (
        final.get("contract_role") != "PUBLIC_SAFE_M336I_FINAL_ROUTE_RECEIPT"
        or final.get("status") != "OUTCOME A"
        or final.get("f24_sha") != args.expected_f24_sha
        or acquisition.get("status") != "PASS"
        or acquisition.get("exact_f24_sha") != args.expected_f24_sha
        or final.get("acquisition_receipt_hash") != acquisition.get("receipt_hash")
    ):
        raise ValueError("M336I H24 final route has not reached Outcome A readiness")
    windows_seal = _verified(
        args.windows_production_root / "m336i_production_seal.json", "seal_hash"
    )
    karina_seal = _verified(
        args.karina_production_root / "m336i_production_seal.json", "seal_hash"
    )
    windows_pack = verify_java_public_candidate_pack(
        args.windows_production_root / "candidate_pack"
    )
    karina_pack = verify_java_public_candidate_pack(
        args.karina_production_root / "candidate_pack"
    )
    windows_replay = _verified(
        args.windows_production_root / "sealed_source_replay_receipt.json",
        "receipt_hash",
    )
    karina_replay = _verified(
        args.karina_production_root / "sealed_source_replay_receipt.json",
        "receipt_hash",
    )
    windows_jdk = _verified(
        args.windows_production_root / "public_jdk_identity_receipt.json",
        "receipt_hash",
    )
    karina_jdk = _verified(
        args.karina_production_root / "public_jdk_identity_receipt.json",
        "receipt_hash",
    )
    excluded = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    if (
        windows_seal.get("platform_role") != "WINDOWS"
        or karina_seal.get("platform_role") != "KARINA"
        or {key: value for key, value in windows_seal.items() if key not in excluded}
        != {key: value for key, value in karina_seal.items() if key not in excluded}
        or windows_pack.candidate_pack_content_hash
        != karina_pack.candidate_pack_content_hash
        or windows_pack.candidate_pack_tree_hash != karina_pack.candidate_pack_tree_hash
        or windows_seal.get("status") != "PASS"
        or karina_seal.get("status") != "PASS"
        or windows_seal.get("sealed_source_replay_receipt_hash")
        != windows_replay.get("receipt_hash")
        or karina_seal.get("sealed_source_replay_receipt_hash")
        != karina_replay.get("receipt_hash")
        or windows_replay.get("status") != "PASS"
        or karina_replay.get("status") != "PASS"
        or windows_jdk.get("platform_role") != "windows"
        or karina_jdk.get("platform_role") != "karina"
    ):
        raise ValueError("M336I H24 platform-neutral production differs")
    acquisition_ledger = M336IFinalAcquisitionLedger(args.acquisition_ledger).receipt()
    route_ledger = M336IRouteStateLedger(args.route_state_ledger).receipt()
    selector_ledger = M336FSelectorLedger(args.selector_ledger).receipt()
    if (
        acquisition_ledger.acquisition_reservation_count != 1
        or acquisition_ledger.acquisition_start_count != 1
        or acquisition_ledger.acquisition_completion_count != 1
        or acquisition_ledger.acquisition_rerun_count
        or selector_ledger["selector_reservation_count"] != 1
        or selector_ledger["selector_invocation_count"] != 1
        or selector_ledger["selector_rerun_count"]
        or not route_ledger.complete
        or route_ledger.final_state != "OUTCOME_A_READY"
        or final.get("acquisition_ledger_receipt_hash")
        != acquisition_ledger.receipt_hash
        or final.get("route_state_ledger_receipt_hash") != route_ledger.receipt_hash
        or final.get("selector_receipt_hash") != selector_ledger.get("receipt_hash")
        or final.get("windows_production_seal_hash") != windows_seal.get("seal_hash")
        or final.get("karina_production_seal_hash") != karina_seal.get("seal_hash")
        or final.get("candidate_pack_content_hash")
        != windows_pack.candidate_pack_content_hash
        or final.get("candidate_pack_tree_hash")
        != windows_pack.candidate_pack_tree_hash
    ):
        raise ValueError("M336I H24 one-shot route counters changed")

    output.mkdir(parents=True)
    shutil.copytree(
        args.windows_production_root / "candidate_pack", output / "candidate-pack"
    )
    shutil.copytree(output / "candidate-pack", output / "installed-pack")
    receipt_root = output / "receipts"
    receipt_root.mkdir()
    for source, name in (
        (args.final_route_receipt, "final_route_receipt.json"),
        (args.acquisition_receipt, "acquisition_receipt.json"),
        (
            args.windows_production_root / "m336i_production_seal.json",
            "windows_production_seal.json",
        ),
        (
            args.karina_production_root / "m336i_production_seal.json",
            "karina_production_seal.json",
        ),
        (
            args.windows_production_root / "sealed_source_replay_receipt.json",
            "windows_replay_receipt.json",
        ),
        (
            args.karina_production_root / "sealed_source_replay_receipt.json",
            "karina_replay_receipt.json",
        ),
        (
            args.windows_production_root / "public_jdk_identity_receipt.json",
            "windows_jdk_identity_receipt.json",
        ),
        (
            args.karina_production_root / "public_jdk_identity_receipt.json",
            "karina_jdk_identity_receipt.json",
        ),
    ):
        shutil.copyfile(source, receipt_root / name)
    comparison_body = {
        "schema_version": 1,
        "windows_production_seal_hash": windows_seal["seal_hash"],
        "karina_production_seal_hash": karina_seal["seal_hash"],
        "candidate_pack_content_hash": windows_pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": windows_pack.candidate_pack_tree_hash,
        "platform_neutral_difference_count": 0,
        "physical_source_difference_count": 0,
        "portable_tree_difference_count": 0,
        "status": "PASS",
    }
    comparison = {**comparison_body, "receipt_hash": content_hash(comparison_body)}
    write_canonical_json(output / "cross_platform_production_receipt.json", comparison)
    report_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_H24_PRODUCTION_REPORT",
        "f24_sha": args.expected_f24_sha,
        "final_route_receipt_hash": final["receipt_hash"],
        "acquisition_receipt_hash": acquisition["receipt_hash"],
        "acquisition_ledger_receipt_hash": acquisition_ledger.receipt_hash,
        "route_state_ledger_receipt_hash": route_ledger.receipt_hash,
        "selector_ledger_receipt_hash": selector_ledger["receipt_hash"],
        "windows_production_seal_hash": windows_seal["seal_hash"],
        "karina_production_seal_hash": karina_seal["seal_hash"],
        "cross_platform_receipt_hash": comparison["receipt_hash"],
        "proposal_count": windows_seal["proposal_count"],
        "trusted_count": windows_seal["trusted_count"],
        "withheld_count": windows_seal["withheld_count"],
        "authorization_count": windows_seal["authorization_count"],
        "trusted_authorized_identity_difference_count": windows_seal[
            "trusted_authorized_identity_difference_count"
        ],
        "candidate_pack_content_hash": windows_pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": windows_pack.candidate_pack_tree_hash,
        "public_replay_commitment_hash": windows_seal["public_replay_commitment_hash"],
        "status": "PASS",
    }
    write_canonical_json(
        output / "production_report.json",
        {**report_body, "report_hash": content_hash(report_body)},
    )
    roles = {
        path.relative_to(output).as_posix(): (
            ArtifactConfidentialityRole.PUBLIC_DERIVED_PACK
            if path.relative_to(output).parts[0] in {"candidate-pack", "installed-pack"}
            else ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT
        )
        for path in output.rglob("*")
        if path.is_file()
    }
    rows = _rows(output)
    manifest, receipt = validate_public_staging(
        staging_root=output,
        artifact_roles=roles,
        sealed_vault_root=args.sealed_vault,
        candidate_pack_relative_path="candidate-pack",
        installed_pack_relative_path="installed-pack",
        prospective_git_tree_hash=content_hash(rows),
        prospective_git_entries=rows,
    )
    validation.mkdir(parents=True)
    write_canonical_json(validation / "h24_staging_manifest.json", manifest)
    write_canonical_json(validation / "h24_staging_receipt.json", receipt)
    write_canonical_json(
        validation / "route_state_ledger_receipt.json", asdict(route_ledger)
    )
    print(
        json.dumps(
            {
                "candidate_pack_hash": windows_pack.candidate_pack_content_hash,
                "h24_staging_tree_hash": manifest.staging_tree_hash,
                "status": "H24_READY_TO_COMMIT",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
