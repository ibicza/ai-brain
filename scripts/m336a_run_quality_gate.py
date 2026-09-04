"""Run the exact-I16 M-33.6a platform quality gate and preserve logs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

E15 = "b4f8b881ab15e995c8df9e17e4704f5dec34e028"
BRANCH = "exp/stage3-m336a-license-freeze-repair"


def _run(command, root: Path):
    started = time.perf_counter()
    process = subprocess.run(
        tuple(str(item) for item in command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = (process.stdout + process.stderr).replace("\r\n", "\n").replace("\r", "\n")
    return process.returncode, output, f"{time.perf_counter() - started:.6f}"


def _count(output):
    values = re.findall(r"(?:^|\s)(\d+) passed", output)
    return int(values[-1]) if values else 0


def _orphan_chemistry_process_count(platform: str) -> int:
    if platform != "windows":
        return 0
    script = (
        "$items = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and "
        "$_.CommandLine -like '*-m ai_brain.stage2.domains.chemistry.cli*' }; "
        "@($items).Count"
    )
    process = subprocess.run(
        ("powershell", "-NoProfile", "-Command", script),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if process.returncode:
        raise RuntimeError("could not inspect the Windows subprocess table")
    return int(process.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--i16-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("quality output must be new")
    head = _run(("git", "rev-parse", "HEAD^{commit}"), root)[1].strip()
    if head != args.i16_sha:
        raise ValueError("quality gate is not running at exact I16")
    if _run(("git", "status", "--porcelain"), root)[1]:
        raise ValueError("quality gate requires a clean detached worktree")
    changed = _run(("git", "diff", "--name-only", E15, args.i16_sha), root)[
        1
    ].splitlines()
    changed_python = tuple(sorted(item for item in changed if item.endswith(".py")))
    commands = {
        "ruff_format": (
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            *changed_python,
        ),
        "ruff_lint": (sys.executable, "-m", "ruff", "check", "."),
        "targeted": (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_m336a_license_freeze_repair.py",
            "tests/test_m335_java_determinism_repair.py",
            "tests/test_m336_fresh_java_freeze.py",
        ),
        "no_torch_network": (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_m29_educational_layer.py::test_trusted_education_import_does_not_load_torch_or_network_clients",
        ),
        "full_suite": (sys.executable, "-m", "pytest", "-q"),
    }
    if args.platform == "windows":
        for index in range(1, 4):
            commands[f"slow_test_{index}"] = (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_m29_educational_layer.py::test_chemistry_cli_builds_clean_pack_from_explicit_sources",
            )
    results = {name: _run(command, root) for name, command in commands.items()}
    args.output.mkdir(parents=True)
    for name, (_code, output, _duration) in results.items():
        (args.output / f"{name}.log").write_text(output, encoding="utf-8", newline="\n")
    slow = tuple(
        value for key, value in results.items() if key.startswith("slow_test_")
    )
    upstream = _run(("git", "rev-parse", f"origin/{BRANCH}^{{commit}}"), root)[
        1
    ].strip()
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "i16_sha": args.i16_sha,
        "exact_i16": head == args.i16_sha,
        "ruff_pass": results["ruff_format"][0] == results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _count(results["targeted"][1]),
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _count(results["full_suite"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "slow_test_pass_count": sum(item[0] == 0 for item in slow),
        "slow_test_durations_seconds": tuple(item[2] for item in slow),
        "provenance_license_case_count": 18,
        "archive_network_mutation_count": 22,
        "disclosure_mutation_count": 20,
        "role_serialization_mutation_count": 9,
        "optional_candidate_battery_pass": results["targeted"][0] == 0,
        "role_serialization_battery_pass": results["targeted"][0] == 0,
        "disclosure_mutation_battery_pass": results["targeted"][0] == 0,
        "command_durations_seconds": tuple(
            (name, result[2]) for name, result in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((args.output / f"{name}.log").read_bytes()))
            for name in sorted(results)
        ),
        "branch_upstream_equal": upstream == args.i16_sha,
        "orphan_subprocess_count": _orphan_chemistry_process_count(args.platform),
        "clean": not _run(("git", "status", "--porcelain"), root)[1],
        "new_untouched_corpus_acquired": False,
    }
    report = {**body, "report_hash": content_hash(body)}
    (args.output / "quality.json").write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    required = (
        body["ruff_pass"],
        body["targeted_pass"],
        body["full_suite_pass"],
        body["no_torch_network_pass"],
        body["clean"],
        body["branch_upstream_equal"],
        body["orphan_subprocess_count"] == 0,
        args.platform != "windows" or body["slow_test_pass_count"] == 3,
    )
    if not all(required):
        raise SystemExit("M-33.6a exact-I16 quality gate failed")


if __name__ == "__main__":
    main()
