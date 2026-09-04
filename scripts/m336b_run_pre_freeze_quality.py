"""Run M-33.6b pre-F17 quality checks and emit a hashed raw report."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def _run(command: tuple[str, ...], root: Path):
    started = time.perf_counter()
    process = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )
    output = (process.stdout + process.stderr).replace("\r\n", "\n").replace("\r", "\n")
    return process.returncode, output, f"{time.perf_counter() - started:.6f}"


def _passed_count(output: str) -> int:
    values = re.findall(r"(?:^|\s)(\d+) passed", output)
    return int(values[-1]) if values else 0


def _tree_hash(root: Path) -> str:
    tracked = _run(("git", "ls-files", "-co", "--exclude-standard"), root)[1]
    rows = []
    for relative in sorted(item for item in tracked.splitlines() if item):
        path = root / relative
        if path.is_file():
            rows.append((relative.replace("\\", "/"), bytes_hash(path.read_bytes())))
    return content_hash(tuple(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("quality output must be new")
    args.output.mkdir(parents=True)
    changed = _run(("git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"), root)[
        1
    ].splitlines()
    untracked = _run(("git", "ls-files", "--others", "--exclude-standard"), root)[
        1
    ].splitlines()
    changed_python = tuple(
        sorted({item for item in (*changed, *untracked) if item.endswith(".py")})
    )
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
            "tests/test_m335_java_determinism_repair.py",
            "tests/test_m336_fresh_java_freeze.py",
            "tests/test_m336a_license_freeze_repair.py",
            "tests/test_m336b_production_provenance.py",
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
    results = {name: _run(command, root) for name, command in commands.items()}
    for name, (_code, output, _duration) in results.items():
        (args.output / f"{name}.log").write_text(output, encoding="utf-8", newline="\n")
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "implementation_tree_hash": _tree_hash(root),
        "changed_python_paths": changed_python,
        "ruff_pass": results["ruff_format"][0] == results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _passed_count(results["targeted"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _passed_count(results["full_suite"][1]),
        "command_exit_codes": tuple(
            (name, value[0]) for name, value in sorted(results.items())
        ),
        "command_durations_seconds": tuple(
            (name, value[2]) for name, value in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((args.output / f"{name}.log").read_bytes()))
            for name in sorted(results)
        ),
    }
    report = {**body, "report_hash": content_hash(body)}
    (args.output / "quality.json").write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if not all(
        (
            body["ruff_pass"],
            body["targeted_pass"],
            body["no_torch_network_pass"],
            body["full_suite_pass"],
        )
    ):
        raise SystemExit("M-33.6b pre-freeze quality gate failed")


if __name__ == "__main__":
    main()
