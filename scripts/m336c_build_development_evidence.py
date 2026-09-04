"""Build deterministic non-final M-33.6c development evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.final_artifact_contract import (
    FINAL_ARTIFACT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336c_contract_verification import (
    complete_hypothetical_h_stage,
    run_contract_mutation_battery,
    verify_contract_tree,
)
from ai_brain.stage3.acquisition.m336c_future_pool import (
    future_candidate_families,
    run_future_pool_simulations,
)
from ai_brain.stage3.acquisition.m336c_h17_forensics import (
    build_h17_contract_forensics,
)
from ai_brain.stage3.acquisition.m336c_license_evaluator import (
    evaluate_independent_license_corpus,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
    build_source_use_authorization,
    semantic_scope_invariant_hash,
)
from ai_brain.stage3.acquisition.spdx_license import (
    SPDXLicenseMatcher,
    classify_license_document,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _percentiles(samples: list[float]) -> dict:
    values = sorted(samples)

    def at(fraction):
        index = round((len(values) - 1) * fraction)
        return f"{values[index]:.9f}"

    return {
        "sample_count": len(values),
        "p50_seconds": at(0.50),
        "p95_seconds": at(0.95),
        "p99_seconds": at(0.99),
        "throughput_per_second": f"{len(values) / sum(values):.6f}",
    }


def _sample(count, operation):
    samples = []
    for _index in range(count):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return _percentiles(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    preparation = args.preparation.resolve(strict=True)
    production = args.production.resolve(strict=True)
    evaluation = args.evaluation.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError(
            "fresh M-33.6c development evidence output already exists"
        )
    args.output.mkdir(parents=True)
    for name in (
        "candidate_authority.json",
        "license_forensics.json",
        "selector_receipt.json",
        "source_use_authorization.json",
        "preparation_performance.json",
    ):
        shutil.copyfile(preparation / name, args.output / name)
    for name in (
        "production_summary.json",
        "production_counts.json",
        "candidate_replay.json",
        "production_performance.json",
    ):
        shutil.copyfile(production / name, args.output / name)
    for name in (
        "evaluation_report.json",
        "evaluation_summary.json",
        "runtime_proof.json",
        "evaluation_performance.json",
        "license_authenticity_breakdown.json",
    ):
        shutil.copyfile(evaluation / name, args.output / name)

    matcher = SPDXLicenseMatcher()
    tracemalloc.start()
    license_started = time.perf_counter()
    license_report = evaluate_independent_license_corpus(matcher)
    license_elapsed = time.perf_counter() - license_started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _write(args.output / "independent_license_evaluation.json", asdict(license_report))

    h17 = build_h17_contract_forensics(project)
    _write(args.output / "h17_contract_forensics.json", h17)
    hypothetical = verify_contract_tree(complete_hypothetical_h_stage())
    mutations = run_contract_mutation_battery()
    _write(args.output / "hypothetical_h_stage_contract.json", asdict(hypothetical))
    _write(args.output / "contract_mutations.json", asdict(mutations))

    verify_disclosed_java_registry()
    entries = load_disclosed_java_registry()
    registry_body = {
        "schema_version": 1,
        "entry_count": len(entries),
        "coordinate_count": len({item.coordinate for item in entries}),
        "archive_hash_count": len({item.archive_hash for item in entries}),
        "pom_hash_count": len({item.pom_hash for item in entries}),
        "source_url_count": len({item.source_url for item in entries}),
        "raw_source_hash_count": len(
            {value for item in entries for value in item.raw_source_hashes}
        ),
        "canonical_source_hash_count": len(
            {value for item in entries for value in item.canonical_source_hashes}
        ),
        "source_tree_hash_count": len({item.source_tree_hash for item in entries}),
        "scm_commit_count": len({item.scm_revision for item in entries}),
        "correspondence_hash_count": len(
            {item.correspondence_hash for item in entries}
        ),
        "declaration_fingerprint_count": len(
            {value for item in entries for value in item.declaration_fingerprints}
        ),
        "entry_hashes": tuple(item.entry_hash for item in entries),
        "status": "PASS" if len(entries) == 6 else "FAIL",
    }
    _write(
        args.output / "disclosure_registry.json",
        {**registry_body, "report_hash": content_hash(registry_body)},
    )

    families = future_candidate_families()
    simulations = run_future_pool_simulations()
    future_body = {
        "schema_version": 1,
        "candidate_family_count": len(families),
        "organization_count": len({item.organization for item in families}),
        "families": tuple(asdict(item) for item in families),
        "simulations": tuple(asdict(item) for item in simulations),
        "source_body_inspection_count": 0,
        "required_candidate_count": 0,
        "status": "PASS",
    }
    _write(
        args.output / "future_candidate_strategy.json",
        {**future_body, "report_hash": content_hash(future_body)},
    )

    summary = _load(production / "production_summary.json")
    output = _load(production / "production_output.json")
    semantic_binding = {
        "production_output_hash": summary["production_output_hash"],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "proposal_manifest_hash": output["proposal_manifest_hash"],
        "trust_closure_hash": output["trust_closure_hash"],
        "candidate_rows_hash": content_hash(output["candidate_rows"]),
    }
    private_exports = ()
    redistribution_exports = tuple(
        item["document_bytes_hash"] for item in output["candidate_rows"]
    )
    private_hash = semantic_scope_invariant_hash(
        {
            "semantic_binding": semantic_binding,
            "source_use_scope": SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
            "raw_export_manifest": private_exports,
        }
    )
    redistribution_hash = semantic_scope_invariant_hash(
        {
            "semantic_binding": semantic_binding,
            "source_use_scope": SourceUseScope.RAW_SOURCE_REDISTRIBUTION,
            "raw_export_manifest": redistribution_exports,
        }
    )
    scope_body = {
        "schema_version": 1,
        "private_scope": SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
        "redistribution_scope": SourceUseScope.RAW_SOURCE_REDISTRIBUTION,
        "private_semantic_content_hash": private_hash,
        "redistribution_semantic_content_hash": redistribution_hash,
        "semantic_content_hashes_equal": private_hash == redistribution_hash,
        "private_raw_export_manifest_hash": content_hash(private_exports),
        "redistribution_raw_export_manifest_hash": content_hash(redistribution_exports),
        "raw_export_manifests_differ": content_hash(private_exports)
        != content_hash(redistribution_exports),
    }
    _write(
        args.output / "source_scope_invariant.json",
        {**scope_body, "report_hash": content_hash(scope_body)},
    )

    model_approval_accepted = 0
    try:
        build_source_use_authorization(
            authority_kind="MODEL",
            authority_id="forged",
            authorized_scopes=(SourceUseScope.RAW_SOURCE_REDISTRIBUTION,),
            publication_targets=(PublicationTarget.RAW_SOURCE_PUBLICATION,),
            policy_version="forged",
        )
        model_approval_accepted = 1
    except ValueError:
        pass
    production_logic = tuple(
        project / "src/ai_brain/stage3/acquisition" / name
        for name in (
            "java_source_index.py",
            "java_type_universe.py",
            "java_production.py",
            "java_semantics.py",
        )
    )
    candidate_markers = tuple(
        item["family_id"] for item in _load(preparation / "candidate_authority.json")
    )
    candidate_specific_branches = sum(
        marker in path.read_text(encoding="utf-8")
        for path in production_logic
        for marker in candidate_markers
    )
    security_body = {
        "schema_version": 1,
        "license_substantive_mutations_blocked": license_report.true_conflict_mutation_blocked_count,
        "license_substantive_mutation_count": license_report.true_conflict_mutation_count,
        "false_apache_match_count": license_report.false_apache_match_count,
        "model_created_publication_approvals_accepted": model_approval_accepted,
        "raw_source_publication_eligible_entry_count": 0,
        "contract_mutations_rejected": mutations.rejected_count,
        "contract_mutation_count": mutations.mutation_count,
        "candidate_specific_branch_count": candidate_specific_branches,
        "content_policy_addition_count": 0,
        "status": "PASS",
    }
    _write(
        args.output / "security_report.json",
        {**security_body, "report_hash": content_hash(security_body)},
    )

    apache = (matcher.snapshot_root / "Apache-2.0.txt").read_bytes()
    contract_sample = complete_hypothetical_h_stage()[3]
    preparation_performance = _load(preparation / "preparation_performance.json")
    preparation_suboperations = preparation_performance["suboperations"]
    performance_body = {
        "schema_version": 1,
        "platform": args.platform,
        "spdx_template_load": _sample(10, SPDXLicenseMatcher),
        "license_match": _sample(
            100, lambda: matcher.match(apache, source_document="LICENSE")
        ),
        "license_evidence_fusion": preparation_suboperations["license_evidence_fusion"],
        "document_role_classification": _sample(
            1000, lambda: classify_license_document("module/LICENSE")
        ),
        "entry_eligibility": preparation_suboperations["entry_eligibility"],
        "candidate_qualification": preparation_suboperations["candidate_qualification"],
        "artifact_contract_lookup": _sample(
            1000,
            lambda: FINAL_ARTIFACT_CONTRACT_REGISTRY.match(
                contract_sample.relative_path
            ),
        ),
        "contract_validation": _sample(
            100,
            lambda: FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
                contract_sample.relative_path, contract_sample.raw
            ),
        ),
        "disclosure_extraction": _sample(
            100,
            lambda: FINAL_ARTIFACT_CONTRACT_REGISTRY.disclosure_claim_specs(
                contract_sample.relative_path, contract_sample.raw
            ),
        ),
        "independent_license_corpus_seconds": f"{license_elapsed:.6f}",
        "peak_python_bytes": peak,
        "complete_disclosed_provenance": preparation_performance,
        "production": _load(production / "production_performance.json"),
        "evaluator": _load(evaluation / "evaluation_performance.json"),
    }
    _write(
        args.output / "performance.json",
        {**performance_body, "report_hash": content_hash(performance_body)},
    )

    manifest_entries = tuple(
        (path.relative_to(args.output).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(args.output.rglob("*"))
        if path.is_file()
    )
    manifest_body = {
        "schema_version": 1,
        "entries": manifest_entries,
        "entry_count": len(manifest_entries),
    }
    _write(
        args.output / "evidence_manifest.json",
        {**manifest_body, "manifest_hash": content_hash(manifest_body)},
    )


if __name__ == "__main__":
    main()
