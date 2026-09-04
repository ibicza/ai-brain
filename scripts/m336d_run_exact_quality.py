"""Run exact-commit M-33.6d quality gates and preserve immutable logs."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _run(command, root: Path):
    started = time.perf_counter()
    result = subprocess.run(
        tuple(str(item) for item in command),
        cwd=root,
        check=False,
        capture_output=True,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": "-1"},
    )
    output = ((result.stdout or b"") + (result.stderr or b"")).decode(
        "utf-8", errors="backslashreplace"
    )
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    return result.returncode, output, f"{time.perf_counter() - started:.6f}"


def _count(output: str) -> int:
    matches = re.findall(r"(?:^|\s)(\d+) passed", output)
    return sum(int(item) for item in matches)


def _test_files(root: Path) -> tuple[str, ...]:
    return tuple(
        path.relative_to(root).as_posix()
        for path in sorted((root / "tests").rglob("test_*.py"))
    )


def _run_full_suite(root: Path):
    files = _test_files(root)
    results = [
        _run((sys.executable, "-m", "pytest", "-q", path), root) for path in files
    ]
    output = "".join(
        (
            f"=== FULL SUITE FILE {index + 1}/{len(files)} {files[index]} ===\n"
            f"{result[1]}"
            f"=== FULL SUITE EXIT {result[0]} {files[index]} ===\n"
        )
        for index, result in enumerate(results)
    )
    return (
        int(any(result[0] for result in results)),
        output,
        f"{sum(float(result[2]) for result in results):.6f}",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--upstream-ref", required=True)
    parser.add_argument("--phase", choices=("F19", "H19", "E19"), required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh exact quality output exists")
    head = _run(("git", "rev-parse", "HEAD^{commit}"), root)[1].strip()
    if head != args.expected_head or len(head) != 40:
        raise ValueError("exact quality HEAD mismatch")
    targeted = (
        "tests/test_m336d_fresh_java_freeze_v3.py",
        "tests/test_m336c_spdx_contract_repair.py",
        "tests/test_m336b_production_provenance.py",
        "tests/test_m336_fresh_java_freeze.py",
    )
    classes = args.output.parent / f".{args.output.name}-java-classes"
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
            str(args.javac),
            "--release",
            "21",
            "-d",
            str(classes),
            str(root / "tools/spdx-reference-java/src/IndependentSpdxReference.java"),
        ),
    }
    results = {name: _run(command, root) for name, command in commands.items()}
    results["full_suite"] = _run_full_suite(root)
    args.output.mkdir(parents=True)
    for name, (_code, log, _duration) in results.items():
        (args.output / f"{name}.log").write_text(log, encoding="utf-8", newline="\n")
    status_before = _run(("git", "status", "--porcelain=v1"), root)[1]
    remote = _run(("git", "rev-parse", f"{args.upstream_ref}^{{commit}}"), root)[
        1
    ].strip()
    body = {
        "schema_version": 1,
        "phase": args.phase,
        "platform": args.platform,
        "exact_head": head,
        "ruff_format_pass": results["ruff_format"][0] == 0,
        "ruff_lint_pass": results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _count(results["targeted"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _count(results["full_suite"][1]),
        "full_suite_shard_count": len(_test_files(root)),
        "full_suite_parallelism": 1,
        "java_reference_compile_pass": results["java_reference_compile"][0] == 0,
        "clean_worktree": not status_before,
        "head_remote_equal": head == remote,
        "command_durations_seconds": tuple(
            (name, result[2]) for name, result in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((args.output / f"{name}.log").read_bytes()))
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
            "full_suite_pass",
            "java_reference_compile_pass",
            "clean_worktree",
            "head_remote_equal",
        )
    )
    report = {**body, "status": "PASS" if passed else "FAIL"}
    (args.output / "quality.json").write_text(
        canonical_json({**report, "report_hash": content_hash(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if classes.exists():
        for path in sorted(classes.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        classes.rmdir()
    if not passed:
        raise SystemExit("exact M-33.6d quality gate failed")


if __name__ == "__main__":
    main()
