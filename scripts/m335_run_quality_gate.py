"""Run exact-I14 Ruff and pytest quality checks and record bounded logs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json

E13 = "f1599585c7b45e73eb3ba3cd9113155188eb6d26"
BRANCH = "exp/stage3-m335-java-determinism-repair"
TARGETED_TESTS = (
    "tests/test_m34_blocker_rework.py",
    "tests/test_m341_java_trust_integration.py",
    "tests/test_m342_java_type_universe.py",
    "tests/test_m343_semantic_proposal_gate.py",
    "tests/test_m344_oracle_free_java.py",
    "tests/test_m335_java_determinism_repair.py",
)


def _git(project: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ("git", "-C", str(project), *args),
        check=check,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _run(output: Path, name: str, command: tuple[str, ...], project: Path):
    completed = subprocess.run(
        command,
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    (output / f"{name}.log").write_text(
        completed.stdout, encoding="utf-8", newline="\n"
    )
    return completed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--exact-i14", required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M-33.5 quality output already exists")
    args.output.mkdir(parents=True)
    head = _git(project, "rev-parse", "HEAD")
    if head != args.exact_i14:
        raise ValueError("quality gate is not running at exact I14")
    parent = _git(project, "rev-parse", "HEAD^")
    if parent != E13:
        raise ValueError("I14 is not the sole child of exact E13")
    clean_before = not _git(project, "status", "--porcelain=v1")
    changed_python = tuple(
        path
        for path in _git(project, "diff", "--name-only", f"{E13}..HEAD").splitlines()
        if path.endswith(".py")
    )
    if not changed_python:
        raise ValueError("I14 has no changed Python implementation")
    commands = {
        "ruff_format": (
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            *changed_python,
        ),
        "ruff_lint": (
            sys.executable,
            "-m",
            "ruff",
            "check",
            *changed_python,
        ),
        "targeted_tests": (
            sys.executable,
            "-m",
            "pytest",
            *TARGETED_TESTS,
            "-q",
        ),
        "full_suite": (sys.executable, "-m", "pytest", "-q"),
    }
    completed = {
        name: _run(args.output, name, command, project)
        for name, command in commands.items()
    }
    match = re.search(r"(\d+) passed", completed["full_suite"].stdout)
    upstream = _git(project, "rev-parse", "--verify", f"origin/{BRANCH}", check=False)
    clean_after = not _git(project, "status", "--porcelain=v1")
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "exact_i14_sha": args.exact_i14,
        "ruff_format_pass": completed["ruff_format"].returncode == 0,
        "ruff_lint_pass": completed["ruff_lint"].returncode == 0,
        "targeted_tests_pass": completed["targeted_tests"].returncode == 0,
        "full_suite_pass": completed["full_suite"].returncode == 0,
        "full_suite_passed_count": int(match.group(1)) if match else 0,
        "clean_worktree": clean_before and clean_after,
        "branch_upstream_equal": upstream == args.exact_i14,
        "production_evaluator_substitution_invariant": completed[
            "targeted_tests"
        ].returncode
        == 0,
        "new_untouched_final_evaluation_executed": False,
    }
    (args.output / "quality_report.json").write_text(
        canonical_json(body) + "\n", encoding="utf-8", newline="\n"
    )
    if not all(
        (
            body["ruff_format_pass"],
            body["ruff_lint_pass"],
            body["targeted_tests_pass"],
            body["full_suite_pass"],
            body["clean_worktree"],
            body["branch_upstream_equal"],
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
