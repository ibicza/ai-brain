"""Run and bind exact-platform quality for M-33.6k.4."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("WINDOWS", "KARINA"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--disposable-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    base = output.with_name(output.stem + "-m336k2-base.json")
    if output.exists() or base.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K4 quality output is stale or inside Git")
    environment = m336k2_minimal_environment()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(repository / "src"),
            "PYTHONUTF8": "1",
        }
    )
    subprocess.run(
        (
            sys.executable,
            "-B",
            str(repository / "scripts/m336k2_run_exact_quality.py"),
            "--repository",
            str(repository),
            "--platform",
            args.platform,
            "--expected-sha",
            args.expected_sha,
            "--git-executable",
            str(args.git_executable.resolve(strict=True)),
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--output",
            str(base),
        ),
        cwd=repository,
        check=True,
        env=environment,
    )
    base_receipt = _verified(args=base, hash_field="receipt_hash")
    disposable = _verified(
        args=args.disposable_proof.resolve(strict=True), hash_field="receipt_hash"
    )
    checks = tuple(base_receipt.get("checks", ()))
    passed = (
        base_receipt.get("status") == "PASS"
        and base_receipt.get("exact_sha") == args.expected_sha
        and base_receipt.get("post_check_exact_sha") == args.expected_sha
        and base_receipt.get("post_check_worktree_clean") is True
        and checks
        and all(item.get("exit_code") == 0 for item in checks)
        and disposable.get("status") == "PASS"
        and disposable.get("identity_observer_count") == 7
        and disposable.get("platform_source_identity_difference_count") == 0
        and disposable.get("windows_project_source_identity")
        == base_receipt.get("project_source_identity")
        and disposable.get("karina_project_source_identity")
        == base_receipt.get("project_source_identity")
        and disposable.get("official_one_shot_counter_count") == 0
        and disposable.get("identity_mutation_case_count") == 25
        and disposable.get("accepted_invalid_case_count") == 0
        and disposable.get("wrong_rejection_layer_count") == 0
        and disposable.get("source_leak_count") == 0
        and disposable.get("absolute_path_count") == 0
        and disposable.get("private_public_artifact_count") == 0
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K4_EXACT_PLATFORM_QUALITY",
        "platform_role": args.platform,
        "exact_sha": args.expected_sha,
        "project_source_identity": base_receipt.get("project_source_identity"),
        "base_quality_receipt_hash": base_receipt.get("receipt_hash"),
        "disposable_final_mode_proof_hash": disposable.get("receipt_hash"),
        "identity_mutation_receipt_hash": disposable.get(
            "identity_mutation_receipt_hash"
        ),
        "check_count": len(checks),
        "failed_check_count": sum(item.get("exit_code") != 0 for item in checks),
        "targeted_identity_status": "PASS" if passed else "FAIL",
        "final_request_builder_status": "PASS" if passed else "FAIL",
        "archive_campaign_status": "PASS" if passed else "FAIL",
        "mixed_candidate_campaign_status": "PASS" if passed else "FAIL",
        "ruff_format_status": _check_status(checks, "ruff_format"),
        "ruff_lint_status": _check_status(checks, "ruff_lint"),
        "compileall_status": _check_status(checks, "compileall"),
        "no_network_status": _check_status(checks, "no_network"),
        "no_torch_status": _check_status(checks, "no_torch"),
        "java_reference_status": _check_status(checks, "java_reference"),
        "stage3_suite_status": _check_status(checks, "stage3_java_regressions"),
        "complete_pytest_status": _check_status(checks, "full_suite"),
        "clean_worktree_status": "PASS"
        if base_receipt.get("post_check_worktree_clean")
        else "FAIL",
        "official_one_shot_counter_count": 0,
        "new_final_source_body_bytes": 0,
        "status": "PASS" if passed else "FAIL",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(output, receipt)
    print(canonical_json(receipt))
    if not passed:
        raise M336K2ProtocolError("M336K4 exact platform quality failed")


def _check_status(checks: tuple, name: str) -> str:
    rows = tuple(item for item in checks if item.get("name") == name)
    return "PASS" if len(rows) == 1 and rows[0].get("exit_code") == 0 else "FAIL"


def _verified(*, args: Path, hash_field: str) -> dict:
    value = json.loads(args.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K4 quality input is not an object")
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K4 quality input hash changed")
    return value


if __name__ == "__main__":
    main()
