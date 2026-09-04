"""Run the exact-I18 disclosed six-root M-33.6c rehearsal on one platform."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

BRANCH = "exp/stage3-m336c-spdx-contract-repair"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _run(name: str, command, root: Path, log_root: Path):
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
    log_root.mkdir(parents=True, exist_ok=True)
    log = log_root / f"{name}.log"
    log.write_text(output, encoding="utf-8", newline="\n")
    if process.returncode:
        raise RuntimeError(f"M-33.6c {name} failed; see {log}")
    return f"{time.perf_counter() - started:.6f}", bytes_hash(log.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--i18-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("M-33.6c rehearsal gate output must be new")
    if (
        _git(root, "rev-parse", "HEAD^{commit}") != args.i18_sha
        or _git(root, "branch", "--show-current")
        or _git(root, "status", "--porcelain")
    ):
        raise ValueError("rehearsal requires a clean detached exact-I18 worktree")
    if _git(root, "rev-parse", f"origin/{BRANCH}^{{commit}}") != args.i18_sha:
        raise ValueError("exact I18 is not equal to the pushed branch")
    args.output.mkdir(parents=True)
    log_root = args.output / "logs"
    disclosed = root / "evaluation/m336b_final_java/acquisition_bundle/candidates"
    steps = (
        (
            "preparation",
            (
                sys.executable,
                root / "scripts/m336c_prepare_disclosed_java.py",
                "--disclosed-root",
                disclosed,
                "--work-root",
                args.output / "work_roots",
                "--selected-root",
                args.output / "selected",
                "--output",
                args.output / "preparation",
            ),
        ),
        (
            "production",
            (
                sys.executable,
                root / "scripts/m336_run_oracle_free_production.py",
                "--source-root",
                args.output / "selected",
                "--output",
                args.output / "production",
                "--platform",
                args.platform,
            ),
        ),
        (
            "evaluation",
            (
                sys.executable,
                root / "scripts/m336c_evaluate_disclosed_java.py",
                "--source-root",
                args.output / "selected",
                "--production-root",
                args.output / "production",
                "--authority-report",
                args.output / "preparation/candidate_authority.json",
                "--java",
                args.java.resolve(strict=True),
                "--javac",
                args.javac.resolve(strict=True),
                "--platform",
                args.platform,
                "--i18-sha",
                args.i18_sha,
                "--output",
                args.output / "evaluation",
            ),
        ),
        (
            "development_evidence",
            (
                sys.executable,
                root / "scripts/m336c_build_development_evidence.py",
                "--project",
                root,
                "--preparation",
                args.output / "preparation",
                "--production",
                args.output / "production",
                "--evaluation",
                args.output / "evaluation",
                "--output",
                args.output / "development",
                "--platform",
                args.platform,
            ),
        ),
    )
    measurements = []
    for name, command in steps:
        duration, log_hash = _run(name, command, root, log_root)
        measurements.append((name, duration, log_hash))
    preparation = _load(args.output / "preparation/preparation_summary.json")
    production = _load(args.output / "production/production_summary.json")
    evaluation = _load(args.output / "evaluation/evaluation_summary.json")
    mutations = _load(args.output / "development/contract_mutations.json")
    h17 = _load(args.output / "development/h17_contract_forensics.json")
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "i18_sha": args.i18_sha,
        "analysis_eligible_root_count": preparation["analysis_eligible_root_count"],
        "selected_source_count": preparation["selected_source_count"],
        "selector_invocation_count": preparation["selector_invocation_count"],
        "selector_rerun_count": preparation["selector_rerun_count"],
        "production_status": production["status"],
        "production_output_hash": production["production_output_hash"],
        "candidate_pack_hash": production["candidate_pack_hash"],
        "candidate_tree_hash": production["candidate_tree_hash"],
        "candidate_replay_status": production["candidate_replay_status"],
        "evaluation_status": evaluation["status"],
        "runtime_status": evaluation["runtime_status"],
        "wrong_trusted_count": evaluation["wrong_trusted_count"],
        "contract_mutations_rejected": mutations["rejected_count"],
        "contract_mutation_count": mutations["mutation_count"],
        "h17_status": h17["status"],
        "step_measurements": tuple(measurements),
        "clean": not _git(root, "status", "--porcelain"),
    }
    passed = (
        body["analysis_eligible_root_count"] >= 4
        and body["selector_invocation_count"] == 1
        and body["selector_rerun_count"] == 0
        and body["production_status"] == "PASS"
        and body["candidate_replay_status"] == "PASS"
        and body["evaluation_status"] == "PASS"
        and body["runtime_status"] == "PASS"
        and body["wrong_trusted_count"] == 0
        and body["contract_mutations_rejected"] == body["contract_mutation_count"]
        and body["h17_status"] == "PASS"
        and body["clean"]
    )
    report = {**body, "status": "PASS" if passed else "FAIL"}
    (args.output / "rehearsal_gate.json").write_text(
        canonical_json({**report, "report_hash": content_hash(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not passed:
        raise SystemExit("M-33.6c exact-I18 rehearsal failed")


if __name__ == "__main__":
    main()
