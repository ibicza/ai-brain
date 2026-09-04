"""Run the disclosed-only R19 quality gate and preserve exact command evidence."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

E18 = "38082dd1eab82ebfff46ad3c55f5021068909f83"


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
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh R19 quality output already exists")
    base = _run(("git", "rev-parse", "HEAD^{commit}"), root)[1].strip()
    if base != E18:
        raise ValueError("R19 quality gate must start from exact E18")
    files = tuple(
        sorted(
            line
            for line in _run(
                ("git", "ls-files", "--cached", "--others", "--exclude-standard"),
                root,
            )[1].splitlines()
            if not line.startswith("runs/m336d_pre_freeze_disclosed/")
        )
    )
    implementation_rows = tuple(
        (path, bytes_hash((root / path).read_bytes())) for path in files
    )
    forbidden_new_source_paths = tuple(
        path
        for path in _run(("git", "ls-files", "--others", "--exclude-standard"), root)[
            1
        ].splitlines()
        if (
            "/source_snapshots/" in f"/{path}"
            or path.endswith(("source.jar", "scm.zip"))
            or (path.startswith("evaluation/") and path.endswith(".java"))
        )
    )
    targeted = (
        "tests/test_m336d_fresh_java_freeze_v3.py",
        "tests/test_m336c_spdx_contract_repair.py",
        "tests/test_m336b_production_provenance.py",
        "tests/test_m336_fresh_java_freeze.py",
    )
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
    }
    results = {name: _run(command, root) for name, command in commands.items()}
    results["full_suite"] = _run_full_suite(root)
    output.mkdir(parents=True)
    for name, (_code, log, _duration) in results.items():
        (output / f"{name}.log").write_text(log, encoding="utf-8", newline="\n")
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "e18_sha": E18,
        "implementation_tree_hash": content_hash(implementation_rows),
        "implementation_file_count": len(implementation_rows),
        "ruff_format_pass": results["ruff_format"][0] == 0,
        "ruff_lint_pass": results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _count(results["targeted"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _count(results["full_suite"][1]),
        "full_suite_shard_count": len(_test_files(root)),
        "full_suite_parallelism": 1,
        "pre_f19_source_body_byte_count": sum(
            (root / path).stat().st_size for path in forbidden_new_source_paths
        ),
        "pre_f19_source_body_paths": forbidden_new_source_paths,
        "command_durations_seconds": tuple(
            (name, result[2]) for name, result in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((output / f"{name}.log").read_bytes()))
            for name in sorted(results)
        ),
    }
    passed = (
        all(
            body[name]
            for name in (
                "ruff_format_pass",
                "ruff_lint_pass",
                "targeted_pass",
                "no_torch_network_pass",
                "full_suite_pass",
            )
        )
        and body["pre_f19_source_body_byte_count"] == 0
    )
    report = {**body, "status": "PASS" if passed else "FAIL"}
    (output / "quality.json").write_text(
        canonical_json({**report, "report_hash": content_hash(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not passed:
        raise SystemExit("M-33.6d R19 quality gate failed")


if __name__ == "__main__":
    main()
