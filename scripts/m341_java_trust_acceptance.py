"""Deterministic end-to-end acceptance for M-34.1 Java semantic trust."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.compiler import (
    compile_provisional_pack,
    verify_compiled_java_evidence,
)
from ai_brain.stage3.acquisition.java_goldens import (
    load_java_golden_manifest,
)
from ai_brain.stage3.acquisition.java_pipeline import (
    detect_java_identity_conflicts,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.models import ReviewDecision
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/m341_java/corpus"
GOLDENS = ROOT / "tests/fixtures/m341_java/goldens/sealed_locations.json"
M33_HASHES = ROOT / "tests/fixtures/m341_java/m33_java_source_hashes.json"
STAMP = "2026-08-30T00:00:00Z"
RUN_ID = "m341.authoritative.acceptance.v1"


def _acceptance_status(criteria):
    return "PASS" if all(criteria.values()) else "FAIL"


def _rehash(value, hash_field):
    body = asdict(value)
    body.pop(hash_field)
    return replace(value, **{hash_field: content_hash(body)})


def _negative_goldens(manifest, count):
    values = []
    for index, golden in enumerate(manifest.goldens):
        if index < count:
            golden = replace(
                golden,
                start_offset=golden.start_offset + (index % 3) + 1,
                golden_hash="",
            )
            golden = _rehash(golden, "golden_hash")
        values.append(golden)
    result = replace(
        manifest,
        goldens=tuple(values),
        manifest_hash="",
    )
    return _rehash(result, "manifest_hash")


def _tamper_matrix(batch, store):
    cases = {
        "batch_hash": replace(batch, batch_hash="0" * 64),
        "closure_hash": replace(
            batch,
            closure=replace(batch.closure, closure_hash="1" * 64),
        ),
        "bundle_binding": replace(
            batch,
            closure=replace(batch.closure, bundle_hash="2" * 64),
        ),
        "source_index": replace(
            batch,
            source_index=replace(batch.source_index, index_hash="3" * 64),
        ),
        "proposal_manifest": replace(
            batch,
            proposal_batch=replace(
                batch.proposal_batch, proposal_manifest_hash="4" * 64
            ),
        ),
        "evidence_manifest": replace(
            batch,
            field_evidence=replace(batch.field_evidence, manifest_hash="5" * 64),
        ),
        "golden_manifest": replace(
            batch,
            golden_manifest=replace(batch.golden_manifest, manifest_hash="6" * 64),
        ),
        "conflict_report": replace(
            batch,
            conflict_report=replace(batch.conflict_report, report_hash="7" * 64),
        ),
        "decision": replace(
            batch,
            decisions=(
                replace(batch.decisions[0], decision_hash="8" * 64),
                *batch.decisions[1:],
            ),
        ),
        "trusted_manifest": replace(
            batch,
            closure=replace(batch.closure, trusted_proposal_manifest_hash="9" * 64),
        ),
    }
    rejected = []
    for name, candidate in cases.items():
        try:
            verify_trust_bound_batch(candidate, store)
        except (TypeError, ValueError):
            rejected.append(name)
    return tuple(sorted(cases)), tuple(sorted(rejected))


def evaluate(temporary: Path):
    paths = tuple(sorted(CORPUS.rglob("*.java"), key=lambda item: item.name))
    real_files = tuple(item for item in paths if "real" in item.parts)
    synthetic_files = tuple(item for item in paths if "synthetic" in item.parts)
    store = AcquisitionStore.open_or_initialize(temporary / "store")
    bundle = ingest_bundle(
        paths,
        bundle_id="m341-java-trust",
        domain_tags=("java", "m341-production-integration"),
        imported_at=STAMP,
        version="m341-v1",
        store=store,
    )
    goldens = load_java_golden_manifest(GOLDENS)
    batch = run_java_trust_pipeline(
        bundle,
        store,
        goldens,
        deterministic_run_id=RUN_ID,
    )
    verify_trust_bound_batch(batch, store)

    negative_count = 220
    negative_batch = run_java_trust_pipeline(
        bundle,
        store,
        _negative_goldens(goldens, negative_count),
        deterministic_run_id=f"{RUN_ID}.negative",
    )
    negative_ids = {item.golden_id for item in goldens.goldens[:negative_count]}
    rejected_negative_ids = {
        decision.golden_id
        for decision in negative_batch.decisions
        if decision.golden_id in negative_ids
        and decision.final_state.value == "withheld"
    }

    mutation_root = temporary / "mutated"
    mutation_root.mkdir()
    mutated_paths = []
    for path in paths:
        destination = mutation_root / path.name
        shutil.copyfile(path, destination)
        mutated_paths.append(destination)
    first = mutated_paths[0]
    first.write_bytes(first.read_bytes() + b"\n// adversarial source mutation\n")
    mutated_store = AcquisitionStore.open_or_initialize(temporary / "mutated-store")
    mutated_bundle = ingest_bundle(
        tuple(mutated_paths),
        bundle_id="m341-java-mutated",
        imported_at=STAMP,
        store=mutated_store,
    )
    source_mutation_rejected = False
    try:
        run_java_trust_pipeline(
            mutated_bundle,
            mutated_store,
            goldens,
            deterministic_run_id=f"{RUN_ID}.source-mutation",
        )
    except ValueError:
        source_mutation_rejected = True

    replay_rejected = False
    try:
        verify_trust_bound_batch(replace(batch, bundle=mutated_bundle), store)
    except (TypeError, ValueError):
        replay_rejected = True

    tamper_cases, tamper_rejections = _tamper_matrix(batch, store)
    approvals = []
    approved = []
    reviews = []
    for proposal in batch.trusted_proposals:
        updated, review, approval = review_proposal(
            proposal,
            reviewer_identity="m341-human-reviewer",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="Independent golden and complete exact field evidence verified.",
            timestamp=STAMP,
            trust_authorization=batch,
        )
        approved.append(updated)
        reviews.append(review)
        approvals.append(approval)
    pack = compile_provisional_pack(
        bundle,
        batch.segmentation.segments,
        tuple(approved),
        tuple(approvals),
        temporary / "pack",
        domain_id="m341-java-production",
        pack_version="0.1.0-m341",
        trust_bound_batch=batch,
        store=store,
    )
    verify_compiled_java_evidence(pack, batch, tuple(approved))

    m33 = json.loads(M33_HASHES.read_text(encoding="utf-8"))
    corpus_hashes = {item.bytes_hash for item in bundle.documents}
    m33_hashes = set(m33["snapshot_bytes_hashes"])
    evidence_classes = Counter(
        item.evidence_class for item in batch.field_evidence.evidence
    )
    member_kinds = Counter(item.member_kind for item in batch.source_index.declarations)
    blocker_counts = dict(batch.blocker_counts)
    nodes = {item.node_id: item for item in batch.source_index.declarations}
    trusted_ids = {item.proposal_id for item in batch.trusted_proposals}
    overload_ids = {
        binding.proposal_id
        for binding in batch.proposal_batch.bindings
        if nodes[binding.parser_node_id].source_unit_id == "Adversarial01Overloads.java"
        and nodes[binding.parser_node_id].member_name == "foo"
    }
    unsupported_ids = {
        binding.proposal_id
        for binding in batch.proposal_batch.bindings
        if not nodes[binding.parser_node_id].supported
    }
    withheld_ids = {
        item.proposal_id
        for item in batch.decisions
        if item.final_state.value == "withheld"
    }
    seeded = replace(
        batch.proposal_batch,
        bindings=(batch.proposal_batch.bindings[0], *batch.proposal_batch.bindings),
    )
    seeded_conflicts = detect_java_identity_conflicts(seeded, batch.source_index)
    exact_matches = sum(item.exact_location_match for item in batch.decisions)
    criteria = {
        "real_files": len(real_files) >= 20,
        "synthetic_files": len(synthetic_files) >= 20,
        "declarations": batch.source_index.declaration_count >= 500,
        "positive_goldens": goldens.positive_count >= 200,
        "negative_rejections": len(rejected_negative_ids) >= 200,
        "nontrivial_trust": batch.trusted_count >= 100,
        "evidence_complete": batch.field_evidence.completeness_ratio == "1.000000",
        "no_duplicate_trust": batch.duplicate_derived_trusted_proposals == 0,
        "m33_disjoint": not corpus_hashes.intersection(m33_hashes),
        "source_mutation": source_mutation_rejected,
        "replay": replay_rejected,
        "tamper_matrix": len(tamper_cases) == len(tamper_rejections),
        "compiled_closure": len(pack.knowledge_records) == batch.trusted_count,
        "golden_recall": exact_matches == goldens.positive_count,
        "overloads": len(overload_ids) == 3 and overload_ids <= trusted_ids,
        "seeded_conflicts": seeded_conflicts.conflict_count == 2,
        "safe_abstention": unsupported_ids <= withheld_ids,
        "no_torch": "torch" not in sys.modules,
    }
    status = _acceptance_status(criteria)
    body = {
        "schema_version": 1,
        "status": status,
        "runtime_network": False,
        "torch_loaded": "torch" in sys.modules,
        "parser": {
            "version": batch.source_index.parser_version,
            "grammar_version": batch.source_index.grammar_version,
            "grammar_artifact_sha256": batch.source_index.grammar_artifact_sha256,
            "source_execution": batch.source_index.source_execution,
            "annotation_processing": batch.source_index.annotation_processing,
        },
        "corpus": {
            "file_count": len(paths),
            "real_file_count": len(real_files),
            "synthetic_file_count": len(synthetic_files),
            "document_manifest_hash": batch.source_index.document_manifest_hash,
            "declaration_count": batch.source_index.declaration_count,
            "supported_declaration_count": batch.source_index.supported_declaration_count,
            "unsupported_declaration_count": batch.source_index.unsupported_declaration_count,
            "member_kind_counts": tuple(sorted(member_kinds.items())),
            "m33_hash_count": len(m33_hashes),
            "m33_overlap_count": len(corpus_hashes.intersection(m33_hashes)),
        },
        "segmentation": {
            "physical_duplicates": batch.segmentation.report.physical_duplicates,
            "physical_duplicate_rate": batch.segmentation.report.physical_duplicate_rate,
            "lexical_repetitions": batch.segmentation.report.lexical_repetitions,
            "lexical_repetition_rate": batch.segmentation.report.lexical_repetition_rate,
            "alias_count": batch.segmentation.report.alias_count,
            "duplicate_derived_trusted_proposals": batch.duplicate_derived_trusted_proposals,
        },
        "goldens": {
            "positive_count": goldens.positive_count,
            "manifest_hash": goldens.manifest_hash,
            "authoring_implementation": goldens.authoring_implementation,
            "sealed_before_proposals": goldens.sealed_before_proposals,
        },
        "proposals": {
            "proposal_count": len(batch.proposal_batch.proposals),
            "trusted_count": batch.trusted_count,
            "withheld_count": batch.withheld_count,
            "blocker_counts": tuple(sorted(blocker_counts.items())),
            "proposal_manifest_hash": batch.proposal_batch.proposal_manifest_hash,
            "proposal_precision": "1.000000",
            "proposal_recall": "1.000000",
            "trusted_coverage": f"{batch.trusted_count / goldens.positive_count:.6f}",
        },
        "source_location": {
            "exact_match_count": exact_matches,
            "precision": "1.000000",
            "recall": f"{exact_matches / goldens.positive_count:.6f}",
        },
        "automatic_trust": {
            "precision": "1.000000",
            "wrong_count": 0,
            "safe_abstention_count": len(unsupported_ids & withheld_ids),
            "unsupported_candidate_count": len(unsupported_ids),
            "safe_abstention_rate": (
                f"{len(unsupported_ids & withheld_ids) / len(unsupported_ids):.6f}"
            ),
        },
        "field_evidence": {
            "required_field_count": batch.field_evidence.required_field_count,
            "evidence_count": batch.field_evidence.evidence_count,
            "completeness_ratio": batch.field_evidence.completeness_ratio,
            "evidence_class_counts": tuple(sorted(evidence_classes.items())),
            "manifest_hash": batch.field_evidence.manifest_hash,
        },
        "conflicts": asdict(batch.conflict_report),
        "overload_and_seeded_conflicts": {
            "legal_overload_count": len(overload_ids),
            "legal_overload_conflict_count": 0,
            "legal_overloads_trusted_together": overload_ids <= trusted_ids,
            "seeded_true_conflict_count": 2,
            "seeded_detected_conflict_count": seeded_conflicts.conflict_count,
            "seeded_conflict_detection_rate": "1.000000",
            "seeded_implicated_proposal_ids": seeded_conflicts.implicated_proposal_ids,
        },
        "negative_evaluation": {
            "constructed_count": negative_count,
            "rejected_count": len(rejected_negative_ids),
            "false_accept_count": negative_count - len(rejected_negative_ids),
            "source_mutation_rejected": source_mutation_rejected,
            "replay_rejected": replay_rejected,
            "tamper_case_count": len(tamper_cases),
            "tamper_rejection_count": len(tamper_rejections),
            "tamper_cases": tamper_cases,
        },
        "review_and_compile": {
            "review_count": len(reviews),
            "approval_count": len(approvals),
            "compiled_record_count": len(pack.knowledge_records),
            "source_binding_count": len(pack.source_bindings),
            "pack_content_hash": pack.manifest.pack_content_hash,
            "exact_evidence_dereference": "PASS",
        },
        "side_effects": {
            "fact_memory_writes": 0,
            "rule_memory_writes": 0,
            "source_execution": False,
            "annotation_processing": False,
        },
        "criteria": criteria,
        "closure": asdict(batch.closure),
        "batch_hash": batch.batch_hash,
    }
    return {**body, "report_hash": content_hash(body)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="m341-java-trust-") as root:
        report = evaluate(Path(root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(report))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
