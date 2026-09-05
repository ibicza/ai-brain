"""Run exact-commit M-33.6f quality gates with an explicit tested scope."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _run(command, root: Path):
    started = time.perf_counter()
    environment = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "-1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    }
    result = subprocess.run(
        tuple(str(item) for item in command),
        cwd=root,
        check=False,
        capture_output=True,
        env=environment,
    )
    output = ((result.stdout or b"") + (result.stderr or b"")).decode(
        "utf-8", errors="backslashreplace"
    )
    return (
        result.returncode,
        output.replace("\r\n", "\n").replace("\r", "\n"),
        f"{time.perf_counter() - started:.6f}",
    )


def _passed_count(output: str) -> int:
    return sum(int(value) for value in re.findall(r"(?:^|\s)(\d+) passed", output))


def _run_full_suite_isolated(root: Path):
    """Run every tracked test module in a fresh interpreter process."""

    tracked = subprocess.run(
        ("git", "ls-files", "-z", "--", "tests"),
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    test_files = tuple(
        sorted(
            (
                item.decode("utf-8", errors="strict")
                for item in tracked
                if item and re.fullmatch(rb"tests/(?:.*/)?test_[^/]+\.py", item)
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if not test_files:
        raise ValueError("full-suite isolation found no tracked test modules")
    started = time.perf_counter()
    logs = []
    passed = True
    for path in test_files:
        code, output, _seconds = _run(
            (sys.executable, "-m", "pytest", "-q", path), root
        )
        logs.append(f"===== {path} =====\n{output}")
        passed = passed and code == 0
    return (
        0 if passed else 1,
        "\n".join(logs),
        f"{time.perf_counter() - started:.6f}",
        len(test_files),
    )


def _tested_scope(root: Path) -> dict:
    completed = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = tuple(
        item.decode("utf-8", errors="strict")
        for item in completed.stdout.split(b"\0")
        if item
    )
    rows = tuple((path, bytes_hash((root / path).read_bytes())) for path in paths)
    body = {
        "schema_version": 1,
        "tracked_file_count": len(rows),
        "tracked_files": rows,
    }
    return {**body, "manifest_hash": content_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--upstream-ref", required=True)
    parser.add_argument(
        "--phase", choices=("R21", "Q21", "F21", "H21", "E21"), required=True
    )
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("fresh exact M-33.6f quality output already exists")
    if output.is_relative_to(root):
        raise ValueError("quality evidence must live outside the Git worktree")
    head = _run(("git", "rev-parse", "HEAD^{commit}"), root)[1].strip()
    if head != args.expected_head or len(head) != 40:
        raise ValueError("exact M-33.6f quality HEAD mismatch")
    scope = _tested_scope(root)
    targeted = (
        "tests/test_m336f_java_trust_closure.py",
        "tests/test_m336e_integration_closed.py",
        "tests/test_m336d_fresh_java_freeze_v3.py",
        "tests/test_m336c_spdx_contract_repair.py",
        "tests/test_m336b_production_provenance.py",
        "tests/test_m336_fresh_java_freeze.py",
        "tests/test_m342_java_type_universe.py",
        "tests/test_m344_oracle_free_java.py",
    )
    with tempfile.TemporaryDirectory(prefix="m336f-quality-javac-") as temporary:
        commands = {
            "ruff_format": (sys.executable, "-m", "ruff", "format", "--check", "."),
            "ruff_lint": (sys.executable, "-m", "ruff", "check", "."),
            "targeted": (sys.executable, "-m", "pytest", "-q", *targeted),
            "no_torch_network": (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_m29_educational_layer.py::test_trusted_education_import_does_not_load_torch_or_network_clients",
            ),
            "java_reference_compile": (
                args.javac.resolve(strict=True),
                "--release",
                "21",
                "-d",
                temporary,
                root / "tools/spdx-reference-java/src/IndependentSpdxReference.java",
            ),
        }
        results = {name: _run(command, root) for name, command in commands.items()}
        full_suite = _run_full_suite_isolated(root)
        results["full_suite"] = full_suite[:3]
    output.mkdir(parents=True)
    for name, (_code, log, _seconds) in results.items():
        (output / f"{name}.log").write_text(log, encoding="utf-8", newline="\n")
    (output / "tested_scope_manifest.json").write_text(
        canonical_json(scope) + "\n", encoding="utf-8", newline="\n"
    )
    status = _run(("git", "status", "--porcelain=v1"), root)[1]
    upstream = _run(("git", "rev-parse", f"{args.upstream_ref}^{{commit}}"), root)[
        1
    ].strip()
    body = {
        "schema_version": 1,
        "phase": args.phase,
        "platform": args.platform,
        "exact_head": head,
        "tested_scope_manifest_hash": scope["manifest_hash"],
        "ruff_format_pass": results["ruff_format"][0] == 0,
        "ruff_lint_pass": results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _passed_count(results["targeted"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "java_reference_compile_pass": results["java_reference_compile"][0] == 0,
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _passed_count(results["full_suite"][1]),
        "full_suite_test_file_count": full_suite[3],
        "clean_worktree": not status,
        "head_upstream_equal": head == upstream,
        "command_durations_seconds": tuple(
            (name, result[2]) for name, result in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((output / f"{name}.log").read_bytes()))
            for name in sorted(results)
        ),
    }
    passed = all(
        body[name]
        for name in (
            "ruff_format_pass",
            "ruff_lint_pass",
            "targeted_pass",
            "no_torch_network_pass",
            "java_reference_compile_pass",
            "full_suite_pass",
            "clean_worktree",
            "head_upstream_equal",
        )
    )
    report = {**body, "status": "PASS" if passed else "FAIL"}
    (output / "quality.json").write_text(
        canonical_json({**report, "report_hash": content_hash(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not passed:
        raise SystemExit("exact M-33.6f quality gate failed")


if __name__ == "__main__":
    main()
