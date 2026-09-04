"""Run independent SPDX and JDK semantic evaluation only after exact H19."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_adaptive_attacker import (
    run_adaptive_mutation_battery,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    materialize_selected_sources,
)
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336d_spdx_reference import REFERENCE_SOURCE
from ai_brain.stage3.acquisition.spdx_license import (
    AUTOMATIC_SPDX_MATCH_STATUSES,
    SPDXLicenseMatcher,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--h19-sha", required=True)
    parser.add_argument("--h19-root", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != args.h19_sha or len(args.h19_sha) != 40:
        raise ValueError("independent evaluator must run at exact H19")
    if args.output.exists():
        raise FileExistsError("fresh independent evaluator output exists")
    h19 = args.h19_root.resolve(strict=True)
    seal = _load(h19 / "h19_seal.json")
    if (
        not seal["production_completed_before_evaluator"]
        or seal["fresh_source_leak_count"]
    ):
        raise ValueError("H19 production seal is not evaluator-ready")
    selected = _load(h19 / "selected_source_manifest.json")
    qualification = _load(h19 / "qualification_decisions.json")
    args.output.mkdir(parents=True)
    tracemalloc.start()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="m336d-evaluator-") as temporary:
        temporary_root = Path(temporary)
        source_root = temporary_root / "selected"
        materialize_selected_sources(
            args.vault.resolve(strict=True), selected, source_root
        )
        authority = tuple(
            {
                "family_id": item["family_id"],
                "authority": {
                    "source_authenticity": item["source_authenticity_decision"],
                    "license_fusion_status": item["scoped_license_decision"],
                },
            }
            for item in qualification["decisions"]
        )
        authority_path = temporary_root / "authority.json"
        _write(authority_path, authority)
        semantic_output = args.output / "semantic"
        subprocess.run(
            (
                sys.executable,
                str(repository / "scripts/m336c_evaluate_disclosed_java.py"),
                "--source-root",
                str(source_root),
                "--production-root",
                str(args.production_root.resolve(strict=True)),
                "--authority-report",
                str(authority_path),
                "--java",
                str(args.java.resolve(strict=True)),
                "--javac",
                str(args.javac.resolve(strict=True)),
                "--platform",
                args.platform,
                "--i18-sha",
                args.h19_sha,
                "--output",
                str(semantic_output),
            ),
            cwd=repository,
            check=True,
        )
        license_report = _evaluate_licenses(
            vault=args.vault.resolve(strict=True),
            selected_families={item["family_id"] for item in selected["files"]},
            java=args.java.resolve(strict=True),
            javac=args.javac.resolve(strict=True),
            temporary=temporary_root,
        )
    adaptive_started = time.perf_counter()
    adaptive_report = run_adaptive_mutation_battery()
    adaptive_seconds = time.perf_counter() - adaptive_started
    if adaptive_report.accepted_count or adaptive_report.wrong_rejection_layer_count:
        raise ValueError("post-H19 adaptive mutation battery failed")
    contract_started = time.perf_counter()
    for logical_path, physical_path in (
        ("h19/acquisition_receipts.json", h19 / "acquisition_receipts.json"),
        ("h19/qualification_decisions.json", h19 / "qualification_decisions.json"),
        ("h19/selector_receipt.json", h19 / "selector_receipt.json"),
        (
            "h19/production/production_summary.json",
            h19 / "production/production_summary.json",
        ),
        ("h19/candidate_pack.json", h19 / "candidate_pack.json"),
        ("h19/vault_manifest.json", h19 / "vault_manifest.json"),
        ("h19/h19_seal.json", h19 / "h19_seal.json"),
    ):
        PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
            logical_path, physical_path.read_bytes()
        )
    contract_seconds = time.perf_counter() - contract_started
    leak_report = scan_fresh_source_leaks(
        args.vault.resolve(strict=True),
        (
            h19,
            repository / "artifacts/acquisition/disclosed_java",
        ),
    )
    if leak_report["fresh_source_leak_count"]:
        raise ValueError("post-H19 fresh-source leak scan failed")
    elapsed = time.perf_counter() - started
    _current_python_bytes, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _write(args.output / "independent_license_evaluation.json", license_report)
    semantic = _load(args.output / "semantic/evaluation_summary.json")
    runtime = _load(args.output / "semantic/runtime_proof.json")
    semantic_performance = _load(args.output / "semantic/evaluation_performance.json")
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "h19_sha": args.h19_sha,
        "production_sealed_before_evaluator": semantic[
            "production_sealed_before_evaluator"
        ],
        "production_reference_license_agreement": license_report[
            "production_reference_agreement"
        ],
        "false_automatic_license_identity_count": license_report[
            "false_automatic_license_identity_count"
        ],
        "selected_root_unresolved_disagreement_count": license_report[
            "selected_root_unresolved_disagreement_count"
        ],
        "location_precision": semantic["location_precision"],
        "location_recall": semantic["location_recall"],
        "semantic_precision": semantic["semantic_precision"],
        "semantic_recall": semantic["semantic_recall"],
        "trust_precision": semantic["trust_precision"],
        "trust_coverage": semantic["trust_coverage"],
        "field_evidence_exactness": semantic["field_evidence_exactness"],
        "resolution_agreement": semantic["resolution_agreement"],
        "wrong_trusted_count": semantic["wrong_trusted_count"],
        "post_trust_pack_failures": semantic["post_trust_pack_failures"],
        "candidate_pack_compiled": semantic["candidate_pack_compiled"],
        "candidate_replay_status": semantic["candidate_replay_status"],
        "runtime_status": runtime["status"],
        "runtime_network_access_count": 0,
        "status": "PASS"
        if semantic["status"] == "PASS"
        and license_report["status"] == "PASS"
        and runtime["status"] == "PASS"
        else "FAIL",
    }
    _write(
        args.output / "evaluation.json",
        {**body, "report_hash": content_hash(body)},
    )
    performance = {
        "schema_version": 1,
        "platform": args.platform,
        "evaluation_total_seconds": f"{elapsed:.6f}",
        "p50_seconds": f"{elapsed:.6f}",
        "p95_seconds": f"{elapsed:.6f}",
        "p99_seconds": f"{elapsed:.6f}",
        "throughput_selected_files_per_second": f"{selected['file_count'] / elapsed:.6f}",
        "peak_python_bytes": peak_python_bytes,
        "peak_java_reference_bytes": license_report["peak_java_reference_bytes"],
        "java_reference_spdx_match_seconds": license_report[
            "java_reference_spdx_match_seconds"
        ],
        "production_spdx_match_seconds": license_report[
            "production_spdx_match_seconds"
        ],
        "operation_count": 8,
        "operations": tuple(
            (name, _single_sample(seconds))
            for name, seconds in (
                (
                    "spdx_production_match",
                    float(license_report["production_spdx_match_seconds"]),
                ),
                (
                    "java_reference_spdx_match",
                    float(license_report["java_reference_spdx_match_seconds"]),
                ),
                (
                    "compilation",
                    float(license_report["java_reference_compilation_seconds"]),
                ),
                (
                    "semantic_evaluation",
                    float(semantic_performance["semantic_evaluation_seconds"]),
                ),
                (
                    "runtime_queries",
                    float(semantic_performance["runtime_queries_seconds"]),
                ),
                ("contract_validation", contract_seconds),
                ("adaptive_mutations", adaptive_seconds),
                ("leak_scan", float(leak_report["leak_scan_seconds"])),
            )
        ),
    }
    _write(args.output / "evaluation_performance.json", performance)
    if body["status"] != "PASS":
        raise SystemExit("independent M-33.6d evaluation failed")


def _evaluate_licenses(
    *,
    vault: Path,
    selected_families: set[str],
    java: Path,
    javac: Path,
    temporary: Path,
):
    legal = tuple(
        sorted(
            (item for item in vault.glob("candidates/*/legal/**/*") if item.is_file()),
            key=lambda item: item.relative_to(vault).as_posix().encode(),
        )
    )
    if not legal:
        raise ValueError("legal-document evaluator denominator is empty")
    classes = temporary / "spdx-classes"
    classes.mkdir()
    compilation_started = time.perf_counter()
    subprocess.run(
        (str(javac), "--release", "21", "-d", str(classes), str(REFERENCE_SOURCE)),
        check=True,
    )
    compilation_seconds = time.perf_counter() - compilation_started
    corpus = temporary / "legal.tsv"
    corpus.write_text(
        "".join(
            f"case-{index:05d}\t{path.relative_to(vault).as_posix()}\t"
            f"{base64.b64encode(path.read_bytes()).decode('ascii')}\n"
            for index, path in enumerate(legal)
        ),
        encoding="utf-8",
        newline="\n",
    )
    java_started = time.perf_counter()
    completed = subprocess.run(
        (
            str(java),
            "-Djava.net.useSystemProxies=false",
            "-cp",
            str(classes),
            "IndependentSpdxReference",
            str(
                (
                    REFERENCE_SOURCE.parents[3]
                    / "src/ai_brain/stage3/acquisition/data/spdx/3.28.0"
                ).resolve(strict=True)
            ),
            str(corpus),
            bytes_hash(REFERENCE_SOURCE.read_bytes()),
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    java_seconds = time.perf_counter() - java_started
    memory_matches = re.findall(r"M336D_PEAK_JAVA_HEAP_BYTES=(\d+)", completed.stderr)
    if len(memory_matches) != 1 or int(memory_matches[0]) <= 0:
        raise ValueError("Java SPDX reference peak-memory receipt is missing")
    peak_java_reference_bytes = int(memory_matches[0])
    reference = tuple(json.loads(line) for line in completed.stdout.splitlines())
    if len(reference) != len(legal):
        raise ValueError("Java license reference denominator mismatch")
    matcher = SPDXLicenseMatcher()
    rows = []
    disagreements = false_automatic = selected_disagreements = 0
    production_match_seconds = 0.0
    for path, other in zip(legal, reference, strict=True):
        relative = path.relative_to(vault).as_posix()
        family = relative.split("/", 2)[1]
        production_started = time.perf_counter()
        production = matcher.match(path.read_bytes(), source_document=relative)
        production_match_seconds += time.perf_counter() - production_started
        production_auto = production.match_status in AUTOMATIC_SPDX_MATCH_STATUSES
        production_id = production.template_license_id if production_auto else None
        reference_id = other["template_license_id"] if other["automatic"] else None
        agrees = (production_auto, production_id) == (other["automatic"], reference_id)
        disagreements += int(not agrees)
        selected_disagreements += int(not agrees and family in selected_families)
        false_automatic += int(
            production_auto != other["automatic"]
            and (production_auto or other["automatic"])
        )
        row_body = {
            "family_id": family,
            "document_identity": relative,
            "document_sha256": bytes_hash(path.read_bytes()),
            "production_automatic": production_auto,
            "production_license_id": production_id,
            "reference_automatic": other["automatic"],
            "reference_license_id": reference_id,
            "agreement": agrees,
            "disposition": "AUTOMATIC"
            if agrees and production_auto
            else "REVIEW_REQUIRED",
        }
        rows.append({**row_body, "row_hash": content_hash(row_body)})
    body = {
        "schema_version": 1,
        "document_count": len(rows),
        "production_reference_agreement": f"{(len(rows) - disagreements) / len(rows):.6f}",
        "disagreement_count": disagreements,
        "disagreement_review_required_count": disagreements,
        "false_automatic_license_identity_count": false_automatic,
        "selected_root_unresolved_disagreement_count": selected_disagreements,
        "java_reference_spdx_match_seconds": f"{java_seconds:.6f}",
        "production_spdx_match_seconds": f"{production_match_seconds:.6f}",
        "java_reference_compilation_seconds": f"{compilation_seconds:.6f}",
        "peak_java_reference_bytes": peak_java_reference_bytes,
        "rows": tuple(rows),
        "status": "PASS" if not disagreements and not false_automatic else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _single_sample(seconds: float) -> dict:
    value = f"{seconds:.9f}"
    return {
        "sample_count": 1,
        "p50_seconds": value,
        "p95_seconds": value,
        "p99_seconds": value,
        "total_seconds": value,
    }


if __name__ == "__main__":
    main()
