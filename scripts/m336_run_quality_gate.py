"""Run the pre-F15 M-33.6 static, targeted, and full-suite quality gate."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_freeze_protocol import M336_BASE_SHA


def _run(command, root: Path):
    result = subprocess.run(
        tuple(str(item) for item in command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = (result.stdout + result.stderr).replace("\r\n", "\n")
    return result.returncode, output


def _count(output: str) -> int:
    matches = re.findall(r"(?:^|\s)(\d+) passed", output)
    return int(matches[-1]) if matches else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("quality gate output already exists")
    root = args.repository.resolve(strict=True)
    changed = set(
        _run(("git", "diff", "--name-only", M336_BASE_SHA), root)[1].splitlines()
    )
    changed.update(
        _run(("git", "ls-files", "--others", "--exclude-standard"), root)[
            1
        ].splitlines()
    )
    changed_python = tuple(sorted(path for path in changed if path.endswith(".py")))
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
            "tests/test_m336_fresh_java_freeze.py",
            "tests/test_m335_java_determinism_repair.py",
            "-q",
        ),
        "full_suite": (sys.executable, "-m", "pytest", "-q"),
    }
    results = {name: _run(command, root) for name, command in commands.items()}
    merge_base = _run(("git", "merge-base", "HEAD", M336_BASE_SHA), root)[1].strip()
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "exact_e14_base": merge_base == M336_BASE_SHA,
        "ruff_format_pass": results["ruff_format"][0] == 0,
        "ruff_lint_pass": results["ruff_lint"][0] == 0,
        "targeted_tests_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _count(results["targeted"][1]),
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _count(results["full_suite"][1]),
        "final_source_directory_absent": not (
            root / "evaluation/m336_final_java"
        ).exists(),
        "new_final_source_acquired_or_inspected": False,
        "command_output_hashes": tuple(
            (name, content_hash(output))
            for name, (_code, output) in sorted(results.items())
        ),
        "output_tails": tuple(
            (name, "\n".join(output.splitlines()[-8:]))
            for name, (_code, output) in sorted(results.items())
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not all(
        body[key]
        for key in (
            "exact_e14_base",
            "ruff_format_pass",
            "ruff_lint_pass",
            "targeted_tests_pass",
            "full_suite_pass",
            "final_source_directory_absent",
        )
    ):
        raise SystemExit("M-33.6 quality gate failed")


if __name__ == "__main__":
    main()
