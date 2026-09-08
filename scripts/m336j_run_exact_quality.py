"""Run exact M-33.6j quality gates and emit a public-safe receipt."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
)


def _run(command: tuple[str, ...], repository: Path) -> tuple[int, bytes]:
    result = subprocess.run(command, cwd=repository, capture_output=True, check=False)
    return result.returncode, result.stdout + result.stderr


def _check(name: str, command: tuple[str, ...], repository: Path, logs: Path) -> dict:
    exit_code, output = _run(command, repository)
    (logs / f"{name}.log").write_bytes(output)
    match = re.search(rb"(\d+) passed", output)
    body = {
        "name": name,
        "exit_code": exit_code,
        "output_bytes_hash": bytes_hash(output),
        "passed_test_count": int(match.group(1)) if match else 0,
    }
    return {**body, "check_hash": content_hash(body)}


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
    parser.add_argument("--platform", choices=("WINDOWS", "KARINA"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    git = args.git_executable.resolve(strict=True)
    output = args.output.resolve(strict=False)
    logs = output.with_name(output.stem + "-logs")
    if output.exists() or logs.exists():
        raise FileExistsError("M336J quality destination must be fresh")
    if output.is_relative_to(repository) or logs.is_relative_to(repository):
        raise ValueError("M336J quality evidence must remain outside Git")
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    status = _git(git, repository, "status", "--porcelain=v1")
    if head != args.expected_sha or status:
        raise ValueError("M336J quality requires a clean exact commit")
    project_source_identity = compute_m336j_project_source_identity(repository, git)
    logs.mkdir(parents=True)
    python = str(Path(sys.executable).absolute())
    targeted_files = (
        "tests/test_m336j_hermetic_karina_execution.py",
        "tests/test_m336j_lineage.py",
        "tests/test_m336j_evidence.py",
        "tests/test_m336i_authorized_final_java_route.py",
        "tests/test_m336h_native_fresh_java_route.py",
        "tests/test_m336g_public_pack_private_replay.py",
        "tests/test_m336f_java_trust_closure.py",
        "tests/test_m336e_integration_closed.py",
        "tests/test_m336d_fresh_java_freeze_v3.py",
    )
    checks = [
        _check(
            "targeted",
            (python, "-m", "pytest", "-q", *targeted_files),
            repository,
            logs,
        ),
        _check(
            "ruff_format",
            (python, "-m", "ruff", "format", "--check", "."),
            repository,
            logs,
        ),
        _check(
            "ruff_lint",
            (python, "-m", "ruff", "check", "."),
            repository,
            logs,
        ),
        _check(
            "compileall",
            (python, "-m", "compileall", "-q", "src", "scripts", "tests"),
            repository,
            logs,
        ),
        _check(
            "no_network",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/test_m336j_hermetic_karina_execution.py",
                "tests/test_m336i_authorized_final_java_route.py",
                "-k",
                "network or acquisition or provider",
            ),
            repository,
            logs,
        ),
        _check(
            "no_torch",
            (
                python,
                "-c",
                (
                    "import sys; import ai_brain.stage3.acquisition.m336j_execution; "
                    "raise SystemExit(1 if 'torch' in sys.modules else 0)"
                ),
            ),
            repository,
            logs,
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="m336j-quality-") as temporary:
        temp = Path(temporary)
        helper = repository / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"
        checks.append(
            _check(
                "java_reference",
                (str(args.javac.resolve(strict=True)), "-d", str(temp), str(helper)),
                repository,
                logs,
            )
        )
        checks.append(
            _check(
                "local_route_preflight",
                (
                    python,
                    "scripts/m336i_java_final_route.py",
                    "preflight",
                    "--output",
                    str(temp / "preflight"),
                ),
                repository,
                logs,
            )
        )
    checks.append(
        _check("full_suite", (python, "-m", "pytest", "-q"), repository, logs)
    )
    post_head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    post_status = _git(git, repository, "status", "--porcelain=v1")
    post_project_source_identity = compute_m336j_project_source_identity(
        repository, git
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_QUALITY_RECEIPT",
        "platform_role": args.platform,
        "exact_sha": head,
        "project_source_identity": project_source_identity,
        "checks": checks,
        "check_count": len(checks),
        "post_check_exact_sha": post_head,
        "post_check_project_source_identity": post_project_source_identity,
        "post_check_worktree_clean": not post_status,
        "receipt_hash": "",
        "status": (
            "PASS"
            if all(item["exit_code"] == 0 for item in checks)
            and post_head == head
            and post_project_source_identity == project_source_identity
            and not post_status
            else "FAIL"
        ),
    }
    body.pop("receipt_hash")
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(output, receipt)
    if receipt["status"] != "PASS":
        raise ValueError("M336J exact quality failed")


if __name__ == "__main__":
    main()
