"""Run exact-SHA M-33.6k.2 quality gates and emit a public-safe receipt."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import stat
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
from ai_brain.stage3.acquisition.m336k5_startup import (
    run_m336k5_bound_python_target,
    startup_receipt_from_path,
)


def _retry_readonly_removal(function, path: str, _error) -> None:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        function(path)
        return
    os.chmod(path, mode | stat.S_IWUSR)
    function(path)


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
    pytest_basetemp.parent.mkdir(parents=True, exist_ok=True)
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
        shutil.rmtree(pytest_basetemp, onexc=_retry_readonly_removal)
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


def _hermetic_python_check(
    *,
    name: str,
    platform_role: str,
    repository: Path,
    logs: Path,
    invocation_root: Path,
    python: Path,
    git: Path,
    powershell: Path | None,
    expected_startup_receipt_hash: str,
    target: Path | str,
    target_kind: str,
    arguments: tuple[str, ...],
    cleanup_root: Path | None = None,
) -> dict:
    started = time.perf_counter_ns()
    invocation, result, startup = run_m336k5_bound_python_target(
        platform_role=platform_role,
        process_role="EXACT_QUALITY",
        python_executable=python,
        git_executable=git,
        powershell_executable=powershell,
        repository=repository,
        working_directory=repository,
        bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
        target=target,
        target_kind=target_kind,
        arguments=arguments,
        launch_root=invocation_root / name,
        expected_startup_receipt_hash=expected_startup_receipt_hash,
    )
    elapsed = (time.perf_counter_ns() - started) // 1_000_000
    output = result.stdout + result.stderr
    if cleanup_root is not None and cleanup_root.exists():
        shutil.rmtree(cleanup_root, onexc=_retry_readonly_removal)
    (logs / f"{name}.log").write_bytes(output)
    match = re.search(rb"(\d+) passed", output)
    body = {
        "name": name,
        "exit_code": result.returncode,
        "duration_ms": elapsed,
        "output_bytes_hash": bytes_hash(output),
        "passed_test_count": int(match.group(1)) if match else 0,
        "python_invocation_plan_hash": invocation.invocation_plan_hash,
        "startup_receipt_hash": startup.receipt_hash,
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


def _pytest_arguments(
    temporary: Path, tests: tuple[str, ...]
) -> tuple[tuple[str, ...], Path]:
    basetemp = temporary.resolve(strict=False)
    return (
        (
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "tmp_path_retention_policy=failed",
            f"--basetemp={basetemp}",
            *tests,
        ),
        basetemp,
    )


def _pytest_probe_arguments(
    *,
    arguments: tuple[str, ...],
    git: Path,
    javac: Path,
    python: Path,
    powershell: Path | None,
) -> tuple[str, ...]:
    handles = (
        "pytest",
        "--git-executable",
        str(git),
        "--javac-executable",
        str(javac),
        "--python-executable",
        str(python),
        *(("--powershell-executable", str(powershell)) if powershell else ()),
        "--",
    )
    return (*handles, *arguments)


def _run_hermetic_checks(
    *,
    platform_role: str,
    repository: Path,
    logs: Path,
    invocation_root: Path,
    python: Path,
    git: Path,
    powershell: Path | None,
    javac: Path,
    expected_startup_receipt_hash: str,
    targeted: tuple[str, ...],
    stage3_java_tests: tuple[str, ...],
    executable_directories: tuple[Path, ...],
) -> list[dict]:
    temp_root = logs.parent / "temp"

    def python_check(
        name: str,
        target: Path | str,
        arguments: tuple[str, ...],
        *,
        target_kind: str = "MODULE",
        cleanup_root: Path | None = None,
    ) -> dict:
        return _hermetic_python_check(
            name=name,
            platform_role=platform_role,
            repository=repository,
            logs=logs,
            invocation_root=invocation_root,
            python=python,
            git=git,
            powershell=powershell,
            expected_startup_receipt_hash=expected_startup_receipt_hash,
            target=target,
            target_kind=target_kind,
            arguments=arguments,
            cleanup_root=cleanup_root,
        )

    targeted_arguments, targeted_temp = _pytest_arguments(
        temp_root / "pytest-targeted", targeted
    )
    stage_arguments, stage_temp = _pytest_arguments(
        temp_root / "pytest-stage3-java-regressions", stage3_java_tests
    )
    checks = [
        python_check(
            "targeted",
            repository / "scripts/m336k5_quality_probe.py",
            _pytest_probe_arguments(
                arguments=targeted_arguments,
                git=git,
                javac=javac,
                python=python,
                powershell=powershell,
            ),
            target_kind="SCRIPT",
            cleanup_root=targeted_temp,
        ),
        python_check(
            "stage3_java_regressions",
            repository / "scripts/m336k5_quality_probe.py",
            _pytest_probe_arguments(
                arguments=stage_arguments,
                git=git,
                javac=javac,
                python=python,
                powershell=powershell,
            ),
            target_kind="SCRIPT",
            cleanup_root=stage_temp,
        ),
        python_check("ruff_format", "ruff", ("format", "--check", ".")),
        python_check("ruff_lint", "ruff", ("check", ".")),
    ]
    compile_cache = temp_root / "compileall-cache"
    checks.append(
        python_check(
            "compileall",
            repository / "scripts/m336k5_quality_probe.py",
            (
                "compileall",
                "--pycache-root",
                str(compile_cache),
                "src",
                "scripts",
                "tests",
            ),
            target_kind="SCRIPT",
            cleanup_root=compile_cache,
        )
    )
    network_temp = temp_root / "pytest-no-network"
    checks.extend(
        (
            python_check(
                "no_network",
                repository / "scripts/m336k5_quality_probe.py",
                (
                    "no-network",
                    "--basetemp",
                    str(network_temp),
                    "--git-executable",
                    str(git),
                    "--javac-executable",
                    str(javac),
                    "--python-executable",
                    str(python),
                    *(
                        (
                            "--powershell-executable",
                            str(powershell),
                        )
                        if powershell
                        else ()
                    ),
                ),
                target_kind="SCRIPT",
                cleanup_root=network_temp,
            ),
            python_check(
                "no_torch",
                repository / "scripts/m336k5_quality_probe.py",
                ("no-torch",),
                target_kind="SCRIPT",
            ),
            python_check(
                "route_preflight",
                repository / "scripts/m336k5_quality_probe.py",
                ("route-preflight",),
                target_kind="SCRIPT",
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
    full_arguments, full_temp = _pytest_arguments(temp_root / "pytest-full-suite", ())
    checks.append(
        python_check(
            "full_suite",
            repository / "scripts/m336k5_quality_probe.py",
            _pytest_probe_arguments(
                arguments=full_arguments,
                git=git,
                javac=javac,
                python=python,
                powershell=powershell,
            ),
            target_kind="SCRIPT",
            cleanup_root=full_temp,
        )
    )
    return checks


def _run_legacy_checks(
    *,
    repository: Path,
    logs: Path,
    python: Path,
    javac: Path,
    targeted: tuple[str, ...],
    stage3_java_tests: tuple[str, ...],
    executable_directories: tuple[Path, ...],
) -> list[dict]:
    checks = [
        _check(
            name,
            command,
            repository,
            logs,
            executable_directories,
        )
        for name, command in (
            ("targeted", (str(python), "-B", "-m", "pytest", "-q", *targeted)),
            (
                "stage3_java_regressions",
                (str(python), "-B", "-m", "pytest", "-q", *stage3_java_tests),
            ),
            (
                "ruff_format",
                (str(python), "-B", "-m", "ruff", "format", "--check", "."),
            ),
            ("ruff_lint", (str(python), "-B", "-m", "ruff", "check", ".")),
        )
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
        output = result.stdout + result.stderr
        (logs / "compileall.log").write_bytes(output)
        body = {
            "name": "compileall",
            "exit_code": result.returncode,
            "duration_ms": elapsed,
            "output_bytes_hash": bytes_hash(output),
            "passed_test_count": 0,
        }
        checks.append({**body, "check_hash": content_hash(body)})
    inline_checks = (
        (
            "no_network",
            (
                "import socket,pytest; "
                "socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); "
                "socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')); "
                "raise SystemExit(pytest.main(['-q','tests/test_m336k2_final_route.py','tests/test_m336k_candidate_isolation.py']))"
            ),
        ),
        (
            "no_torch",
            (
                "import sys; import ai_brain.stage3.acquisition.m336k2_stage; "
                "raise SystemExit(1 if 'torch' in sys.modules else 0)"
            ),
        ),
        (
            "route_preflight",
            (
                "from ai_brain.stage3.acquisition.m336k2_controller import build_m336k2_schema_registry; "
                "from ai_brain.stage3.acquisition.m336k2_registry import build_m336k2_route_registry; "
                "r=build_m336k2_route_registry(__import__('pathlib').Path('.')); "
                "s=build_m336k2_schema_registry(); "
                "raise SystemExit(0 if len(r.components)>=1 and s.incompatible_edge_count==0 else 1)"
            ),
        ),
    )
    checks.extend(
        _check(
            name,
            (str(python), "-B", "-c", source),
            repository,
            logs,
            executable_directories,
        )
        for name, source in inline_checks
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
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("WINDOWS", "KARINA"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path)
    parser.add_argument("--powershell-executable", type=Path)
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
    invocation_root = output.with_name(output.stem + "-python-invocations")
    if output.exists() or logs.exists() or invocation_root.exists():
        raise FileExistsError("M336K2 quality destination must be fresh")
    if any(path.is_relative_to(repository) for path in (output, logs, invocation_root)):
        raise ValueError("M336K2 quality evidence must remain outside Git")
    startup = (
        startup_receipt_from_path(args.startup_receipt.resolve(strict=True))
        if args.startup_receipt is not None
        else None
    )
    powershell = (
        args.powershell_executable.resolve(strict=True)
        if args.powershell_executable is not None
        else None
    )
    if startup is not None and args.platform == "WINDOWS" and powershell is None:
        raise ValueError("M336K5 Windows quality requires exact PowerShell")
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
        *(
            str(path.relative_to(repository))
            for path in sorted((repository / "tests").glob("test_m336k5_*.py"))
        ),
        *(
            ("tests/test_m336k4_typed_final_identity.py",)
            if (repository / "tests/test_m336k4_typed_final_identity.py").is_file()
            else ()
        ),
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
    if startup is None:
        checks = _run_legacy_checks(
            repository=repository,
            logs=logs,
            python=python,
            javac=javac,
            targeted=targeted,
            stage3_java_tests=stage3_java_tests,
            executable_directories=executable_directories,
        )
    else:
        checks = _run_hermetic_checks(
            platform_role=args.platform,
            repository=repository,
            logs=logs,
            invocation_root=invocation_root,
            python=python,
            git=git,
            powershell=powershell,
            javac=javac,
            expected_startup_receipt_hash=startup.receipt_hash,
            targeted=targeted,
            stage3_java_tests=stage3_java_tests,
            executable_directories=executable_directories,
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
        "startup_receipt_hash": startup.receipt_hash if startup is not None else None,
        "hermetic_python_invocation_count": sum(
            "python_invocation_plan_hash" in item for item in checks
        ),
        "unclassified_python_process_launch_count": 0,
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
