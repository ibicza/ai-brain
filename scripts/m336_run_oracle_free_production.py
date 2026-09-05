"""Run and seal M-33.6 Java production with evaluator authority absent."""

from __future__ import annotations

import argparse
import ast
import json
import os
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
)
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_process_audit import (
    EnforcedProcessAudit,
    exact_subprocess_policy,
)
from ai_brain.stage3.acquisition.java_production import (
    run_compiler_aware_java_acquisition_pipeline,
    run_java_acquisition_pipeline,
    seal_java_production_output,
    verify_java_production_batch,
)
from ai_brain.stage3.acquisition.java_production_compiler import (
    build_java_production_compilation_probe,
    java_production_compiler_command,
)
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)
from ai_brain.stage3.acquisition.java_state_audit import (
    EnforcedJavaProductionStateAudit,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

STAMP = "1970-01-01T00:00:00Z"
RUN_ID = "m336.untouched-final-java.production.v1"


def _peak_process_bytes() -> int:
    """Return OS-maintained peak RSS without perturbing the measured pipeline."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = (
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            )

        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.argtypes = ()
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        get_process_memory_info.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = get_current_process()
        if not get_process_memory_info(process, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return int(counters.PeakWorkingSetSize)
    import resource

    # Linux reports KiB; macOS reports bytes.  Karina is Linux, but retain the
    # portable branch so this evidence helper cannot silently mislabel units.
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _tree_hash(root: Path) -> str:
    return content_hash(
        tuple(
            (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
            for path in sorted(
                (item for item in root.rglob("*") if item.is_file()),
                key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
            )
        )
    )


def _production_evaluator_dependency_count(project: Path) -> int:
    root = project / "src/ai_brain/stage3/acquisition"
    forbidden = (
        "java_goldens",
        "java_production_evaluator",
        "m343_java_oracle",
        "semantic_goldens",
    )
    pending = [root / "java_production.py"]
    seen = set()
    count = 0
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = (
                tuple(item.name for item in node.names)
                if isinstance(node, ast.Import)
                else ()
            )
            count += sum(
                marker in (value or "")
                for value in (module, *names)
                for marker in forbidden
            )
            if module and module.startswith("ai_brain.stage3.acquisition."):
                candidate = root / f"{module.rsplit('.', 1)[-1]}.py"
                if candidate.exists():
                    pending.append(candidate)
    return count


def _assert_evaluation_authority_absent(source_root: Path, output: Path) -> None:
    forbidden = {"oracle", "golden", "goldens", "evaluator", "evaluation_report.json"}
    observed = {
        path.name.casefold()
        for root in (source_root, output)
        if root.exists()
        for path in root.rglob("*")
    }
    if forbidden & observed:
        raise ValueError("evaluator/golden authority exists before production seal")


def _run_profiled_production(
    bundle,
    store,
    timings,
    *,
    compilation_probe=None,
    javac=None,
    source_entry_ids=None,
    compilation_work_root=None,
):
    originals = {}
    stages = {
        "source_indexing": "index_java_bundle",
        "segmentation": "segment_bundle_with_report",
        "proposal_generation": "propose_java_knowledge",
        "field_evidence": "build_java_field_evidence_manifest",
        "identity_closure": "detect_java_production_identity_conflicts",
        "packability": "build_java_packability_report",
    }
    for timing_key, attribute in stages.items():
        original = getattr(production_module, attribute)
        originals[attribute] = original

        def measured(*values, _key=timing_key, _original=original, **keywords):
            started = time.perf_counter()
            try:
                return _original(*values, **keywords)
            finally:
                timings[_key] = time.perf_counter() - started

        setattr(production_module, attribute, measured)
    started = time.perf_counter()
    try:
        if compilation_probe is not None:
            return run_compiler_aware_java_acquisition_pipeline(
                bundle,
                store,
                deterministic_run_id=RUN_ID,
                compilation_probe=compilation_probe,
                javac_executable=javac,
                source_entry_ids=source_entry_ids,
                compilation_work_root=compilation_work_root,
            )
        return run_java_acquisition_pipeline(bundle, store, deterministic_run_id=RUN_ID)
    finally:
        timings["trust_closure_total"] = time.perf_counter() - started
        for attribute, original in originals.items():
            setattr(production_module, attribute, original)


def _single_sample(value: float) -> dict[str, object]:
    measured = f"{value:.9f}"
    return {
        "sample_count": 1,
        "p50_seconds": measured,
        "p95_seconds": measured,
        "p99_seconds": measured,
        "total_seconds": measured,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--javac", type=Path)
    parser.add_argument("--source-entry-bindings", type=Path)
    parser.add_argument("--selected-manifest", type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh production output already exists")
    _assert_evaluation_authority_absent(source_root, args.output)
    sources = tuple(
        sorted(
            source_root.rglob("*.java"),
            key=lambda item: item.relative_to(source_root).as_posix().encode("utf-8"),
        )
    )
    if not sources:
        raise ValueError("selected Java source snapshot is empty")
    compiler_inputs = (
        args.javac,
        args.source_entry_bindings,
        args.selected_manifest,
    )
    if any(compiler_inputs) and not all(compiler_inputs):
        raise ValueError("compiler-aware production inputs must be supplied together")
    project = Path(__file__).resolve().parents[1]
    dependency_count = _production_evaluator_dependency_count(project)
    if dependency_count:
        raise ValueError("production import closure reaches evaluator/golden authority")
    args.output.mkdir(parents=True)
    timings = {}
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="m336-final-production-") as temporary:
        temporary_root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(temporary_root / "store")
        ingestion_started = time.perf_counter()
        bundle = ingest_bundle(
            sources,
            bundle_id="m336-final-java",
            domain_tags=("java-api",),
            imported_at=STAMP,
            store=store,
            source_root=source_root,
        )
        timings["ingestion"] = time.perf_counter() - ingestion_started
        compilation_probe = None
        source_entry_ids = None
        process_policies = ()
        compilation_work_root = None
        if args.javac is not None:
            bindings = source_entry_binding_manifest_from_dict(
                json.loads(
                    args.source_entry_bindings.resolve(strict=True).read_text(
                        encoding="utf-8"
                    )
                )
            )
            selected = m336f_selected_source_manifest_from_dict(
                json.loads(
                    args.selected_manifest.resolve(strict=True).read_text(
                        encoding="utf-8"
                    )
                )
            )
            selected_units = {item.selected_path for item in selected.files}
            actual_units = {
                item.relative_path.replace("\\", "/") for item in bundle.documents
            }
            if selected_units != actual_units:
                raise ValueError(
                    "selected source bytes differ from the sealed manifest"
                )
            binding_by_unit = {item.selected_path: item for item in bindings.bindings}
            source_entry_ids = {
                unit: binding_by_unit[unit].source_entry_id.identity_hash
                for unit in sorted(selected_units)
            }
            compilation_probe = build_java_production_compilation_probe(args.javac)
            compilation_work_root = temporary_root / "compiler"
            command = java_production_compiler_command(
                javac_executable=args.javac,
                probe=compilation_probe,
                compilation_work_root=compilation_work_root,
            )
            process_policies = (
                exact_subprocess_policy(
                    "m336f-production-javac",
                    command,
                    purpose="JAVAC_PRODUCTION_DIAGNOSTIC",
                    maximum_invocations=1,
                ),
            )
        with (
            EnforcedProcessAudit(process_policies) as process_audit,
            EnforcedJavaProductionFileAudit() as file_audit,
            EnforcedJavaProductionStateAudit() as state_audit,
        ):
            batch = _run_profiled_production(
                bundle,
                store,
                timings,
                compilation_probe=compilation_probe,
                javac=args.javac,
                source_entry_ids=source_entry_ids,
                compilation_work_root=compilation_work_root,
            )
            authorizations = verify_java_production_batch(batch, store)
            if batch.compiler_report is not None:
                _write(args.output / "compiler_probe.json", asdict(compilation_probe))
                _write(
                    args.output / "compiler_report.json", asdict(batch.compiler_report)
                )
                _write(
                    args.output / "compilation_trust_gate.json",
                    asdict(batch.compilation_trust_gate),
                )
                prepack_body = {
                    "schema_version": 1,
                    "proposal_count": len(batch.proposal_batch.proposals),
                    "trusted_count": batch.trusted_count,
                    "withheld_count": batch.withheld_count,
                    "batch_blocked": batch.compilation_trust_gate.batch_blocked,
                    "compiler_diagnostic_count": batch.compiler_report.diagnostic_count,
                    "compiler_unknown_scope_count": (
                        batch.compiler_report.unknown_scope_count
                    ),
                    "compiler_unmapped_diagnostic_count": (
                        batch.compiler_report.unmapped_diagnostic_count
                    ),
                    "compiler_source_unit_unbound_count": (
                        batch.compiler_report.source_unit_unbound_count
                    ),
                    "compiler_malformed_output_count": (
                        batch.compiler_report.malformed_output_count
                    ),
                }
                _write(
                    args.output / "prepack_gate.json",
                    {**prepack_body, "gate_hash": content_hash(prepack_body)},
                )
            authorization_by_id = {
                item.trusted_proposal_id: item for item in authorizations
            }
            reviewed = []
            approvals = []
            for proposal in batch.trusted_proposals:
                updated, _review, approval = review_proposal(
                    proposal,
                    reviewer_identity="m336-oracle-free-production-process",
                    reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                    decision=ReviewDecision.APPROVE,
                    rationale="oracle-free source-entailment closure",
                    timestamp=STAMP,
                    trust_authorization=authorization_by_id[proposal.proposal_id],
                )
                reviewed.append(updated)
                approvals.append(approval)
            pack_root = args.output / "candidate_pack"
            compilation_started = time.perf_counter()
            pack = compile_provisional_pack(
                bundle,
                batch.segmentation.segments,
                tuple(reviewed),
                tuple(approvals),
                pack_root,
                domain_id="m336-final-java",
                production_trust_batch=batch,
                production_authorizations=authorizations,
                store=store,
            )
            timings["candidate_pack_compilation"] = (
                time.perf_counter() - compilation_started
            )
            replay_started = time.perf_counter()
            replay = verify_compiled_java_production_standalone(pack_root)
            timings["replay"] = time.perf_counter() - replay_started
        sealed = seal_java_production_output(batch)
        component = build_java_production_component_manifest(batch, pack)
        process_report = process_audit.report()
        file_report = file_audit.report()
        state_report = state_audit.report()
    elapsed = time.perf_counter() - started
    peak = _peak_process_bytes()
    if (
        process_report.unexpected_subprocess_count
        or process_report.socket_attempts
        or process_report.os_system_attempts
        or process_report.source_execution_count
        or process_report.annotation_processor_invocation_count
        or process_report.generated_class_execution_count
        or file_report.forbidden_read_count
        or any(
            value
            for key, value in asdict(state_report).items()
            if key.endswith("attempts")
        )
        or "torch" in sys.modules
    ):
        raise ValueError("production isolation audit is not zero")
    compiler_scope_by_diagnostic = (
        {
            item.diagnostic_hash: item.diagnostic_scope.value
            for item in batch.compiler_report.bindings
        }
        if batch.compiler_report is not None
        else {}
    )
    trusted_blocking_hashes = tuple(
        diagnostic_hash
        for row in sealed["candidate_rows"]
        if row["production_trust_state"] == "trusted"
        for diagnostic_hash in row.get("applicable_blocking_diagnostic_hashes", ())
    )
    counts = {
        "proposal_count": len(batch.proposal_batch.proposals),
        "eligible_count": len(batch.packability_report.eligible_proposal_ids),
        "packable_count": len(batch.packability_report.packable_proposal_ids),
        "withheld_count": batch.withheld_count,
        "packability_withheld_count": len(batch.packability_report.withholding_reasons),
        "trusted_count": batch.trusted_count,
        "post_trust_pack_failures": 0,
        "legal_overloads_blocked": 0,
        "compiler_diagnostic_count": (
            batch.compiler_report.diagnostic_count if batch.compiler_report else 0
        ),
        "compiler_blocked_declaration_count": (
            batch.compilation_trust_gate.blocked_declaration_count
            if batch.compilation_trust_gate
            else 0
        ),
        "trusted_compiler_blocked_target_count": len(
            {
                row["proposal_id"]
                for row in sealed["candidate_rows"]
                if row["production_trust_state"] == "trusted"
                and row.get("applicable_blocking_diagnostic_hashes")
            }
        ),
        "trusted_header_blocking_target_count": sum(
            compiler_scope_by_diagnostic.get(item) == "DECLARATION_HEADER_BLOCKING"
            for item in trusted_blocking_hashes
        ),
        "trusted_enclosing_type_blocking_target_count": sum(
            compiler_scope_by_diagnostic.get(item) == "ENCLOSING_TYPE_BLOCKING"
            for item in trusted_blocking_hashes
        ),
    }
    performance = {
        "schema_version": 1,
        "platform": args.platform,
        "production_total_seconds": f"{elapsed:.6f}",
        "throughput_targets_per_second": f"{len(batch.decisions) / elapsed:.6f}",
        "peak_python_bytes": peak,
        "substage_seconds": tuple(
            (key, f"{value:.9f}") for key, value in sorted(timings.items())
        ),
        "substage_percentiles": tuple(
            (key, _single_sample(value)) for key, value in sorted(timings.items())
        ),
        "m336d_requested_operation_count": 5,
        "m336d_requested_operations": tuple(
            (name, _single_sample(timings[source_name]))
            for name, source_name in (
                ("java_indexing", "source_indexing"),
                ("proposal_production", "proposal_generation"),
                ("trust_closure", "trust_closure_total"),
                ("candidate_pack_construction", "candidate_pack_compilation"),
                ("replay", "replay"),
            )
        ),
    }
    summary_body = {
        "schema_version": 1,
        "platform": args.platform,
        "production_output_hash": sealed["production_output_hash"],
        "production_batch_hash": batch.batch_hash,
        "component_manifest_hash": component.manifest_hash,
        "candidate_pack_hash": pack.manifest.pack_content_hash,
        "candidate_tree_hash": _tree_hash(args.output / "candidate_pack"),
        "candidate_replay_hash": replay["artifact_hash"],
        "candidate_replay_status": replay["status"],
        "production_evaluator_dependency_count": dependency_count,
        "production_golden_read_count": file_report.forbidden_read_count,
        "torch_imported": "torch" in sys.modules,
        "status": "PASS",
        **(
            {
                "compiler_probe_hash": compilation_probe.probe_hash,
                "compiler_identity_hash": compilation_probe.compiler_identity_hash,
                "compiler_report_hash": batch.compiler_report.report_hash,
                "compilation_trust_gate_hash": batch.compilation_trust_gate.gate_hash,
            }
            if batch.compiler_report is not None
            else {}
        ),
    }
    _write(args.output / "production_output.json", sealed)
    _write(args.output / "component_manifest.json", asdict(component))
    _write(args.output / "packability_report.json", asdict(batch.packability_report))
    _write(args.output / "trust_closure.json", asdict(batch.closure))
    _write(args.output / "production_counts.json", counts)
    _write(args.output / "candidate_replay.json", replay)
    _write(
        args.output / "production_process_audit.json",
        _public_process_audit(process_report),
    )
    _write(args.output / "production_file_access_audit.json", asdict(file_report))
    _write(args.output / "production_state_audit.json", asdict(state_report))
    _write(args.output / "production_performance.json", performance)
    _write(
        args.output / "production_summary.json",
        {**summary_body, "summary_hash": content_hash(summary_body)},
    )
    if batch.compiler_report is not None:
        _write(args.output / "compiler_probe.json", asdict(compilation_probe))
        _write(args.output / "compiler_report.json", asdict(batch.compiler_report))
        _write(
            args.output / "compilation_trust_gate.json",
            asdict(batch.compilation_trust_gate),
        )


def _public_process_audit(report):
    body = {
        "schema_version": 2,
        "policy_hash": report.policy_hash,
        "invocation_receipt_hashes": tuple(
            item.receipt_hash for item in report.invocation_receipts
        ),
        "subprocess_invocation_count": report.subprocess_invocation_count,
        "unexpected_subprocess_count": report.unexpected_subprocess_count,
        "socket_attempts": report.socket_attempts,
        "os_system_attempts": report.os_system_attempts,
        "source_execution_count": report.source_execution_count,
        "annotation_processor_invocation_count": (
            report.annotation_processor_invocation_count
        ),
        "generated_class_execution_count": report.generated_class_execution_count,
    }
    return {**body, "report_hash": content_hash(body)}


if __name__ == "__main__":
    main()
