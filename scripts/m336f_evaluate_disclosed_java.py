"""Evaluate one sealed M-33.6f compiler-aware Java production independently."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from m336_evaluate_sealed_java import (
    _approve_and_install,
    _reconstruct_batch,
    _runtime_proof,
)
from m336d_evaluate_final import _evaluate_licenses

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_jdk_provider import (
    frozen_m336_jdk_provider_manifest,
    verify_m336_jdk_provider,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    java_production_compilation_probe_from_dict,
    java_production_compiler_report_from_dict,
)
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_contracts import (
    run_m336f_producer_contract_gate,
)
from ai_brain.stage3.acquisition.m336f_evaluation_artifacts import (
    build_m336f_evaluation_telemetry_receipt,
    build_m336f_semantic_evaluation_artifact,
)
from ai_brain.stage3.acquisition.m336f_field_evidence import (
    build_java_field_evidence_conformance_report,
)
from ai_brain.stage3.acquisition.m336f_license_evaluation import (
    split_m336f_license_evaluation,
)
from ai_brain.stage3.acquisition.m336f_thresholds import (
    M336F_JAVA_ACCEPTANCE_THRESHOLDS,
    build_m336f_trust_metrics,
    ratio_meets_threshold,
    ratio_string,
)
from ai_brain.stage3.acquisition.m336f_trust_opportunities import (
    build_trust_coverage_opportunity_report,
)
from ai_brain.stage3.domains.loader import load_pack


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


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
        raise ValueError("evaluation requires a clean exact-R21 worktree")


def _verify_production_seals(args) -> None:
    if args.development and (
        args.windows_production_root is None or args.karina_production_root is None
    ):
        return
    if args.windows_production_root is None or args.karina_production_root is None:
        raise ValueError("authoritative evaluation requires both production seals")
    expected_platform_root = {
        "windows": args.windows_production_root,
        "karina": args.karina_production_root,
    }[args.platform].resolve(strict=True)
    if args.production_root.resolve(strict=True) != expected_platform_root:
        raise ValueError("evaluation production root does not match its platform seal")
    values = []
    for platform, root in (
        ("windows", args.windows_production_root),
        ("karina", args.karina_production_root),
    ):
        root = root.resolve(strict=True)
        execution = _load(root / "m336f_production_execution.json")
        execution_body = dict(execution)
        execution_hash = execution_body.pop("seal_hash", None)
        summary = _load(root / "production_summary.json")
        summary_body = dict(summary)
        summary_hash = summary_body.pop("summary_hash", None)
        production = _load(root / "production_output.json")
        production_body = dict(production)
        production_hash = production_body.pop("production_output_hash", None)
        counts = _load(root / "production_counts.json")
        compiler = java_production_compiler_report_from_dict(
            _load(root / "compiler_report.json")
        )
        probe = java_production_compilation_probe_from_dict(
            _load(root / "compiler_probe.json")
        )
        expected_javac = next(
            item.javac_sha256
            for item in frozen_m336_jdk_provider_manifest().platforms
            if item.platform == platform
        )
        replay = verify_compiled_java_production_standalone(root / "candidate_pack")
        if (
            execution_hash is None
            or content_hash(execution_body) != execution_hash
            or summary_hash is None
            or content_hash(summary_body) != summary_hash
            or production_hash is None
            or content_hash(production_body) != production_hash
            or execution["r21_sha"] != args.r21_sha
            or execution["platform"] != platform
            or execution["status"] != "PASS"
            or execution["production_completed_before_evaluator"] is not True
            or execution["production_output_hash"] != production_hash
            or execution["production_output_hash"] != summary["production_output_hash"]
            or execution["production_batch_hash"] != summary["production_batch_hash"]
            or execution["compiler_identity_hash"] != compiler.compiler_identity_hash
            or execution["compiler_identity_hash"] != probe.compiler_identity_hash
            or execution["compiler_probe_hash"] != probe.probe_hash
            or execution["compiler_probe_hash"] != summary["compiler_probe_hash"]
            or execution["compiler_javac_sha256"] != probe.javac_sha256
            or probe.javac_sha256 != expected_javac
            or execution["compiler_report_hash"] != compiler.report_hash
            or execution["compiler_report_hash"] != summary["compiler_report_hash"]
            or execution["compiler_diagnostic_count"]
            != counts["compiler_diagnostic_count"]
            or execution["compiler_diagnostic_count"] != compiler.diagnostic_count
            or execution["compiler_blocked_declaration_count"]
            != counts["compiler_blocked_declaration_count"]
            or execution["trusted_compiler_blocked_target_count"]
            != counts["trusted_compiler_blocked_target_count"]
            or execution["trusted_header_blocking_target_count"]
            != counts["trusted_header_blocking_target_count"]
            or execution["trusted_enclosing_type_blocking_target_count"]
            != counts["trusted_enclosing_type_blocking_target_count"]
            or execution["candidate_pack_hash"] != summary["candidate_pack_hash"]
            or execution["candidate_replay_hash"] != replay["artifact_hash"]
            or execution["candidate_replay_hash"] != summary["candidate_replay_hash"]
            or execution["candidate_replay_status"] != replay["status"]
            or execution["candidate_replay_status"]
            != summary["candidate_replay_status"]
            or execution["post_trust_pack_failure_count"]
            != counts["post_trust_pack_failures"]
            or execution["post_trust_pack_failure_count"]
            != M336F_JAVA_ACCEPTANCE_THRESHOLDS.post_trust_pack_failures
            or any(
                execution[name] != 0
                for name in (
                    "production_evaluator_read_count",
                    "production_golden_read_count",
                    "production_network_access_count",
                    "trusted_compiler_blocked_target_count",
                    "trusted_header_blocking_target_count",
                    "trusted_enclosing_type_blocking_target_count",
                )
            )
            or (
                not args.development
                and execution["qualification_mode"] != "EXACT_R21_AUTHORITATIVE"
            )
        ):
            raise ValueError("production seal is not eligible for evaluation")
        values.append(execution)
    neutral = (
        "selected_manifest_hash",
        "selector_receipt_hash",
        "production_output_hash",
        "production_batch_hash",
        "compiler_identity_hash",
        "compiler_report_hash",
        "compiler_diagnostic_count",
        "compiler_blocked_declaration_count",
        "trusted_compiler_blocked_target_count",
        "trusted_header_blocking_target_count",
        "trusted_enclosing_type_blocking_target_count",
        "candidate_pack_hash",
        "candidate_replay_hash",
        "candidate_replay_status",
        "post_trust_pack_failure_count",
    )
    if any(values[0][name] != values[1][name] for name in neutral):
        raise ValueError("platform-neutral production seals differ before evaluation")


def _verify_selected_authority(authority: dict, selected_roots: set[str]) -> dict:
    rows = authority.get("candidates")
    if not isinstance(rows, list):
        raise TypeError("authority report has no candidate decisions")
    eligible = {
        item["family_id"]
        for item in rows
        if item.get("analysis_eligible") is True
        and item.get("authority_receipt_valid") is True
    }
    missing = selected_roots - eligible
    body = {
        "schema_version": 1,
        "selected_root_count": len(selected_roots),
        "eligible_selected_root_count": len(selected_roots - missing),
        "ineligible_selected_root_count": len(missing),
        "authority_report_hash": authority.get("report_hash"),
        "status": "PASS" if not missing else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _root_holdout_report(evaluation) -> dict:
    rows = []
    for item in evaluation.breakdowns["source_root"]:
        trusted = item["trusted_count"]
        correct = item["correct_trusted_count"]
        precision = ratio_string(correct, trusted)
        body = {
            "source_root_identity_hash": content_hash(("SOURCE_ROOT", item["value"])),
            "expected_supported_count": item["expected_supported_count"],
            "trusted_count": trusted,
            "correct_trusted_count": correct,
            "wrong_trusted_count": item["wrong_trusted_count"],
            "trust_precision": precision,
            "status": (
                "PASS"
                if trusted > 0
                and item["wrong_trusted_count"]
                == M336F_JAVA_ACCEPTANCE_THRESHOLDS.wrong_trusted
                and ratio_meets_threshold(
                    correct,
                    trusted,
                    M336F_JAVA_ACCEPTANCE_THRESHOLDS.trust_precision,
                )
                else "FAIL"
            ),
        }
        rows.append({**body, "row_hash": content_hash(body)})
    report_body = {
        "schema_version": 1,
        "holdout_root_count": len(rows),
        "rows": tuple(rows),
        "status": (
            "PASS"
            if len(rows) >= 5 and all(item["status"] == "PASS" for item in rows)
            else "FAIL"
        ),
    }
    return {**report_body, "report_hash": content_hash(report_body)}


def _diagnostic_correspondence(production: dict, goldens, sealed: dict) -> dict:
    production_rows = Counter(
        (
            item["source_unit_id"],
            item["line"],
            item["column"],
            item["normalized_category"],
        )
        for item in production["diagnostics"]
    )
    evaluator_rows = Counter(
        (item.source_unit_id, item.line, item.column, item.normalized_category)
        for item in goldens.diagnostics
    )
    matched = production_rows & evaluator_rows
    production_only = production_rows - evaluator_rows
    evaluator_only = evaluator_rows - production_rows
    trusted_locations = {
        (
            item["document_bytes_hash"],
            item["source_unit_id"],
            item["start_offset"],
            item["end_offset"],
        )
        for item in sealed["candidate_rows"]
        if item["production_trust_state"] == "trusted"
    }
    trusted_target_ids = {
        item.expected_semantics.target_id
        for item in goldens.goldens
        if item.expected_semantics is not None
        and (
            item.document_bytes_hash,
            item.source_unit_id,
            item.start_offset,
            item.end_offset,
        )
        in trusted_locations
    }
    evaluator_only_keys = set(evaluator_only)
    evaluator_only_blocking_trusted = sum(
        item.trust_relevant
        and bool(set(item.target_ids) & trusted_target_ids)
        and (
            item.source_unit_id,
            item.line,
            item.column,
            item.normalized_category,
        )
        in evaluator_only_keys
        for item in goldens.diagnostics
    )
    body = {
        "schema_version": 1,
        "production_compiler_report_hash": production["report_hash"],
        "evaluator_diagnostic_manifest_hash": goldens.diagnostic_manifest_hash,
        "production_diagnostic_count": sum(production_rows.values()),
        "evaluator_diagnostic_count": sum(evaluator_rows.values()),
        "matched_diagnostic_count": sum(matched.values()),
        "production_only_diagnostic_count": sum(production_only.values()),
        "evaluator_only_diagnostic_count": sum(evaluator_only.values()),
        "evaluator_only_blocking_trusted_count": evaluator_only_blocking_trusted,
        "production_unknown_scope_count": production["unknown_scope_count"],
        "production_unmapped_diagnostic_count": production["unmapped_diagnostic_count"],
        "production_source_unit_unbound_count": production["source_unit_unbound_count"],
        "production_malformed_output_count": production["malformed_output_count"],
        "production_scope_counts": tuple(
            sorted(
                Counter(
                    item["diagnostic_scope"] for item in production["bindings"]
                ).items()
            )
        ),
        "production_category_counts": tuple(
            sorted(
                Counter(
                    item["normalized_category"] for item in production["diagnostics"]
                ).items()
            )
        ),
        "evaluator_category_counts": tuple(sorted(goldens.diagnostic_counts)),
    }
    return {**body, "report_hash": content_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--windows-production-root", type=Path)
    parser.add_argument("--karina-production-root", type=Path)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--authority-report", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--r21-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--development",
        action="store_true",
        help="allow a dirty pre-R21 worktree and mark output non-authoritative",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh M-33.6f evaluator output already exists")
    repository = args.repository.resolve(strict=True)
    if not args.development:
        _require_clean_exact(repository, args.r21_sha)
    _verify_production_seals(args)
    source_root = args.source_root.resolve(strict=True)
    production_root = args.production_root.resolve(strict=True)
    sealed_path = production_root / "production_output.json"
    sealed = _load(sealed_path)
    bindings = source_entry_binding_manifest_from_dict(_load(args.bindings))
    available = {
        item.relative_to(source_root).as_posix()
        for item in source_root.rglob("*.java")
        if item.is_file()
    }
    source_entry_ids = {
        item.selected_path: item.source_entry_id.identity_hash
        for item in bindings.bindings
        if item.selected_path in available
    }
    if set(source_entry_ids) != available:
        raise ValueError(
            "evaluator SourceEntryId binding does not close selected source"
        )
    selected_roots = {item.partition("/")[0] for item in available}
    authority = _verify_selected_authority(_load(args.authority_report), selected_roots)
    if authority["status"] != "PASS":
        raise ValueError("selected source does not have closed authority")
    replay_started = time.perf_counter()
    replay = verify_compiled_java_production_standalone(
        production_root / "candidate_pack"
    )
    replay_seconds = time.perf_counter() - replay_started
    reconstruct_started = time.perf_counter()
    batch = _reconstruct_batch(
        source_root,
        sealed,
        javac=args.javac.resolve(strict=True),
        source_entry_ids=source_entry_ids,
    )
    reconstruct_seconds = time.perf_counter() - reconstruct_started
    jdk = verify_m336_jdk_provider(
        platform=args.platform,
        java=args.java,
        javac=args.javac,
    )
    args.output.mkdir(parents=True)
    oracle_root = args.output / "oracle"
    tracemalloc.start()
    license_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="m336f-disclosed-spdx-") as temporary:
        mixed_license = _evaluate_licenses(
            vault=args.vault.resolve(strict=True),
            selected_families=selected_roots,
            java=args.java.resolve(strict=True),
            javac=args.javac.resolve(strict=True),
            temporary=Path(temporary),
        )
    license_seconds = time.perf_counter() - license_started
    license_split = split_m336f_license_evaluation(mixed_license)
    license_semantic = license_split.semantic
    oracle_started = time.perf_counter()
    subprocess.run(
        (
            sys.executable,
            str(repository / "scripts/m343_author_semantic_goldens.py"),
            "--corpus",
            str(source_root),
            "--helper",
            str(repository / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"),
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--java",
            str(args.java.resolve(strict=True)),
            "--output",
            str(oracle_root),
            "--parser-common-hash",
            batch.parser_common_artifact.manifest_hash,
            "--evidence-policy-hash",
            batch.evidence_policy.manifest_hash,
            "--authority-id",
            "m336f-independent-javac-disclosed-evaluator",
            "--sealing-ref",
            args.r21_sha,
            "--authority-purpose",
            "post-seal-disclosed-evaluation",
            "--config-id",
            "m336f.disclosed-java-evaluation.v1",
            "--diagnostic-scope-v2",
        ),
        cwd=repository,
        check=True,
    )
    oracle_seconds = time.perf_counter() - oracle_started
    goldens = load_java_golden_manifest(oracle_root / "semantic_goldens.json")
    semantic_started = time.perf_counter()
    evaluation = evaluate_sealed_java_production(sealed, batch, goldens)
    field_report = build_java_field_evidence_conformance_report(batch, goldens)
    semantic_seconds = time.perf_counter() - semantic_started
    compiler = _load(production_root / "compiler_report.json")
    correspondence = _diagnostic_correspondence(compiler, goldens, sealed)
    root_holdouts = _root_holdout_report(evaluation)
    opportunities = (
        build_trust_coverage_opportunity_report(sealed, goldens)
        if args.development
        else None
    )
    contracts_started = time.perf_counter()
    contracts = run_m336f_producer_contract_gate(
        _load(repository / "evaluation/m336d_final_java/h19/acquisition_receipts.json")
    )
    contracts_seconds = time.perf_counter() - contracts_started
    trust = build_m336f_trust_metrics(
        actual_trusted=evaluation.trust.correct_trusted
        + evaluation.trust.wrong_trusted,
        expected_trusted=evaluation.trust.correct_trusted
        + evaluation.trust.incorrect_withheld,
        correct_trusted=evaluation.trust.correct_trusted,
        wrong_trusted=evaluation.trust.wrong_trusted,
        correct_withheld=evaluation.trust.correct_withheld,
        incorrect_withheld=evaluation.trust.incorrect_withheld,
    )
    production_summary = _load(production_root / "production_summary.json")
    production_execution = _load(production_root / "m336f_production_execution.json")
    production_counts = _load(production_root / "production_counts.json")
    pack = load_pack(production_root / "candidate_pack")
    runtime = {"status": "NOT_RUN", "report_hash": content_hash("NOT_RUN")}
    approval = installed = None
    runtime_seconds = 0.0
    thresholds = M336F_JAVA_ACCEPTANCE_THRESHOLDS
    field_pass = (
        field_report.missing_count
        == field_report.extra_count
        == field_report.duplicate_count
        == field_report.wrong_count
        == 0
        and ratio_meets_threshold(
            field_report.exact_count,
            field_report.present_count,
            thresholds.field_evidence_exactness,
        )
    )
    safe_coverage_pass = ratio_meets_threshold(
        trust.correct_trusted,
        trust.expected_trusted,
        thresholds.safe_trust_coverage,
    )
    semantic_pass = (
        evaluation.passed
        and field_pass
        and safe_coverage_pass
        and correspondence["evaluator_only_blocking_trusted_count"] == 0
        and root_holdouts["status"] == "PASS"
        and license_semantic["status"] == "PASS"
        and contracts.status == "PASS"
        and compiler["source_unit_unbound_count"] == 0
        and compiler["malformed_output_count"] == 0
        and replay["status"] == "PASS"
        and production_counts["post_trust_pack_failures"]
        == thresholds.post_trust_pack_failures
    )
    if semantic_pass:
        approval, installed, registry, _providers, _capabilities = _approve_and_install(
            pack, args.output
        )
        runtime_started = time.perf_counter()
        runtime = _runtime_proof(pack, installed, registry, source_root)
        runtime_seconds = time.perf_counter() - runtime_started
    readiness = "PASS" if semantic_pass and runtime["status"] == "PASS" else "FAIL"
    semantic_artifact = build_m336f_semantic_evaluation_artifact(
        identities={
            "field_evidence_specification": field_report.specification_version,
            "r21_sha": args.r21_sha,
            "semantic_contract": "m336f.semantic-evaluation.v1",
        },
        counts={
            "actual_trusted": trust.actual_trusted,
            "correct_trusted": trust.correct_trusted,
            "correct_withheld": trust.correct_withheld,
            "evaluator_only_blocking_trusted": correspondence[
                "evaluator_only_blocking_trusted_count"
            ],
            "field_duplicate": field_report.duplicate_count,
            "field_extra": field_report.extra_count,
            "field_missing": field_report.missing_count,
            "field_wrong": field_report.wrong_count,
            "incorrect_withheld": trust.incorrect_withheld,
            "license_disagreements": license_semantic["disagreement_count"],
            "license_false_automatic_identities": license_semantic[
                "false_automatic_license_identity_count"
            ],
            "post_trust_pack_failures": production_counts["post_trust_pack_failures"],
            "producer_contract_failures": (
                contracts.uncontracted_produced_artifact_count
                + contracts.contract_type_without_producer_or_legacy_count
                + contracts.ambiguous_path_contract_count
            ),
            "trusted_compiler_blocked_targets": production_counts[
                "trusted_compiler_blocked_target_count"
            ],
            "trusted_enclosing_type_blocking_targets": production_counts[
                "trusted_enclosing_type_blocking_target_count"
            ],
            "trusted_header_blocking_targets": production_counts[
                "trusted_header_blocking_target_count"
            ],
            "wrong_trusted": trust.wrong_trusted,
        },
        ratios={
            "field_evidence_exactness": field_report.exactness,
            "legacy_trust_coverage": trust.legacy_trust_coverage,
            "location_precision": evaluation.location.precision,
            "location_recall": evaluation.location.recall,
            "resolution_agreement": evaluation.resolution["oracle_agreement"],
            "safe_trust_coverage": trust.safe_trust_coverage,
            "semantic_precision": evaluation.semantic.exact_semantic_precision,
            "semantic_recall": evaluation.semantic.exact_semantic_recall,
            "spdx_agreement": license_semantic["production_reference_agreement"],
            "trust_precision": trust.trust_precision,
            "trust_recall": trust.trust_recall,
        },
        decisions={
            "candidate_replay": replay["status"],
            "evaluation": "PASS" if semantic_pass else "FAIL",
            "producer_contracts": contracts.status,
            "root_holdouts": root_holdouts["status"],
            "runtime": runtime["status"],
        },
        hashes={
            "candidate_pack": production_summary["candidate_pack_hash"],
            "compiler_identity": production_summary["compiler_identity_hash"],
            "compiler_report": compiler["report_hash"],
            "golden_manifest": goldens.manifest_hash,
            "independent_license": license_semantic["report_hash"],
            "production_output": production_summary["production_output_hash"],
            "producer_contract_gate": contracts.report_hash,
            "selected_manifest": production_execution["selected_manifest_hash"],
            "selected_authority": authority["report_hash"],
            "selector_receipt": production_execution["selector_receipt_hash"],
            "threshold_manifest": M336F_JAVA_ACCEPTANCE_THRESHOLDS.manifest_hash,
        },
        normalized_diagnostic_categories=dict(
            correspondence["production_category_counts"]
        ),
        mismatch_manifest_hashes={
            "diagnostic_correspondence": correspondence["report_hash"],
            "field_evidence": field_report.report_hash,
            "root_holdouts": root_holdouts["report_hash"],
            "semantic": evaluation.semantic.matrix_hash,
        },
        readiness_result=readiness,
    )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    telemetry = build_m336f_evaluation_telemetry_receipt(
        platform=args.platform,
        host_identity_hash=content_hash(
            (
                args.platform,
                os.environ.get("COMPUTERNAME")
                or os.environ.get("HOSTNAME")
                or "unknown",
            )
        ),
        operation_timings_seconds={
            "contracts": f"{contracts_seconds:.9f}",
            "license": f"{license_seconds:.9f}",
            "oracle": f"{oracle_seconds:.9f}",
            "reconstruction": f"{reconstruct_seconds:.9f}",
            "replay": f"{replay_seconds:.9f}",
            "runtime": f"{runtime_seconds:.9f}",
            "semantic": f"{semantic_seconds:.9f}",
            **dict(license_split.telemetry_timings_seconds),
        },
        peak_memory_bytes=peak,
        jdk_executable_hash=bytes_hash(args.javac.resolve(strict=True).read_bytes()),
        process_measurements={
            "compiler_invocations": 3,
            "license_reference_peak_memory_bytes": (
                license_split.peak_java_reference_bytes
            ),
            "oracle_invocations": 1,
            "runtime_network_accesses": 0,
        },
    )
    _write(args.output / "jdk_provider_receipt.json", asdict(jdk))
    _write(args.output / "evaluation_report.json", asdict(evaluation))
    _write(args.output / "field_evidence_conformance.json", asdict(field_report))
    _write(args.output / "diagnostic_correspondence.json", correspondence)
    _write(args.output / "root_holdout_trust.json", root_holdouts)
    if opportunities is not None:
        _write(args.output / "trust_coverage_opportunities.json", asdict(opportunities))
    _write(args.output / "selected_authority_validation.json", authority)
    _write(args.output / "independent_license_evaluation.json", license_semantic)
    _write(args.output / "producer_contract_compatibility.json", asdict(contracts))
    _write(args.output / "runtime_proof.json", runtime)
    _write(args.output / "semantic_evaluation.json", asdict(semantic_artifact))
    _write(args.output / "evaluation_telemetry.json", asdict(telemetry))
    if approval is not None:
        _write(args.output / "development_approval.json", asdict(approval))
        _write(args.output / "installation.json", asdict(installed))
    if readiness != "PASS":
        raise SystemExit("M-33.6f disclosed independent evaluation failed")


if __name__ == "__main__":
    main()
