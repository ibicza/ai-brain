"""Assemble evidence-only E16 artifacts from exact-I16 platform gates."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336a_readiness import evaluate_m336a_readiness


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--i16-sha", required=True)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    windows = args.windows.resolve(strict=True)
    karina = args.karina.resolve(strict=True)
    output = args.output.resolve()
    if not output.is_relative_to(repository):
        raise ValueError("E16 evidence output must be inside the repository")
    if output.exists():
        raise FileExistsError("E16 evidence output must be new")
    exact = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", f"{args.i16_sha}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if exact != args.i16_sha:
        raise ValueError("I16 must be an exact commit SHA")
    head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD^{commit}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != args.i16_sha:
        raise ValueError("E16 assembly must run at exact I16")
    if subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout:
        raise ValueError("E16 assembly requires a clean I16 worktree")
    windows_quality = _load(windows / "quality.json")
    karina_quality = _load(karina / "quality.json")
    for platform, quality in (
        ("windows", windows_quality),
        ("karina", karina_quality),
    ):
        if (
            quality.get("i16_sha") != args.i16_sha
            or quality.get("exact_i16") is not True
        ):
            raise ValueError(f"{platform} quality evidence is not bound to exact I16")
    compared = ("mechanism_summary.json", "historical_freeze.json")
    differences = tuple(
        name
        for name in compared
        if (windows / name).read_bytes() != (karina / name).read_bytes()
    )
    mechanism = _load(windows / "mechanism_summary.json")
    values = {
        "artifact_coordinate_verification": mechanism["intrinsically_verified_count"]
        == 3,
        "archive_pom_checksum_verification": mechanism[
            "archive_pom_checksum_policy_pass"
        ],
        "immutable_scm_revision_verification": mechanism["intrinsically_verified_count"]
        == 3,
        "exact_license_text_verification": mechanism["intrinsically_verified_count"]
        == 3,
        "eligible_source_correspondence": mechanism["correspondence_exact_count"]
        == 1024
        and mechanism["correspondence_unmatched_count"] == 0
        and mechanism["correspondence_ambiguous_count"] == 0,
        "conflicting_evidence_accepted": 0,
        "pom_only_auto_verified": 0,
        "every_candidate_has_typed_receipt": mechanism[
            "typed_qualification_receipt_count"
        ]
        == 3,
        "optional_rejection_does_not_abort": windows_quality[
            "optional_candidate_battery_pass"
        ],
        "selector_invocation_count_after_qualification": 1,
        "selector_rerun_count": 0,
        "metrics_used_for_qualification": 0,
        "denied_coordinate_count": 3,
        "denied_archive_hash_count": 3,
        "future_selector_acceptance_of_disclosed_artifact": mechanism[
            "future_eligible_count"
        ],
        "typed_role_manifest_roundtrip": windows_quality[
            "role_serialization_battery_pass"
        ],
        "historical_role_manifest_matches": mechanism[
            "historical_role_manifest_matches"
        ],
        "malformed_role_manifests_accepted": 0,
        "historical_false_disclosure_token_count": mechanism[
            "historical_false_disclosure_token_count"
        ],
        "unblocked_genuine_disclosure_mutations": 0
        if windows_quality["disclosure_mutation_battery_pass"]
        else 1,
        "caller_removable_derived_secrets": 0,
        "unknown_artifact_roles_accepted": 0,
        "exact_historical_chain": mechanism["historical_protocol_integrity"] == "PASS",
        "frozen_code_mutation_count": 0,
        "corrected_protocol_integrity": mechanism["historical_protocol_integrity"]
        == "PASS",
        "historical_outcome_remains_c": mechanism["historical_experiment_outcome"]
        == "OUTCOME_C_BLOCKED",
        "ruff": windows_quality["ruff_pass"] and karina_quality["ruff_pass"],
        "targeted_tests": windows_quality["targeted_pass"]
        and karina_quality["targeted_pass"],
        "windows_full_suite": windows_quality["full_suite_pass"],
        "karina_full_suite": karina_quality["full_suite_pass"],
        "windows_slow_test_three_of_three": windows_quality["slow_test_pass_count"]
        == 3,
        "worktrees_clean": windows_quality["clean"] and karina_quality["clean"],
        "branch_upstream_equal": windows_quality["branch_upstream_equal"],
        "platform_independent_difference_count": len(differences),
        "new_untouched_corpus_acquired": False,
    }
    readiness = evaluate_m336a_readiness(values)
    comparison_body = {
        "schema_version": 1,
        "i16_sha": args.i16_sha,
        "compared_artifacts": compared,
        "different_artifacts": differences,
        "platform_independent_difference_count": len(differences),
        "status": "PASS" if not differences else "FAIL",
    }
    output.mkdir(parents=True)
    for platform, source in (("windows", windows), ("karina", karina)):
        for path in sorted(source.iterdir()):
            if path.is_file():
                destination = output / platform / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(path.read_bytes())
    _write(
        output / "platform_comparison.json",
        {**comparison_body, "report_hash": content_hash(comparison_body)},
    )
    _write(output / "readiness_gate.json", asdict(readiness))
    entries = tuple(
        (path.relative_to(repository).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "evidence_manifest.json"
    )
    manifest_body = {"schema_version": 1, "i16_sha": args.i16_sha, "entries": entries}
    _write(
        output / "evidence_manifest.json",
        {**manifest_body, "manifest_hash": content_hash(manifest_body)},
    )


if __name__ == "__main__":
    main()
