"""Run M-33.5 on the disclosed Apache corpus as development data only."""

from __future__ import annotations

import argparse
import ctypes
import random
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import ai_brain.stage3.acquisition.java_production as production_module
from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_component_manifest import (
    build_java_production_component_manifest,
    compare_java_component_manifests,
)
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_process_audit import EnforcedProcessAudit
from ai_brain.stage3.acquisition.java_production import (
    run_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_evaluator import (
    evaluate_sealed_java_production,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_state_audit import (
    EnforcedJavaProductionStateAudit,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.capabilities.registry import CapabilityRegistry
from ai_brain.stage3.domains.aliases import resolve_alias
from ai_brain.stage3.domains.approval import PackApprovalDecision, approve_pack
from ai_brain.stage3.domains.registry import InstalledDomainRegistry
from ai_brain.stage3.domains.runtime import GenericDomainRuntime
from ai_brain.stage3.domains.validation import validate_pack
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION
from ai_brain.stage3.providers.registry import ProviderRegistry

STAMP = "2026-09-03T00:00:00Z"
RUN_ID = "m335.disclosed-development-java.v1"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _paths(root: Path, order: str) -> tuple[Path, ...]:
    values = list(root.rglob("*.java"))
    canonical = sorted(
        values, key=lambda item: item.relative_to(root).as_posix().encode("utf-8")
    )
    if order == "reverse":
        canonical.reverse()
    elif order == "shuffle":
        random.Random(335).shuffle(canonical)
    elif order == "native":
        return tuple(values)
    elif order != "original":
        raise ValueError("unknown M-33.5 input order")
    return tuple(canonical)


def _run(root: Path, output: Path, order: str, *, compact: bool):
    timings = {}
    with tempfile.TemporaryDirectory(prefix="m335-development-") as temporary:
        store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
        started = time.perf_counter()
        bundle = ingest_bundle(
            _paths(root, order),
            bundle_id="m335-disclosed-java",
            domain_tags=("java-api",),
            imported_at=STAMP,
            source_root=root,
            store=store,
        )
        timings["canonical_ingestion_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        with (
            EnforcedProcessAudit(()) as process_audit,
            EnforcedJavaProductionFileAudit() as file_audit,
            EnforcedJavaProductionStateAudit() as state_audit,
        ):
            batch = _run_profiled_production(bundle, store, timings)
        timings["production_seconds"] = time.perf_counter() - started
        sealed = seal_java_production_output(batch)
        authorizations = verify_java_production_batch(batch, store)
        by_id = {item.trusted_proposal_id: item for item in authorizations}
        reviewed = []
        approvals = []
        for proposal in batch.trusted_proposals:
            updated, _review, approval = review_proposal(
                proposal,
                reviewer_identity="m335-development-process",
                reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                decision=ReviewDecision.APPROVE,
                rationale="successful canonical packability closure",
                timestamp=STAMP,
                trust_authorization=by_id[proposal.proposal_id],
            )
            reviewed.append(updated)
            approvals.append(approval)
        started = time.perf_counter()
        pack = compile_provisional_pack(
            bundle,
            batch.segmentation.segments,
            tuple(reviewed),
            tuple(approvals),
            output / "candidate_pack",
            domain_id="m335-disclosed-java",
            production_trust_batch=batch,
            production_authorizations=authorizations,
            store=store,
        )
        timings["candidate_compilation_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        replay = verify_compiled_java_production_standalone(output / "candidate_pack")
        timings["candidate_replay_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        installation, runtime_probes = _install_and_probe(
            pack, batch.packability_report, output
        )
        timings["candidate_installation_seconds"] = time.perf_counter() - started
        component = build_java_production_component_manifest(batch, pack)
        pack_files = tuple(
            (
                item.relative_to(output / "candidate_pack").as_posix(),
                bytes_hash(item.read_bytes()),
            )
            for item in sorted(
                (output / "candidate_pack").iterdir(), key=lambda value: value.name
            )
        )
        ambiguous_entry = next(
            (
                item
                for item in pack.alias_semantics.search_aliases
                if len(item.record_ids) > 1
            ),
            None,
        )
        short_query = (
            ambiguous_entry.alias
            if ambiguous_entry is not None
            else "m335.no-ambiguous-alias-present"
        )
        lookup = resolve_alias(pack.alias_semantics, short_query)
        exact_query = pack.alias_semantics.exact_references[0].reference
        performance = {
            "exact_descriptor_lookup_ns": _benchmark_ns(
                lambda: resolve_alias(pack.alias_semantics, exact_query)
            ),
            "ambiguous_alias_lookup_ns": _benchmark_ns(
                lambda: resolve_alias(pack.alias_semantics, short_query)
            ),
            "component_manifest_comparison_ns": _benchmark_ns(
                lambda: compare_java_component_manifests(component, component)
            ),
        }
        if not compact:
            _write(output / "production_output.json", sealed)
        _write(
            output / "production_counts.json",
            {
                "proposal_count": len(batch.proposal_batch.proposals),
                "trusted_count": batch.trusted_count,
                "withheld_count": batch.withheld_count,
                "conflict_count": batch.conflict_report.conflict_count,
                "packability_report_hash": batch.packability_report.report_hash,
                "packable_count": len(batch.packability_report.packable_proposal_ids),
                "legal_overload_group_count": len(
                    batch.packability_report.legal_overload_groups
                ),
                "true_conflict_group_count": len(
                    batch.packability_report.true_conflict_groups
                ),
                "batch_hash": batch.batch_hash,
            },
        )
        if not compact:
            _write(output / "packability_report.json", asdict(batch.packability_report))
            _write(output / "component_manifest.json", asdict(component))
        _write(
            output / "component_roots.json",
            {
                "schema_version": component.schema_version,
                "manifest_hash": component.manifest_hash,
                "components": tuple(
                    {
                        "stage": item.stage,
                        "component_hash": item.component_hash,
                        "item_count": len(item.items),
                    }
                    for item in component.components
                ),
            },
        )
        _write(output / "candidate_replay.json", replay)
        _write(output / "candidate_installation.json", installation)
        _write(output / "runtime_query_probes.json", runtime_probes)
        _write(output / "search_alias_probe.json", asdict(lookup))
        _write(output / "production_process_audit.json", asdict(process_audit.report()))
        _write(output / "production_state_audit.json", asdict(state_audit.report()))
        _write(
            output / "production_file_access_audit.json", asdict(file_audit.report())
        )
        peak = _peak_python_process_bytes()
        measured_timings = {
            key: f"{value:.9f}" for key, value in sorted(timings.items())
        }
        summary = {
            "schema_version": 1,
            "classification": "DISCLOSED_DEVELOPMENT_REGRESSION_ONLY",
            "order": order,
            "bundle_hash": bundle.bundle_hash,
            "source_index_hash": batch.source_index.index_hash,
            "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
            "evidence_manifest_hash": batch.field_evidence.manifest_hash,
            "conflict_report_hash": batch.conflict_report.report_hash,
            "packability_report_hash": batch.packability_report.report_hash,
            "trust_closure_hash": batch.closure.closure_hash,
            "candidate_pack_hash": pack.manifest.pack_content_hash,
            "candidate_pack_tree_hash": content_hash(pack_files),
            "component_manifest_hash": component.manifest_hash,
            "replay_status": replay["status"],
            "timings": measured_timings,
            "performance": performance,
            "proposal_throughput_per_second": f"{len(batch.proposal_batch.proposals) / timings['production_seconds']:.6f}",
            "peak_python_memory_bytes": peak,
            "python_version": sys.version,
            "torch_imported": "torch" in sys.modules,
            "source_execution": batch.source_index.source_execution,
            "annotation_processing": batch.source_index.annotation_processing,
        }
        _write(
            output / "summary.json", {**summary, "summary_hash": content_hash(summary)}
        )
        if compact:
            shutil.rmtree(output / "candidate_pack")
            shutil.rmtree(output / "installed_registry")
        return batch, sealed


def _install_and_probe(pack, packability, output: Path):
    validation = validate_pack(pack)
    providers = ProviderRegistry.build(output / "provider_authority", ())
    capabilities = CapabilityRegistry.build((), providers)
    approval = approve_pack(
        pack_hash=pack.manifest.pack_content_hash,
        knowledge_ir_schema=UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
        concept_graph_hash=pack.manifest.concept_graph_hash,
        source_binding_hashes=pack.manifest.source_binding_hashes,
        capability_resolution_receipt_hashes=(),
        validation_report_hash=content_hash(validation),
        evaluation_manifest_hash=pack.manifest.evaluation_manifest_hash,
        reviewer_identity="m335-development-install-process",
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=PackApprovalDecision.APPROVE,
        policy_version="m335.disclosed-development-install.v1",
        timestamp=STAMP,
    )
    registry = InstalledDomainRegistry.initialize(
        output / "installed_registry",
        capability_registry=capabilities,
        provider_registry=providers,
        created_at=STAMP,
    )
    installed = registry.install(pack, approval, (), installed_at=STAMP)
    verification = registry.verify(require_current_authority=True)
    installed_pack = registry.load_installed_pack(
        pack.manifest.domain_id, pack.manifest.pack_version
    )
    runtime = GenericDomainRuntime(installed_pack, installed_registry=registry)
    exact_by_record = {}
    for item in installed_pack.alias_semantics.exact_references:
        exact_by_record.setdefault(item.record_id, []).append(item.reference)
    binding_by_record = {
        item.record_id: item
        for item in packability.bindings
        if item.proposal_id in packability.packable_proposal_ids
    }
    records = {item.knowledge_id: item for item in installed_pack.knowledge_records}

    def descriptor_reference(record_id):
        return next(value for value in exact_by_record[record_id] if "#" in value)

    queries = []
    first = next(iter(sorted(binding_by_record)))
    queries.append(("exact_receiver_descriptor", descriptor_reference(first)))
    resolved = next(
        (
            value
            for value in exact_by_record[first]
            if "." in value and "#" not in value and "(" in value
        ),
        descriptor_reference(first),
    )
    queries.append(("receiver_method_exact_parameter_types", resolved))
    ambiguous_entry = next(
        (
            item
            for item in installed_pack.alias_semantics.search_aliases
            if len(item.record_ids) > 1
        ),
        None,
    )
    if ambiguous_entry is not None:
        queries.append(("ambiguous_short_method_alias", ambiguous_entry.alias))
    by_member = {}
    for record_id, binding in binding_by_record.items():
        key = (
            binding.identity.binary_receiver_identity,
            binding.identity.member_name,
        )
        by_member.setdefault(key, []).append((record_id, binding))
    constructor_group = next(
        (
            values
            for (_receiver, member), values in sorted(by_member.items())
            if member == "<init>" and len(values) > 1
        ),
        (),
    )
    for index, (record_id, _binding) in enumerate(constructor_group[:2], 1):
        queries.append(
            (f"constructor_overload_{index}", descriptor_reference(record_id))
        )
    primitive_wrapper_pairs = (
        ("Z", "Ljava/lang/Boolean;"),
        ("B", "Ljava/lang/Byte;"),
        ("C", "Ljava/lang/Character;"),
        ("S", "Ljava/lang/Short;"),
        ("I", "Ljava/lang/Integer;"),
        ("J", "Ljava/lang/Long;"),
        ("F", "Ljava/lang/Float;"),
        ("D", "Ljava/lang/Double;"),
    )
    primitive_wrapper_group = next(
        (
            values
            for values in by_member.values()
            if any(
                {primitive, wrapper}
                <= {
                    item.identity.erased_parameter_descriptor
                    for _record, item in values
                }
                for primitive, wrapper in primitive_wrapper_pairs
            )
        ),
        (),
    )
    pair = next(
        (
            (primitive, wrapper)
            for primitive, wrapper in primitive_wrapper_pairs
            if {primitive, wrapper}
            <= {
                item.identity.erased_parameter_descriptor
                for _record, item in primitive_wrapper_group
            }
        ),
        (),
    )
    selected_primitive_wrapper = tuple(
        item
        for item in primitive_wrapper_group
        if item[1].identity.erased_parameter_descriptor in pair
    )
    for index, (record_id, _binding) in enumerate(selected_primitive_wrapper, 1):
        queries.append(
            (f"wrapper_primitive_overload_{index}", descriptor_reference(record_id))
        )
    category_selectors = (
        ("generic_method", lambda record: bool(record.content.method_type_parameters)),
        ("throws_declaration", lambda record: bool(record.content.declared_exceptions)),
        (
            "nested_receiver",
            lambda record: (
                "$"
                in binding_by_record[
                    record.knowledge_id
                ].identity.binary_receiver_identity
            ),
        ),
    )
    for category, selector in category_selectors:
        record = next((item for item in records.values() if selector(item)), None)
        if record is not None:
            queries.append((category, descriptor_reference(record.knowledge_id)))
    queries.append(("unknown_callable", "m335.unknown.callable"))
    probes = tuple(
        {"category": category, **asdict(runtime.resolve_knowledge_alias(query))}
        for category, query in queries
    )
    required_categories = {
        "exact_receiver_descriptor",
        "receiver_method_exact_parameter_types",
        "ambiguous_short_method_alias",
        "constructor_overload_1",
        "constructor_overload_2",
        "wrapper_primitive_overload_1",
        "wrapper_primitive_overload_2",
        "generic_method",
        "throws_declaration",
        "nested_receiver",
        "unknown_callable",
    }
    observed_categories = {item["category"] for item in probes}
    return (
        {
            "status": verification["status"],
            "installed_count": verification["installed_count"],
            "pack_hash": installed.pack_hash,
            "installation_receipt_hash": installed.installation_receipt_hash,
            "runtime_currentness": runtime.verify_currentness(),
        },
        {
            "status": "PASS"
            if required_categories <= observed_categories
            and all(
                item["status"] == "EXACT"
                for item in probes
                if item["category"] != "ambiguous_short_method_alias"
                and item["category"] != "unknown_callable"
            )
            and all(
                item["status"] == "AMBIGUOUS_OVERLOAD"
                for item in probes
                if item["category"] == "ambiguous_short_method_alias"
            )
            and probes[-1]["status"] == "NOT_FOUND"
            else "FAIL",
            "required_categories": tuple(sorted(required_categories)),
            "missing_categories": tuple(
                sorted(required_categories - observed_categories)
            ),
            "probes": probes,
        },
    )


def _run_profiled_production(bundle, store, timings):
    originals = {}
    stages = {
        "source_indexing_seconds": "index_java_bundle",
        "segmentation_seconds": "segment_bundle_with_report",
        "proposal_construction_seconds": "propose_java_knowledge",
        "evidence_construction_seconds": "build_java_field_evidence_manifest",
        "identity_conflict_closure_seconds": "detect_java_production_identity_conflicts",
        "packability_preflight_seconds": "build_java_packability_report",
    }
    for timing_key, attribute in stages.items():
        original = getattr(production_module, attribute)
        originals[attribute] = original

        def measured(*args, _key=timing_key, _original=original, **kwargs):
            started = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                timings[_key] = time.perf_counter() - started

        setattr(production_module, attribute, measured)
    try:
        return run_java_acquisition_pipeline(bundle, store, deterministic_run_id=RUN_ID)
    finally:
        for attribute, original in originals.items():
            setattr(production_module, attribute, original)


def _benchmark_ns(operation, *, repetitions: int = 1_000) -> dict[str, int]:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        operation()
        samples.append(time.perf_counter_ns() - started)
    samples.sort()

    def percentile(value: float) -> int:
        return samples[min(len(samples) - 1, int((len(samples) - 1) * value))]

    return {
        "samples": repetitions,
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
    }


def _peak_python_process_bytes() -> int:
    if sys.platform == "win32":

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        query = getattr(
            ctypes.windll.kernel32,
            "K32GetProcessMemoryInfo",
            ctypes.windll.psapi.GetProcessMemoryInfo,
        )
        query.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        )
        query.restype = ctypes.c_int
        if not query(handle, ctypes.byref(counters), counters.cb):
            return 0
        return int(counters.PeakWorkingSetSize)
    import resource

    # Linux ru_maxrss is KiB; macOS reports bytes.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--order",
        choices=("original", "reverse", "shuffle", "native"),
        default="original",
    )
    parser.add_argument("--java", type=Path)
    parser.add_argument("--javac", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-33.5 development output already exists")
    args.output.mkdir(parents=True)
    root = args.source_root.resolve(strict=True)
    batch, sealed = _run(root, args.output, args.order, compact=args.compact)
    if args.java and args.javac:
        project = Path(__file__).resolve().parents[1]
        oracle = args.output / "oracle"
        command = [
            sys.executable,
            str(project / "scripts/m343_author_semantic_goldens.py"),
            "--corpus",
            str(root),
            "--helper",
            str(project / "tools/m343_java_oracle/JavaSemanticProposalOracle.java"),
            "--javac",
            str(args.javac.resolve(strict=True)),
            "--java",
            str(args.java.resolve(strict=True)),
            "--output",
            str(oracle),
            "--parser-common-hash",
            batch.parser_common_artifact.manifest_hash,
            "--evidence-policy-hash",
            batch.evidence_policy.manifest_hash,
            "--authority-id",
            "m335-disclosed-development-evaluator",
            "--sealing-ref",
            "I14-DEVELOPMENT",
            "--authority-purpose",
            "disclosed-corpus-development-evaluation",
            "--config-id",
            "m335.disclosed-development-evaluation.v1",
            "--real-prefix",
            "apache-commons-io",
            "--real-prefix",
            "apache-commons-lang3",
        ]
        subprocess.run(command, check=True)
        goldens = load_java_golden_manifest(oracle / "semantic_goldens.json")
        evaluation = evaluate_sealed_java_production(sealed, batch, goldens)
        _write(args.output / "evaluation_report.json", asdict(evaluation))


if __name__ == "__main__":
    main()
