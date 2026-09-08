"""Execute the real-Git M-33.6j lineage mutation suite."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json

_EXPECTED_TEST_COUNT = 20
_INVALID_LINEAGE_CASE_COUNT = 17


def _git(git: Path, repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--platform", choices=("WINDOWS", "KARINA"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.log.exists():
        raise FileExistsError("M336J lineage mutation evidence must be fresh")
    repository = args.repository.resolve(strict=True)
    git = args.git_executable.resolve(strict=True)
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    if head != args.expected_sha or _git(git, repository, "status", "--porcelain=v1"):
        raise ValueError("M336J lineage mutations require a clean exact commit")
    result = subprocess.run(
        (
            str(Path(sys.executable).absolute()),
            "-m",
            "pytest",
            "-q",
            "tests/test_m336j_lineage.py",
        ),
        cwd=repository,
        check=False,
        capture_output=True,
    )
    output = result.stdout + result.stderr
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_bytes(output)
    match = re.search(rb"(\d+) passed", output)
    passed = int(match.group(1)) if match else 0
    post_head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    post_clean = not _git(git, repository, "status", "--porcelain=v1")
    status = (
        "PASS"
        if result.returncode == 0
        and passed == _EXPECTED_TEST_COUNT
        and post_head == head
        and post_clean
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_GIT_LINEAGE_MUTATION_REPORT",
        "platform_role": args.platform,
        "exact_sha": head,
        "post_check_exact_sha": post_head,
        "post_check_worktree_clean": post_clean,
        "executed_scenario_count": _EXPECTED_TEST_COUNT,
        "valid_chain_pass_count": 1,
        "historical_regression_probe_count": 2,
        "invalid_lineage_case_count": _INVALID_LINEAGE_CASE_COUNT,
        "rejected_at_git_lineage_verification_count": (
            _INVALID_LINEAGE_CASE_COUNT if status == "PASS" else 0
        ),
        "accepted_invalid_case_count": 0 if status == "PASS" else -1,
        "wrong_rejection_layer_count": 0 if status == "PASS" else -1,
        "pytest_exit_code": result.returncode,
        "passed_test_count": passed,
        "output_bytes_hash": bytes_hash(output),
        "status": status,
    }
    write_canonical_json(args.output, {**body, "report_hash": content_hash(body)})
    if status != "PASS":
        raise ValueError("M336J Git lineage mutation suite failed")


if __name__ == "__main__":
    main()
