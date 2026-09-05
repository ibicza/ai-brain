"""Run one exact-R21 disclosed compiler-aware production seal."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    frozen_m336_jdk_provider_manifest,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    java_production_compilation_probe_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
    m336f_selector_receipt_from_dict,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.m336f_thresholds import (
    M336F_JAVA_ACCEPTANCE_THRESHOLDS,
)


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _require_clean_exact(repository: Path, expected: str) -> None:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != expected or len(head) != 40 or status:
        raise ValueError("production requires a clean exact-R21 worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r21-sha", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--closure-proof", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--development",
        action="store_true",
        help="allow a dirty pre-R21 worktree and mark output non-authoritative",
    )
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if not args.development:
        _require_clean_exact(repository, args.r21_sha)
    if args.output.exists():
        raise FileExistsError("fresh production output already exists")
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _load(args.closure_proof)
    )
    selected = m336f_selected_source_manifest_from_dict(_load(args.selected_manifest))
    selector = m336f_selector_receipt_from_dict(_load(args.selector_receipt))
    verify_m336f_selection(selected, selector, proof)
    subprocess.run(
        (
            sys.executable,
            str(repository / "scripts/m336_run_oracle_free_production.py"),
            "--source-root",
            str(args.source_root.resolve(strict=True)),
            "--output",
            str(args.output),
            "--platform",
            args.platform,
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--source-entry-bindings",
            str(args.bindings.resolve(strict=True)),
            "--selected-manifest",
            str(args.selected_manifest.resolve(strict=True)),
        ),
        cwd=repository,
        check=True,
    )
    summary = _load(args.output / "production_summary.json")
    counts = _load(args.output / "production_counts.json")
    process = _load(args.output / "production_process_audit.json")
    files = _load(args.output / "production_file_access_audit.json")
    state = _load(args.output / "production_state_audit.json")
    compiler = _load(args.output / "compiler_report.json")
    compiler_probe = java_production_compilation_probe_from_dict(
        _load(args.output / "compiler_probe.json")
    )
    expected_javac = next(
        item.javac_sha256
        for item in frozen_m336_jdk_provider_manifest().platforms
        if item.platform == args.platform
    )
    if (
        summary["status"] != "PASS"
        or summary["candidate_replay_status"] != "PASS"
        or summary["production_evaluator_dependency_count"] != 0
        or summary["production_golden_read_count"] != 0
        or counts["post_trust_pack_failures"]
        != M336F_JAVA_ACCEPTANCE_THRESHOLDS.post_trust_pack_failures
        or counts["trusted_compiler_blocked_target_count"] != 0
        or counts["trusted_header_blocking_target_count"] != 0
        or counts["trusted_enclosing_type_blocking_target_count"] != 0
        or compiler["source_unit_unbound_count"] != 0
        or compiler["malformed_output_count"] != 0
        or compiler_probe.javac_sha256 != expected_javac
        or compiler_probe.compiler_identity_hash != compiler["compiler_identity_hash"]
        or process["subprocess_invocation_count"] != 1
        or process["unexpected_subprocess_count"] != 0
        or process["socket_attempts"] != 0
        or process["os_system_attempts"] != 0
        or files["forbidden_read_count"] != 0
        or any(
            value
            for name, value in state.items()
            if name.endswith(("count", "attempts")) and isinstance(value, int)
        )
    ):
        raise ValueError("compiler-aware production isolation gate failed")
    body = {
        "schema_version": 1,
        "r21_sha": args.r21_sha,
        "qualification_mode": (
            "DEVELOPMENT_NON_AUTHORITATIVE"
            if args.development
            else "EXACT_R21_AUTHORITATIVE"
        ),
        "platform": args.platform,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "compiler_identity_hash": summary["compiler_identity_hash"],
        "compiler_probe_hash": compiler_probe.probe_hash,
        "compiler_javac_sha256": compiler_probe.javac_sha256,
        "compiler_report_hash": summary["compiler_report_hash"],
        "compiler_diagnostic_count": counts["compiler_diagnostic_count"],
        "compiler_blocked_declaration_count": counts[
            "compiler_blocked_declaration_count"
        ],
        "trusted_compiler_blocked_target_count": counts[
            "trusted_compiler_blocked_target_count"
        ],
        "trusted_header_blocking_target_count": counts[
            "trusted_header_blocking_target_count"
        ],
        "trusted_enclosing_type_blocking_target_count": counts[
            "trusted_enclosing_type_blocking_target_count"
        ],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "candidate_replay_hash": summary["candidate_replay_hash"],
        "candidate_replay_status": summary["candidate_replay_status"],
        "production_completed_before_evaluator": True,
        "production_evaluator_read_count": 0,
        "production_golden_read_count": 0,
        "production_network_access_count": 0,
        "post_trust_pack_failure_count": counts["post_trust_pack_failures"],
        "status": "PASS",
    }
    (args.output / "m336f_production_execution.json").write_text(
        canonical_json({**body, "seal_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
