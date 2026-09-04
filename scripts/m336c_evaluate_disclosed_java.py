"""Evaluate and install a sealed M-33.6c disclosed-development production."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from m336_evaluate_sealed_java import (
    _approve_and_install,
    _reconstruct_batch,
    _runtime_proof,
)

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_jdk_provider import verify_m336_jdk_provider
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.domains.loader import load_pack


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--authority-report", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--i18-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh M-33.6c evaluator output already exists")
    source_root = args.source_root.resolve(strict=True)
    production_root = args.production_root.resolve(strict=True)
    sealed_path = production_root / "production_output.json"
    if not sealed_path.is_file():
        raise ValueError("production is not sealed before evaluator creation")
    sealed_mtime = sealed_path.stat().st_mtime_ns
    replay_started = time.perf_counter()
    replay = verify_compiled_java_production_standalone(
        production_root / "candidate_pack"
    )
    replay_seconds = time.perf_counter() - replay_started
    batch = _reconstruct_batch(source_root, _load(sealed_path))
    jdk = verify_m336_jdk_provider(
        platform=args.platform, java=args.java, javac=args.javac
    )
    args.output.mkdir(parents=True)
    oracle_root = args.output / "oracle"
    project = Path(__file__).resolve().parents[1]
    tracemalloc.start()
    started = time.perf_counter()
    javac_oracle_started = time.perf_counter()
    subprocess.run(
        (
            sys.executable,
            str(project / "scripts/m343_author_semantic_goldens.py"),
            "--corpus",
            str(source_root),
            "--helper",
            str(project / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"),
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
            "m336c-independent-javac-development-evaluator",
            "--sealing-ref",
            args.i18_sha,
            "--authority-purpose",
            "post-seal-disclosed-development-evaluation",
            "--config-id",
            "m336c.disclosed-java-evaluation.v1",
            "--diagnostic-scope-v2",
        ),
        check=True,
    )
    javac_oracle_seconds = time.perf_counter() - javac_oracle_started
    goldens = load_java_golden_manifest(oracle_root / "semantic_goldens.json")
    semantic_started = time.perf_counter()
    evaluation = evaluate_sealed_java_production(_load(sealed_path), batch, goldens)
    semantic_seconds = time.perf_counter() - semantic_started
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    pack = load_pack(production_root / "candidate_pack")
    runtime = {"status": "NOT_RUN", "report_hash": content_hash("NOT_RUN")}
    approval = None
    installed = None
    runtime_seconds = 0.0
    if evaluation.passed and replay["status"] == "PASS":
        approval, installed, registry, _providers, _capabilities = _approve_and_install(
            pack, args.output
        )
        runtime_started = time.perf_counter()
        runtime = _runtime_proof(pack, installed, registry, source_root)
        runtime_seconds = time.perf_counter() - runtime_started
    authority = _load(args.authority_report.resolve(strict=True))
    modes = {
        item["family_id"]: (
            item["authority"]["source_authenticity"],
            item["authority"]["license_fusion_status"],
        )
        for item in authority
    }
    by_root = {item["value"]: item for item in evaluation.breakdowns["source_root"]}
    license_authenticity = tuple(
        {
            "source_root": root,
            "source_authenticity": mode[0],
            "license_fusion_status": mode[1],
            **by_root.get(root, {}),
        }
        for root, mode in sorted(modes.items())
    )
    production_summary = _load(production_root / "production_summary.json")
    production_counts = _load(production_root / "production_counts.json")
    summary_body = {
        "schema_version": 1,
        "platform": args.platform,
        "i18_sha": args.i18_sha,
        "production_output_hash": production_summary["production_output_hash"],
        "production_sealed_before_evaluator": sealed_mtime
        < (oracle_root / "semantic_goldens.json").stat().st_mtime_ns,
        "candidate_replay_status": replay["status"],
        "candidate_pack_compiled": True,
        "evaluation_passed": evaluation.passed,
        "runtime_status": runtime["status"],
        "proposal_count": production_counts["proposal_count"],
        "wrong_trusted_count": evaluation.wrong_trusted_count,
        "location_precision": evaluation.location.precision,
        "location_recall": evaluation.location.recall,
        "semantic_precision": evaluation.semantic.exact_semantic_precision,
        "semantic_recall": evaluation.semantic.exact_semantic_recall,
        "trust_precision": evaluation.trust.precision,
        "trust_coverage": evaluation.trust.coverage,
        "field_evidence_exactness": evaluation.field_evidence.exactness,
        "resolution_agreement": evaluation.resolution["oracle_agreement"],
        "post_trust_pack_failures": production_counts["post_trust_pack_failures"],
        "status": "PASS"
        if evaluation.passed and runtime["status"] == "PASS"
        else "FAIL",
    }
    performance = {
        "schema_version": 1,
        "platform": args.platform,
        "evaluator_seconds": f"{elapsed:.6f}",
        "p50_seconds": f"{elapsed:.6f}",
        "p95_seconds": f"{elapsed:.6f}",
        "p99_seconds": f"{elapsed:.6f}",
        "sample_count": 1,
        "throughput_targets_per_second": f"{len(goldens.goldens) / elapsed:.6f}",
        "peak_python_bytes": peak,
        "javac_oracle_seconds": f"{javac_oracle_seconds:.9f}",
        "semantic_evaluation_seconds": f"{semantic_seconds:.9f}",
        "runtime_queries_seconds": f"{runtime_seconds:.9f}",
        "replay_seconds": f"{replay_seconds:.9f}",
    }
    _write(args.output / "jdk_provider_receipt.json", asdict(jdk))
    _write(args.output / "evaluation_report.json", asdict(evaluation))
    _write(args.output / "runtime_proof.json", runtime)
    _write(args.output / "license_authenticity_breakdown.json", license_authenticity)
    _write(args.output / "evaluation_performance.json", performance)
    _write(
        args.output / "evaluation_summary.json",
        {**summary_body, "summary_hash": content_hash(summary_body)},
    )
    if approval is not None:
        _write(args.output / "development_approval.json", asdict(approval))
        _write(args.output / "installation.json", asdict(installed))


if __name__ == "__main__":
    main()
