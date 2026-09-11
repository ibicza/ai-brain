"""Run exact-SHA M-33.6k.2 quality gates and emit a public-safe receipt."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_python_environment_manifest,
    m336k2_python_invocation_handle,
)
from ai_brain.stage3.acquisition.m336k2_protocol import m336k2_minimal_environment


def _environment(
    repository: Path, *, executable_directories: tuple[Path, ...] = ()
) -> dict[str, str]:
    environment = m336k2_minimal_environment()
    environment.update(
        {
            "PATH": os.pathsep.join(
                str(directory.resolve(strict=True))
                for directory in executable_directories
            ),
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str((repository / "src").resolve(strict=True)),
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _check(
    name: str,
    command: tuple[str, ...],
    repository: Path,
    logs: Path,
    executable_directories: tuple[Path, ...],
) -> dict:
    pytest_basetemp = (logs.parent / "temp" / f"pytest-{name}").resolve(strict=False)
    if pytest_basetemp.is_relative_to(repository):
        raise ValueError("M336K2 pytest temp must remain outside Git")
    environment = _environment(
        repository, executable_directories=executable_directories
    )
    basetemp_argument = shlex.quote(pytest_basetemp.as_posix())
    environment["PYTEST_ADDOPTS"] = (
        "-p no:cacheprovider -o tmp_path_retention_policy=failed "
        f"--basetemp={basetemp_argument}"
    )
    started = time.perf_counter_ns()
    result = subprocess.run(
        command,
        cwd=repository,
        capture_output=True,
        check=False,
        env=environment,
    )
    elapsed = (time.perf_counter_ns() - started) // 1_000_000
    output = result.stdout + result.stderr
    if pytest_basetemp.exists():
        shutil.rmtree(pytest_basetemp)
    (logs / f"{name}.log").write_bytes(output)
    match = re.search(rb"(\d+) passed", output)
    body = {
        "name": name,
        "exit_code": result.returncode,
        "duration_ms": elapsed,
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
        errors="strict",
        env=_environment(repository),
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
    javac = args.javac.resolve(strict=True)
    python = m336k2_python_invocation_handle()
    python.resolve(strict=True)
    executable_directories = (git.parent, javac.parent, python.parent)
    output = args.output.resolve(strict=False)
    logs = output.with_name(output.stem + "-logs")
    if output.exists() or logs.exists():
        raise FileExistsError("M336K2 quality destination must be fresh")
    if output.is_relative_to(repository) or logs.is_relative_to(repository):
        raise ValueError("M336K2 quality evidence must remain outside Git")
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    status = _git(git, repository, "status", "--porcelain=v1")
    if head != args.expected_sha or status:
        raise ValueError("M336K2 quality requires a clean exact commit")
    source_identity = compute_m336j_project_source_identity(repository, git)
    environment_manifest = build_m336k2_python_environment_manifest(
        repository=repository,
        python_executable=python,
        git_executable=git,
    )
    logs.mkdir(parents=True)
    stage3_java_tests = tuple(
        str(path.relative_to(repository))
        for path in sorted((repository / "tests").glob("test_m336*.py"))
    )
    targeted = (
        "tests/test_m336k2_final_route.py",
        "tests/test_m336k_candidate_isolation.py",
        "tests/test_m336i_authorized_final_java_route.py",
        "tests/test_m336j_hermetic_karina_execution.py",
        "tests/test_m336j3_final_handshake.py",
        "tests/test_m336h_native_fresh_java_route.py",
        "tests/test_m336g_public_pack_private_replay.py",
        "tests/test_m336f_java_trust_closure.py",
        "tests/test_m336e_integration_closed.py",
    )
    checks = [
        _check(
            "targeted",
            (str(python), "-B", "-m", "pytest", "-q", *targeted),
            repository,
            logs,
            executable_directories,
        ),
        _check(
            "stage3_java_regressions",
            (str(python), "-B", "-m", "pytest", "-q", *stage3_java_tests),
            repository,
            logs,
            executable_directories,
        ),
        _check(
            "ruff_format",
            (str(python), "-B", "-m", "ruff", "format", "--check", "."),
            repository,
            logs,
            executable_directories,
        ),
        _check(
            "ruff_lint",
            (str(python), "-B", "-m", "ruff", "check", "."),
            repository,
            logs,
            executable_directories,
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="m336k2-compile-") as pycache:
        compile_environment = _environment(
            repository, executable_directories=executable_directories
        )
        compile_environment["PYTHONPYCACHEPREFIX"] = pycache
        started = time.perf_counter_ns()
        result = subprocess.run(
            (str(python), "-B", "-m", "compileall", "-q", "src", "scripts", "tests"),
            cwd=repository,
            capture_output=True,
            check=False,
            env=compile_environment,
        )
        elapsed = (time.perf_counter_ns() - started) // 1_000_000
        compile_output = result.stdout + result.stderr
        (logs / "compileall.log").write_bytes(compile_output)
        compile_body = {
            "name": "compileall",
            "exit_code": result.returncode,
            "duration_ms": elapsed,
            "output_bytes_hash": bytes_hash(compile_output),
            "passed_test_count": 0,
        }
        checks.append({**compile_body, "check_hash": content_hash(compile_body)})
    checks.extend(
        (
            _check(
                "no_network",
                (
                    str(python),
                    "-B",
                    "-c",
                    (
                        "import socket,pytest; "
                        "socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); "
                        "socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); "
                        "raise SystemExit(pytest.main(['-q','tests/test_m336k2_final_route.py','tests/test_m336k_candidate_isolation.py']))"
                    ),
                ),
                repository,
                logs,
                executable_directories,
            ),
            _check(
                "no_torch",
                (
                    str(python),
                    "-B",
                    "-c",
                    (
                        "import sys; import ai_brain.stage3.acquisition.m336k2_stage; "
                        "raise SystemExit(1 if 'torch' in sys.modules else 0)"
                    ),
                ),
                repository,
                logs,
                executable_directories,
            ),
            _check(
                "route_preflight",
                (
                    str(python),
                    "-B",
                    "-c",
                    (
                        "from ai_brain.stage3.acquisition.m336k2_controller import build_m336k2_schema_registry; "
                        "from ai_brain.stage3.acquisition.m336k2_registry import build_m336k2_route_registry; "
                        "r=build_m336k2_route_registry(__import__('pathlib').Path('.')); "
                        "s=build_m336k2_schema_registry(); "
                        "raise SystemExit(0 if len(r.components)>=1 and s.incompatible_edge_count==0 else 1)"
                    ),
                ),
                repository,
                logs,
                executable_directories,
            ),
        )
    )
    with tempfile.TemporaryDirectory(prefix="m336k2-java-") as java_output:
        checks.append(
            _check(
                "java_reference",
                (
                    str(javac),
                    "-d",
                    java_output,
                    str(
                        repository
                        / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"
                    ),
                ),
                repository,
                logs,
                executable_directories,
            )
        )
    checks.append(
        _check(
            "full_suite",
            (str(python), "-B", "-m", "pytest", "-q"),
            repository,
            logs,
            executable_directories,
        )
    )
    post_head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    post_status = _git(git, repository, "status", "--porcelain=v1")
    post_source_identity = compute_m336j_project_source_identity(repository, git)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_EXACT_QUALITY_RECEIPT",
        "platform_role": args.platform,
        "exact_sha": head,
        "project_source_identity": source_identity,
        "python_environment_manifest_hash": environment_manifest[
            "environment_manifest_hash"
        ],
        "checks": tuple(checks),
        "check_count": len(checks),
        "post_check_exact_sha": post_head,
        "post_check_project_source_identity": post_source_identity,
        "post_check_worktree_clean": not post_status,
        "status": (
            "PASS"
            if all(item["exit_code"] == 0 for item in checks)
            and post_head == head
            and post_source_identity == source_identity
            and not post_status
            else "FAIL"
        ),
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(output, receipt)
    if receipt["status"] != "PASS":
        raise ValueError("M336K2 exact quality failed")


if __name__ == "__main__":
    main()
