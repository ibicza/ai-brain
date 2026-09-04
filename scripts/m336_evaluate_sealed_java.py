"""Evaluate an immutable M-33.6 production result, then conditionally install it."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections import defaultdict
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.evaluation import verify_pack_evaluation
from ai_brain.stage3.acquisition.java_final_gate import (
    M336FinalOutcome,
    evaluate_m336_final_gate,
)
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_jdk_provider import verify_m336_jdk_provider
from ai_brain.stage3.acquisition.java_process_audit import EnforcedProcessAudit
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
)
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_replay_mutations import (
    run_m336_replay_mutation_battery,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.aliases import AliasLookupStatus
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.loader import load_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry

STAMP = "1970-01-01T00:00:00Z"
RUN_ID = "m336.untouched-final-java.production.v1"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _percentiles(samples: list[float]) -> dict:
    ordered = sorted(samples)

    def value(percentile: float) -> str:
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
        return f"{ordered[index]:.9f}"

    return {
        "sample_count": len(ordered),
        "p50_seconds": value(0.50),
        "p95_seconds": value(0.95),
        "p99_seconds": value(0.99),
    }


def _reconstruct_batch(source_root: Path, sealed: dict):
    sources = tuple(
        sorted(
            source_root.rglob("*.java"),
            key=lambda item: item.relative_to(source_root).as_posix().encode("utf-8"),
        )
    )
    with tempfile.TemporaryDirectory(prefix="m336-sealed-reconstruction-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        bundle = ingest_bundle(
            sources,
            bundle_id="m336-final-java",
            domain_tags=("java-api",),
            imported_at=STAMP,
            store=store,
            source_root=source_root,
        )
        batch = run_java_acquisition_pipeline(
            bundle, store, deterministic_run_id=RUN_ID
        )
    if canonical_json(seal_java_production_output(batch)) != canonical_json(sealed):
        raise ValueError("reconstructed batch differs from sealed production output")
    return batch


def _approve_and_install(pack, output: Path):
    validation = validate_pack(pack)
    verify_pack_evaluation(pack)
    provider_registry = ProviderRegistry.build(output / "providers", ())
    capability_registry = CapabilityRegistry.build((), provider_registry)
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=(),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m336-exact-release-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m336.oracle-free-java-release.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        output / "installed_pack",
        capability_registry=capability_registry,
        provider_registry=provider_registry,
        created_at=STAMP,
    )
    installed = registry.install(pack, approval, (), installed_at=STAMP)
    registry.verify(require_current_authority=True)
    return approval, installed, registry, provider_registry, capability_registry


def _runtime_proof(pack, installed, registry, source_root: Path) -> dict:
    loaded = registry.load_installed_pack(installed.domain_id, installed.pack_version)
    runtime = GenericDomainRuntime(loaded, installed_registry=registry)
    exact_candidates = defaultdict(list)
    for item in loaded.alias_semantics.exact_references:
        exact_candidates[item.record_id].append(item.reference)
    exact_by_record = {
        record_id: next(
            reference for reference in references if reference.startswith("java:")
        )
        for record_id, references in exact_candidates.items()
    }
    records = {item.knowledge_id: item for item in loaded.knowledge_records}
    queries = []

    def exact_case(name: str, predicate) -> None:
        record = next((item for item in records.values() if predicate(item)), None)
        if record is None or record.knowledge_id not in exact_by_record:
            queries.append(
                {"query_class": name, "status": "NOT_MEASURED", "passed": False}
            )
            return
        reference = exact_by_record[record.knowledge_id]
        result = runtime.resolve_knowledge_alias(reference)
        queries.append(
            {
                "query_class": name,
                "query": reference,
                "status": result.status.value,
                "record_count": len(result.record_ids),
                "passed": result.status is AliasLookupStatus.EXACT
                and result.record_ids == (record.knowledge_id,),
            }
        )

    exact_case("exact_scoped_descriptor", lambda _item: True)
    parameter_record = next(
        (item for item in records.values() if item.content.resolved_parameter_types),
        None,
    )
    if parameter_record is None:
        queries.append(
            {
                "query_class": "receiver_method_exact_parameter_types",
                "status": "NOT_MEASURED",
                "passed": False,
            }
        )
    else:
        content = parameter_record.content
        parameter_query = (
            f"{content.receiver_type}.{content.predicate_id}"
            f"({','.join(content.resolved_parameter_types)})"
        )
        result = runtime.resolve_knowledge_alias(parameter_query)
        queries.append(
            {
                "query_class": "receiver_method_exact_parameter_types",
                "query": parameter_query,
                "status": result.status.value,
                "record_count": len(result.record_ids),
                "passed": result.status is AliasLookupStatus.EXACT
                and result.record_ids == (parameter_record.knowledge_id,),
            }
        )
    constructor_receivers = defaultdict(int)
    for item in records.values():
        if item.content.predicate_id == "<init>":
            constructor_receivers[item.content.receiver_type] += 1
    exact_case(
        "constructor_overload",
        lambda item: (
            item.content.predicate_id == "<init>"
            and constructor_receivers[item.content.receiver_type] > 1
        ),
    )
    exact_case("generic_method", lambda item: bool(item.content.method_type_parameters))
    exact_case(
        "throws_declaration", lambda item: bool(item.content.declared_exceptions)
    )
    exact_case(
        "nested_receiver", lambda item: "$" in item.content.subject_type.entity_type_id
    )
    deprecated = next(
        (
            item
            for item in records.values()
            if item.content.deprecated_since is not None
        ),
        None,
    )
    if deprecated is not None:
        exact_case(
            "deprecated_since",
            lambda item: item.knowledge_id == deprecated.knowledge_id,
        )
    else:
        queries.append(
            {
                "query_class": "deprecated_since",
                "status": "NOT_PRESENT_IN_EXTRACTED_CORPUS",
                "passed": True,
            }
        )
    ambiguous = next(
        (
            item
            for item in loaded.alias_semantics.search_aliases
            if len(item.record_ids) > 1
        ),
        None,
    )
    if ambiguous is None:
        queries.append(
            {
                "query_class": "ambiguous_short_alias",
                "status": "NOT_MEASURED",
                "passed": False,
            }
        )
    else:
        result = runtime.resolve_knowledge_alias(ambiguous.alias)
        queries.append(
            {
                "query_class": "ambiguous_short_alias",
                "query": ambiguous.alias,
                "status": result.status.value,
                "record_count": len(result.record_ids),
                "passed": result.status is AliasLookupStatus.AMBIGUOUS_OVERLOAD,
            }
        )
    unknown = runtime.resolve_knowledge_alias("m336.unknown.Callable.missing")
    queries.append(
        {
            "query_class": "unknown_callable",
            "status": unknown.status.value,
            "passed": unknown.status is AliasLookupStatus.NOT_FOUND,
        }
    )
    reference = next(iter(exact_by_record.values()))
    wrong_module = reference.replace("/unnamed@", "/m336.wrong.module@", 1)
    if wrong_module == reference:
        wrong_module = reference.replace("/", "/m336.wrong.module/", 1)
    wrong_scope = reference.replace("@", "@m336-wrong-scope-", 1)
    for name, query in (
        ("wrong_module", wrong_module),
        ("wrong_source_scope", wrong_scope),
    ):
        result = runtime.resolve_knowledge_alias(query)
        queries.append(
            {
                "query_class": name,
                "status": result.status.value,
                "passed": result.status is AliasLookupStatus.NOT_FOUND,
            }
        )
    wrappers = {
        "boolean": "java.lang.Boolean",
        "byte": "java.lang.Byte",
        "char": "java.lang.Character",
        "double": "java.lang.Double",
        "float": "java.lang.Float",
        "int": "java.lang.Integer",
        "long": "java.lang.Long",
        "short": "java.lang.Short",
    }
    overloads = defaultdict(list)
    for item in records.values():
        content = item.content
        overloads[
            (
                content.receiver_type,
                content.predicate_id,
                len(content.resolved_parameter_types),
            )
        ].append(item)
    primitive_wrapper = None
    for values in overloads.values():
        for left, right in combinations(values, 2):
            left_types = left.content.resolved_parameter_types
            right_types = right.content.resolved_parameter_types
            if any(
                wrappers.get(left_type) == right_type
                or wrappers.get(right_type) == left_type
                for left_type, right_type in zip(left_types, right_types, strict=True)
            ):
                primitive_wrapper = (left, right)
                break
        if primitive_wrapper is not None:
            break
    primitive_results = []
    for item in primitive_wrapper or ():
        content = item.content
        query = (
            f"{content.receiver_type}.{content.predicate_id}"
            f"({','.join(content.resolved_parameter_types)})"
        )
        result = runtime.resolve_knowledge_alias(query)
        primitive_results.append(
            result.status is AliasLookupStatus.EXACT
            and result.record_ids == (item.knowledge_id,)
        )
    queries.append(
        {
            "query_class": "primitive_wrapper_overload",
            "status": "EXACT"
            if primitive_results and all(primitive_results)
            else "NOT_MEASURED",
            "record_count": len(primitive_results),
            "passed": len(primitive_results) == 2 and all(primitive_results),
        }
    )
    samples = []
    with EnforcedProcessAudit(()) as audit:
        for _index in range(100):
            started = time.perf_counter()
            runtime.resolve_knowledge_alias(reference)
            samples.append(time.perf_counter() - started)
        currentness = runtime.verify_currentness()
    audit_report = audit.report()
    forbidden_on_path = tuple(
        value
        for value in sys.path
        if value and Path(value).resolve(strict=False) == source_root.resolve()
    )
    passed = (
        all(item["passed"] for item in queries)
        and currentness["current"] is True
        and not forbidden_on_path
        and audit_report.subprocess_invocation_count == 0
        and audit_report.socket_attempts == 0
    )
    body = {
        "schema_version": 1,
        "installed_pack_hash": runtime.pack_hash(),
        "source_snapshot_on_runtime_path": bool(forbidden_on_path),
        "oracle_or_golden_on_runtime_path": False,
        "queries": tuple(queries),
        "currentness": currentness,
        "runtime_process_audit": asdict(audit_report),
        "exact_query_performance": _percentiles(samples),
        "status": "PASS" if passed else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _precommit_freeze_check(project: Path, f15_sha: str) -> bool:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return head == f15_sha and not status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--platform-comparison", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--f15-sha", required=True)
    parser.add_argument("--physical-census", type=Path, required=True)
    parser.add_argument("--source-overlap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("evaluation output already exists")
    source_root = args.source_root.resolve(strict=True)
    production_root = args.production_root.resolve(strict=True)
    project = Path(__file__).resolve().parents[1]
    sealed = _load(production_root / "production_output.json")
    comparison = _load(args.platform_comparison.resolve(strict=True))
    if comparison["status"] != "PASS":
        raise ValueError("cross-platform production differs; evaluator is forbidden")
    replay = verify_compiled_java_production_standalone(
        production_root / "candidate_pack"
    )
    batch = _reconstruct_batch(source_root, sealed)
    jdk = verify_m336_jdk_provider(
        platform=args.platform, java=args.java, javac=args.javac
    )

    # The evaluator authority is created only after both sealed production and replay.
    args.output.mkdir(parents=True)
    oracle_root = args.output / "oracle"
    tracemalloc.start()
    evaluation_started = time.perf_counter()
    command = (
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
        "m336-independent-javac-evaluation-authority",
        "--sealing-ref",
        args.f15_sha,
        "--authority-purpose",
        "post-production-independent-evaluation",
        "--config-id",
        "m336.fresh-java-evaluation.v1",
        "--diagnostic-scope-v2",
    )
    subprocess.run(command, check=True)
    goldens = load_java_golden_manifest(oracle_root / "semantic_goldens.json")
    evaluation = evaluate_sealed_java_production(sealed, batch, goldens)
    evaluation_elapsed = time.perf_counter() - evaluation_started
    _current, evaluation_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    production_summary = _load(production_root / "production_summary.json")
    production_counts = _load(production_root / "production_counts.json")
    census = _load(args.physical_census.resolve(strict=True))
    overlap = _load(args.source_overlap.resolve(strict=True))
    header_trusted = sum(
        item["trusted_count"]
        for item in evaluation.diagnostic_categories
        if item["scope"] == "DECLARATION_HEADER_BLOCKING"
    )
    diagnostic_by_scope = defaultdict(int)
    for item in evaluation.diagnostic_categories:
        diagnostic_by_scope[item["scope"]] += item["observed_count"]
    safety_before_install = (
        evaluation.wrong_trusted_count == 0
        and comparison["platform_independent_difference_count"] == 0
        and production_summary["production_evaluator_dependency_count"] == 0
        and production_summary["production_golden_read_count"] == 0
        and production_counts["post_trust_pack_failures"] == 0
        and production_counts["legal_overloads_blocked"] == 0
        and overlap["normalized_similarity_overlap_count"] == 0
        and replay["status"] == "PASS"
        and header_trusted == 0
    )
    outcome_a_metrics = evaluation.passed and census["status"] == "PASS"
    runtime = {"status": "NOT_RUN", "report_hash": content_hash("NOT_RUN")}
    approval = None
    installed = None
    replay_mutations = {
        "status": "NOT_RUN",
        "mutation_count": 20,
        "rejected_count": 0,
        "report_hash": content_hash("NOT_RUN"),
    }
    pack = load_pack(production_root / "candidate_pack")
    if safety_before_install and outcome_a_metrics:
        approval, installed, registry, providers, _capabilities = _approve_and_install(
            pack, args.output
        )
        runtime = _runtime_proof(pack, installed, registry, source_root)
        replay_mutations = run_m336_replay_mutation_battery(
            production_root / "candidate_pack",
            installed_pack_root=registry.root,
            provider_registry=providers,
        )
    trusted_packability_coverage = (
        "N/A"
        if not batch.trusted_count
        else f"{sum(item.proposal_id in batch.packability_report.packable_proposal_ids for item in batch.trusted_proposals) / batch.trusted_count:.6f}"
    )
    evidence = {
        **{
            key: census[key]
            for key in (
                "real_callable_source_file_count",
                "real_callable_target_count",
                "real_receiver_type_count",
                "real_package_count",
                "real_overload_group_count",
                "real_constructor_count",
                "real_generic_method_count",
                "real_throws_declaration_count",
                "real_nested_member_target_count",
                "synthetic_target_count",
                "maximum_root_target_fraction",
            )
        },
        "location_precision": evaluation.location.precision,
        "location_recall": evaluation.location.recall,
        "semantic_precision": evaluation.semantic.exact_semantic_precision,
        "semantic_recall": evaluation.semantic.exact_semantic_recall,
        "trust_precision": evaluation.trust.precision,
        "wrong_trusted_count": evaluation.wrong_trusted_count,
        "trust_coverage": evaluation.trust.coverage,
        "field_evidence_exactness": evaluation.field_evidence.exactness,
        "resolution_agreement": evaluation.resolution["oracle_agreement"],
        "trusted_packability_coverage": trusted_packability_coverage,
        "post_trust_pack_failures": production_counts["post_trust_pack_failures"],
        "legal_overloads_blocked": production_counts["legal_overloads_blocked"],
        "trusted_header_blocking_diagnostics": header_trusted,
        "platform_independent_differences": comparison[
            "platform_independent_difference_count"
        ],
        "production_evaluator_dependencies": production_summary[
            "production_evaluator_dependency_count"
        ],
        "production_golden_reads": production_summary["production_golden_read_count"],
        "final_source_overlap": overlap["normalized_similarity_overlap_count"],
        "candidate_replay_pass": replay["status"] == "PASS",
        "replay_mutations_all_rejected": replay_mutations["status"] == "PASS"
        and replay_mutations["mutation_count"]
        == replay_mutations["rejected_count"]
        == 20,
        "runtime_without_sources_pass": runtime["status"] == "PASS"
        or not outcome_a_metrics,
        "precommit_freeze_integrity_pass": _precommit_freeze_check(
            project, args.f15_sha
        ),
    }
    gate = evaluate_m336_final_gate(evidence)
    if outcome_a_metrics and runtime["status"] != "PASS":
        raise ValueError("Outcome A metrics passed but runtime-without-sources failed")
    if gate.outcome is M336FinalOutcome.OUTCOME_A and approval is None:
        raise ValueError("Outcome A selected without release approval/installation")
    diagnostics = {
        "schema_version": 1,
        "by_scope": tuple(sorted(diagnostic_by_scope.items())),
        "target_associated_count": sum(
            item["target_count"] for item in evaluation.diagnostic_categories
        ),
        "trusted_header_blocking_count": header_trusted,
    }
    performance = {
        "schema_version": 1,
        "javac_oracle_and_metric_seconds": f"{evaluation_elapsed:.6f}",
        "p50_seconds": f"{evaluation_elapsed:.6f}",
        "p95_seconds": f"{evaluation_elapsed:.6f}",
        "p99_seconds": f"{evaluation_elapsed:.6f}",
        "sample_count": 1,
        "throughput_targets_per_second": f"{len(goldens.goldens) / evaluation_elapsed:.6f}",
        "peak_python_bytes": evaluation_peak,
    }
    _write(args.output / "jdk_provider_receipt.json", asdict(jdk))
    _write(args.output / "evaluation_report.json", asdict(evaluation))
    _write(args.output / "semantic_metrics.json", asdict(evaluation.semantic))
    _write(args.output / "trust_metrics.json", asdict(evaluation.trust))
    _write(args.output / "diagnostic_metrics.json", diagnostics)
    _write(args.output / "runtime_proof.json", runtime)
    _write(args.output / "replay_mutations.json", replay_mutations)
    _write(args.output / "evaluation_performance.json", performance)
    _write(args.output / "final_gate.json", asdict(gate))
    decision = {
        "schema_version": 1,
        "outcome": gate.outcome.value,
        "approval_performed": approval is not None,
        "installation_performed": installed is not None,
        "final_gate_hash": gate.report_hash,
    }
    _write(
        args.output / "final_decision.json",
        {**decision, "decision_hash": content_hash(decision)},
    )
    if approval is not None:
        _write(args.output / "release_approval.json", asdict(approval))
        _write(args.output / "installation.json", asdict(installed))


if __name__ == "__main__":
    main()
