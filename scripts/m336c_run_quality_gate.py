"""Run and preserve the exact-I18 M-33.6c platform quality gate."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

BRANCH = "exp/stage3-m336c-spdx-contract-repair"
E17 = "1541805f9cd6c19ff9c372afeefbd41148217736"


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


def _count(output: str) -> int:
    values = re.findall(r"(?:^|\s)(\d+) passed", output)
    return int(values[-1]) if values else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--i18-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M-33.6c quality output must be new")
    head = _run(("git", "rev-parse", "HEAD^{commit}"), root)[1].strip()
    branch = _run(("git", "branch", "--show-current"), root)[1].strip()
    initial_clean = not _run(("git", "status", "--porcelain"), root)[1]
    upstream = _run(("git", "rev-parse", f"origin/{BRANCH}^{{commit}}"), root)[
        1
    ].strip()
    changed = _run(("git", "diff", "--name-status", E17, args.i18_sha), root)[
        1
    ].splitlines()
    added_paths = tuple(
        line.split("\t", 1)[1]
        for line in changed
        if line.startswith("A\t") and "\t" in line
    )
    acquired_corpus_paths = tuple(
        path
        for path in added_paths
        if path.startswith("evaluation/")
        and (
            "/source_snapshots/" in path
            or (
                "/acquisition_bundle/candidates/" in path
                and path.endswith(("source.jar", "scm.zip", ".java"))
            )
        )
    )
    if head != args.i18_sha or branch or not initial_clean:
        raise ValueError("quality gate requires a clean detached exact-I18 worktree")
    targeted = (
        "tests/test_m335_java_determinism_repair.py",
        "tests/test_m336_fresh_java_freeze.py",
        "tests/test_m336a_license_freeze_repair.py",
        "tests/test_m336b_production_provenance.py",
        "tests/test_m336c_spdx_contract_repair.py",
        "tests/test_m341_java_trust_integration.py",
        "tests/test_m342_java_type_universe.py",
        "tests/test_m343_semantic_proposal_gate.py",
        "tests/test_m344_oracle_free_java.py",
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
        "full_suite": (sys.executable, "-m", "pytest", "-q"),
    }
    results = {name: _run(command, root) for name, command in commands.items()}
    args.output.mkdir(parents=True)
    for name, (_code, output, _duration) in results.items():
        (args.output / f"{name}.log").write_text(output, encoding="utf-8", newline="\n")
    final_clean = not _run(("git", "status", "--porcelain"), root)[1]
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "i18_sha": args.i18_sha,
        "exact_i18": head == args.i18_sha,
        "detached": not branch,
        "initial_clean": initial_clean,
        "ruff_format": results["ruff_format"][0] == 0,
        "ruff_lint": results["ruff_lint"][0] == 0,
        "targeted_pass": results["targeted"][0] == 0,
        "targeted_passed_count": _count(results["targeted"][1]),
        "full_suite_pass": results["full_suite"][0] == 0,
        "full_suite_passed_count": _count(results["full_suite"][1]),
        "no_torch_network_pass": results["no_torch_network"][0] == 0,
        "branch_upstream_equal": upstream == args.i18_sha,
        "clean": final_clean,
        "new_untouched_corpus_acquired": bool(acquired_corpus_paths),
        "new_untouched_corpus_paths": acquired_corpus_paths,
        "command_durations_seconds": tuple(
            (name, result[2]) for name, result in sorted(results.items())
        ),
        "command_log_hashes": tuple(
            (name, bytes_hash((args.output / f"{name}.log").read_bytes()))
            for name in sorted(results)
        ),
    }
    (args.output / "quality.json").write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    required = (
        body["exact_i18"],
        body["detached"],
        body["initial_clean"],
        body["ruff_format"],
        body["ruff_lint"],
        body["targeted_pass"],
        body["full_suite_pass"],
        body["no_torch_network_pass"],
        body["branch_upstream_equal"],
        body["clean"],
        not body["new_untouched_corpus_acquired"],
    )
    if not all(required):
        raise SystemExit("M-33.6c exact-I18 quality gate failed")


if __name__ == "__main__":
    main()
