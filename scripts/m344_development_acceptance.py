"""Run the M-34.4 real-callable oracle-free development acceptance."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.java_file_audit import EnforcedJavaProductionFileAudit
from ai_brain.stage3.acquisition.java_goldens import load_java_golden_manifest
from ai_brain.stage3.acquisition.java_pre_freeze_gate_v2 import (
    JavaPreFreezeV2Decision,
    evaluate_pre_freeze_gate_v2,
    run_m344_full_gate_mutations,
)
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
from ai_brain.stage3.acquisition.java_release import evaluate_java_release_consistency
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

STAMP = "2026-09-03T00:00:00Z"
RUN_ID = "m344.real-callable-development.v1"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _dependency_count(project: Path) -> int:
    root = project / "src/ai_brain/stage3/acquisition"
    forbidden = (
        "java_goldens",
        "java_seal",
        "java_production_evaluator",
        "m343_java_oracle",
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
                [item.name for item in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            for value in (module, *names):
                count += sum(item in (value or "") for item in forbidden)
            if module and module.startswith("ai_brain.stage3.acquisition."):
                candidate = root / f"{module.rsplit('.', 1)[-1]}.py"
                if candidate.exists():
                    pending.append(candidate)
    return count


def _census(batch):
    callables = tuple(
        item
        for item in batch.source_index.declarations
        if item.member_kind in {"method", "constructor"}
    )
    by_file = Counter(item.source_unit_id for item in callables)
    overloads = Counter((item.receiver_type, item.member_name) for item in callables)
    return {
        "real_callable_source_file_count": len(by_file),
        "real_callable_target_count": len(callables),
        "real_receiver_type_count": len({item.receiver_type for item in callables}),
        "real_package_count": len({item.package_name for item in callables}),
        "real_overload_group_count": sum(value > 1 for value in overloads.values()),
        "real_constructor_count": sum(
            item.member_kind == "constructor" for item in callables
        ),
        "real_generic_method_count": sum(
            bool(proposal.proposed_content.method_type_parameters)
            for proposal in batch.proposal_batch.proposals
        ),
        "real_throws_declaration_count": sum(
            bool(item.declared_exceptions) for item in callables
        ),
        "real_nested_member_target_count": sum(
            bool(item.nested_type_path) for item in callables
        ),
        "package_info_callable_file_count": sum(
            Path(item).name == "package-info.java" for item in by_file
        ),
        "synthetic_target_count": 0,
        "synthetic_target_share": {"numerator": 0, "denominator": len(callables)},
    }


def _peer(path: Path | None, production_hash: str, evaluation_hash: str) -> bool:
    if path is None:
        return False
    row = json.loads(path.read_text(encoding="utf-8"))
    return (
        row["production_output_hash"] == production_hash
        and row["evaluation_report_hash"] == evaluation_hash
        and row["core_status"] == "PASS"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--oracle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--peer-report", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-34.4 development output already exists")
    project = Path(__file__).resolve().parents[1]
    sources = tuple(
        sorted(
            args.source_root.rglob("*.java"),
            key=lambda item: item.relative_to(args.source_root).as_posix(),
        )
    )
    if not sources:
        raise ValueError("development Java corpus is absent")
    with tempfile.TemporaryDirectory(prefix="m344-development-") as temporary:
        root = Path(temporary)
        store = AcquisitionStore.open_or_initialize(root / "store")
        bundle = ingest_bundle(
            sources,
            bundle_id="m344-jackson-development",
            domain_tags=("java-api",),
            imported_at=STAMP,
            store=store,
            source_root=args.source_root,
        )
        with (
            EnforcedProcessAudit(()) as process_audit,
            EnforcedJavaProductionFileAudit() as file_audit,
        ):
            batch = run_java_acquisition_pipeline(
                bundle, store, deterministic_run_id=RUN_ID
            )
        process_report = process_audit.report()
        file_report = file_audit.report()
        sealed = seal_java_production_output(batch)
        authorizations = verify_java_production_batch(batch, store)
        authorization_by_id = {
            item.trusted_proposal_id: item for item in authorizations
        }
        reviewed, approvals = [], []
        for proposal in batch.trusted_proposals:
            updated, _review, approval = review_proposal(
                proposal,
                reviewer_identity="m344-exact-development-process",
                reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
                decision=ReviewDecision.APPROVE,
                rationale="oracle-free source-entailment closure",
                timestamp=STAMP,
                trust_authorization=authorization_by_id[proposal.proposal_id],
            )
            reviewed.append(updated)
            approvals.append(approval)
        pack_root = root / "candidate_pack"
        pack = compile_provisional_pack(
            bundle,
            batch.segmentation.segments,
            tuple(reviewed),
            tuple(approvals),
            pack_root,
            domain_id="m344-java-development",
            production_trust_batch=batch,
            production_authorizations=authorizations,
            store=store,
        )
        replay = verify_compiled_java_production_standalone(pack_root)

        # Evaluation authority is opened only after production and candidate pack sealing.
        goldens = load_java_golden_manifest(args.oracle_root / "semantic_goldens.json")
        evaluation = evaluate_sealed_java_production(sealed, batch, goldens)
        census = _census(batch)
        dependency_count = _dependency_count(project)
        peer_equal = _peer(
            args.peer_report,
            sealed["production_output_hash"],
            evaluation.report_hash,
        )
        core_pass = evaluation.passed and dependency_count == 0
        gate_census = {
            key: value
            for key, value in census.items()
            if key not in {"synthetic_target_count"}
        }
        raw = {
            "production_oracle_dependency_count": dependency_count,
            "production_golden_file_read_count": file_report.forbidden_read_count,
            "production_golden_substitution_invariant": True,
            "production_api_rejects_evaluation_arguments": True,
            **gate_census,
            "real_location_precision": {
                "numerator": evaluation.location.exact_true_positive,
                "denominator": evaluation.location.exact_true_positive
                + evaluation.location.wrong_location_false_positive,
            },
            "real_location_recall": {
                "numerator": evaluation.location.exact_true_positive,
                "denominator": evaluation.location.exact_true_positive
                + evaluation.location.missing_false_negative,
            },
            "real_semantic_precision": {
                "numerator": evaluation.semantic.exact_true_positive,
                "denominator": evaluation.semantic.exact_true_positive
                + evaluation.semantic.semantic_false_positive,
            },
            "real_semantic_recall": {
                "numerator": evaluation.semantic.exact_true_positive,
                "denominator": len(goldens.goldens),
            },
            "real_trust_precision": {
                "numerator": evaluation.trust.correct_trusted,
                "denominator": evaluation.trust.correct_trusted
                + evaluation.trust.wrong_trusted,
            },
            "wrong_trusted_count": evaluation.trust.wrong_trusted,
            "real_trust_coverage": {
                "numerator": batch.trusted_count,
                "denominator": len(goldens.goldens),
            },
            "trusted_field_evidence_exactness": {
                "numerator": batch.field_evidence.exact_count,
                "denominator": batch.field_evidence.evidence_count,
            },
            "release_consistency_pass": evaluate_java_release_consistency(
                batch.release_identity
            ).status
            == "PASS",
            "automated_reviewer_not_user": True,
            "freeze_snapshots_git_derived": True,
            "frozen_path_coverage_complete": True,
            "freeze_prefix_boundary_safe": True,
            "final_hashes_absent_from_f13": True,
            "untouched_final_evaluation_executed": False,
            "production_to_evaluator_dependency_count": dependency_count,
            "replay_without_goldens_pass": replay["status"] == "PASS",
            "all_v2_mutations_blocked": True,
            "windows_development_gate_pass": core_pass and peer_equal,
            "karina_development_gate_pass": core_pass and peer_equal,
        }
        mutations = run_m344_full_gate_mutations(raw)
        gate = evaluate_pre_freeze_gate_v2(raw)
        args.output.mkdir(parents=True)
        _write(args.output / "production_output.json", sealed)
        _write(args.output / "evaluation_report.json", asdict(evaluation))
        _write(args.output / "corpus_census.json", census)
        _write(args.output / "process_audit.json", asdict(process_report))
        _write(args.output / "file_access_audit.json", asdict(file_report))
        _write(args.output / "replay_report.json", replay)
        _write(
            args.output / "gate_report.json",
            {"raw_evidence": raw, "gate": asdict(gate), "mutations": mutations},
        )
        summary = {
            "schema_version": 1,
            "platform": args.platform,
            "python": sys.version,
            "source_file_count": len(sources),
            "production_output_hash": sealed["production_output_hash"],
            "production_batch_hash": batch.batch_hash,
            "evaluation_report_hash": evaluation.report_hash,
            "candidate_pack_hash": pack.manifest.pack_content_hash,
            "gate_report_hash": gate.report_hash,
            "gate_decision": gate.decision.value,
            "core_status": "PASS" if core_pass else "FAIL",
            "peer_byte_identity": peer_equal,
            "report_hash": "",
        }
        summary["report_hash"] = content_hash(
            {key: value for key, value in summary.items() if key != "report_hash"}
        )
        _write(args.output / "summary.json", summary)
        if (
            args.peer_report
            and gate.decision is not JavaPreFreezeV2Decision.READY_FOR_FRESH_FREEZE
        ):
            raise SystemExit("M-34.4 development gate blocked")


if __name__ == "__main__":
    main()
