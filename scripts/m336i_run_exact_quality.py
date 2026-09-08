"""Run exact M-33.6i quality gates and emit a public-safe receipt."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("WINDOWS", "KARINA"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    logs = output.with_name(output.stem + "-logs")
    if output.exists() or logs.exists():
        raise FileExistsError("M336I quality destination must be fresh")
    if output.is_relative_to(repository) or logs.is_relative_to(repository):
        raise ValueError("M336I quality evidence must remain outside Git")
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
    ).stdout.strip()
    if head != args.expected_sha or status:
        raise ValueError("M336I quality requires a clean exact commit")
    logs.mkdir(parents=True)
    python = sys.executable
    targeted_files = (
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
                "tests/test_m336i_authorized_final_java_route.py",
                "-k",
                "acquisition or provider",
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
                    "import sys; import ai_brain.stage3.acquisition.m336i_readiness; "
                    "raise SystemExit(1 if 'torch' in sys.modules else 0)"
                ),
            ),
            repository,
            logs,
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="m336i-quality-") as temporary:
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
                "route_preflight",
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
    post_head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    post_status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_QUALITY_RECEIPT",
        "platform_role": args.platform,
        "exact_sha": head,
        "checks": checks,
        "check_count": len(checks),
        "post_check_exact_sha": post_head,
        "post_check_worktree_clean": not post_status,
        "status": (
            "PASS"
            if all(item["exit_code"] == 0 for item in checks)
            and post_head == head
            and not post_status
            else "FAIL"
        ),
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(output, receipt)
    if receipt["status"] != "PASS":
        raise ValueError("M336I exact quality failed")


if __name__ == "__main__":
    main()
