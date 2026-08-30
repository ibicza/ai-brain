from __future__ import annotations

import ast
import inspect
import json
import runpy
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_evidence import (
    build_java_field_evidence_manifest,
    verify_java_field_evidence_manifest,
)
from ai_brain.stage3.acquisition.java_goldens import (
    load_java_golden_manifest,
    verify_java_golden_manifest,
)
from ai_brain.stage3.acquisition.java_pipeline import (
    detect_java_identity_conflicts,
    run_java_trust_pipeline,
    verify_trust_bound_batch,
)
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    ProposalStatus,
    ReviewDecision,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import propose_knowledge, with_status
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.trust import ProposalTrustState
from ai_brain.stage3.acquisition.verification import verify_proposals

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/m341_java/corpus"
GOLDENS = ROOT / "tests/fixtures/m341_java/goldens/sealed_locations.json"
STAMP = "2026-08-30T00:00:00Z"


@pytest.fixture(scope="module")
def java_closure(tmp_path_factory):
    root = tmp_path_factory.mktemp("m341-closure")
    store = AcquisitionStore.open_or_initialize(root / "store")
    paths = tuple(sorted(CORPUS.rglob("*.java"), key=lambda item: item.name))
    bundle = ingest_bundle(
        paths,
        bundle_id="m341-test",
        imported_at=STAMP,
        store=store,
    )
    goldens = load_java_golden_manifest(GOLDENS)
    batch = run_java_trust_pipeline(
        bundle,
        store,
        goldens,
        deterministic_run_id="m341.pytest.v1",
    )
    return store, bundle, goldens, batch


def test_real_public_pipeline_meets_scale_and_trust_thresholds(java_closure):
    store, _bundle, goldens, batch = java_closure
    verify_trust_bound_batch(batch, store)
    assert batch.source_index.declaration_count == 1146
    assert len(batch.proposal_batch.proposals) == 931
    assert goldens.positive_count == 300
    assert batch.trusted_count == 300
    assert batch.withheld_count == 631
    assert batch.field_evidence.required_field_count == 4718
    assert batch.field_evidence.completeness_ratio == "1.000000"


def test_parser_coordinates_overloads_and_unsupported_abstention(java_closure):
    _store, _bundle, _goldens, batch = java_closure
    declarations = batch.source_index.declarations
    clock = next(item for item in declarations if item.member_name == "tickMillis")
    assert (clock.declaration_span.line_start, clock.declaration_span.line_end) == (
        232,
        234,
    )
    overloads = {
        item.erased_jvm_descriptor
        for item in declarations
        if item.source_unit_id == "Adversarial01Overloads.java"
        and item.member_name == "foo"
    }
    assert len(overloads) == 3
    assert "foo(I)Ljava/lang/String;" in overloads
    unsupported = {
        item.unsupported_reason for item in declarations if not item.supported
    }
    assert "unresolved_parameter_type:MissingType" in unsupported
    assert "local_type_member" in unsupported


def test_import_multiline_text_block_and_repeated_occurrence_regressions(
    java_closure,
):
    store, bundle, _goldens, batch = java_closure
    declarations = batch.source_index.declarations
    function = next(
        item
        for item in declarations
        if item.source_unit_id == "Adversarial05FunctionImport.java"
        and item.member_name == "apply"
    )
    assert "Ljava/util/function/Function;" in function.erased_jvm_descriptor
    assert "dev/m341/synthetic/Function" not in function.erased_jvm_descriptor
    multiline = next(
        item
        for item in declarations
        if item.source_unit_id == "Adversarial08Multiline.java"
        and item.member_name == "multiline"
    )
    document = next(
        item for item in bundle.documents if item.document_id == multiline.document_id
    )
    raw = store.get_blob(document.bytes_hash)
    exact = raw[
        multiline.declaration_span.byte_start : multiline.declaration_span.byte_end
    ]
    assert exact.startswith(b"@Deprecated")
    assert exact.endswith(b"}")
    assert multiline.declaration_span.line_start == 4
    assert multiline.declaration_span.line_end == 11
    text_method = next(
        item
        for item in declarations
        if item.source_unit_id == "Adversarial14TextBlocks.java"
        and item.member_name == "text"
    )
    assert text_method.receiver_type == "dev.m341.synthetic.Adversarial14TextBlocks"
    repeated_occurrences = {
        (
            item.document_id,
            item.declaration_span.byte_start,
            item.declaration_span.byte_end,
        )
        for item in declarations
        if item.source_unit_id
        in {"Adversarial03RepeatOne.java", "Adversarial04RepeatTwo.java"}
        and item.member_name == "repeated"
    }
    repeated = tuple(
        item
        for item in batch.segmentation.segments
        if (
            item.document_id,
            item.source_location.byte_start,
            item.source_location.byte_end,
        )
        in repeated_occurrences
    )
    assert len(repeated) == 2
    assert (
        len({(item.document_id, item.source_location.byte_start) for item in repeated})
        == 2
    )


def test_physical_duplicates_are_distinct_from_lexical_repetition(java_closure):
    _store, _bundle, _goldens, batch = java_closure
    report = batch.segmentation.report
    assert report.physical_duplicates == 0
    assert report.alias_count == 0
    assert report.lexical_repetitions >= 1
    assert batch.duplicate_derived_trusted_proposals == 0


def test_java_proposals_cannot_self_assert_verified_authority(java_closure):
    store, bundle, _goldens, batch = java_closure
    proposals = batch.proposal_batch.proposals
    assert {item.status for item in proposals} == {ProposalStatus.PROPOSED}
    assert {item.extraction_method for item in proposals} == {ExtractionMethod.JAVA_AST}
    assert (
        verify_proposals(bundle, batch.segmentation.segments, proposals, store)
        == proposals
    )
    with pytest.raises(ValueError, match="requires source index"):
        propose_knowledge(bundle, batch.segmentation.segments)
    assert (
        "required_fields"
        not in inspect.signature(build_java_field_evidence_manifest).parameters
    )


def test_java_policy_is_selected_by_media_not_domain_tags(tmp_path):
    store = AcquisitionStore.open_or_initialize(tmp_path / "store")
    source = CORPUS / "synthetic/Adversarial01Overloads.java"
    bundle = ingest_bundle(
        (source,),
        bundle_id="tag-independent-java",
        domain_tags=("openjdk", "api"),
        imported_at=STAMP,
        store=store,
    )
    with pytest.raises(ValueError, match="requires source index"):
        propose_knowledge(bundle, ())


def test_evidence_and_golden_tampering_are_recomputed(java_closure):
    store, bundle, goldens, batch = java_closure
    first = batch.field_evidence.evidence[0]
    forged_evidence = replace(
        batch.field_evidence,
        evidence=(
            replace(first, normalized_output="forged"),
            *batch.field_evidence.evidence[1:],
        ),
    )
    with pytest.raises(ValueError):
        verify_java_field_evidence_manifest(
            forged_evidence,
            batch.proposal_batch,
            batch.source_index,
            bundle,
            store,
        )
    forged_golden = replace(
        goldens,
        goldens=(replace(goldens.goldens[0], start_offset=0), *goldens.goldens[1:]),
    )
    with pytest.raises(ValueError):
        verify_java_golden_manifest(forged_golden)


def test_complete_field_evidence_adversarial_matrix(java_closure):
    store, bundle, _goldens, batch = java_closure
    evidence = batch.field_evidence.evidence
    first = evidence[0]
    other = next(item for item in evidence if item.proposal_id != first.proposal_id)

    def sealed(item):
        body = asdict(item)
        body.pop("evidence_hash")
        return replace(item, evidence_hash=content_hash(body))

    def manifest(values, required=None):
        value = replace(
            batch.field_evidence,
            evidence=tuple(values),
            required_field_count=len(values) if required is None else required,
            evidence_count=len(values),
            completeness_ratio="1.000000" if values else "0.000000",
            manifest_hash="",
        )
        body = asdict(value)
        body.pop("manifest_hash")
        return replace(value, manifest_hash=content_hash(body))

    shifted = replace(
        first.source_location,
        byte_start=first.source_location.byte_start + 1,
    )
    mutations = (
        sealed(replace(first, normalized_output="caller supplied")),
        sealed(replace(first, source_location=shifted)),
        sealed(replace(first, parser_node_id="java-node." + "0" * 32)),
        sealed(replace(first, transformation_id="invented")),
        sealed(replace(first, transformation_hash="1" * 64)),
        sealed(replace(first, field_path="synthetic.field")),
        sealed(
            replace(
                first,
                document_id=other.document_id,
                document_bytes_hash=other.document_bytes_hash,
                source_location=other.source_location,
                source_span_hash=other.source_span_hash,
            )
        ),
        sealed(
            replace(
                first,
                proposal_id=other.proposal_id,
                proposal_hash=other.proposal_hash,
            )
        ),
    )
    candidates = [manifest((item, *evidence[1:])) for item in mutations]
    candidates.extend(
        (
            manifest(evidence[1:]),
            manifest((first, first, *evidence[1:])),
            manifest((), required=0),
        )
    )
    for candidate in candidates:
        with pytest.raises(ValueError):
            verify_java_field_evidence_manifest(
                candidate,
                batch.proposal_batch,
                batch.source_index,
                bundle,
                store,
            )


def test_conflicts_implicate_only_bound_proposals_and_overloads_pass(java_closure):
    _store, _bundle, _goldens, batch = java_closure
    assert batch.conflict_report.status == "PASS"
    duplicated = replace(
        batch.proposal_batch,
        bindings=(batch.proposal_batch.bindings[0], *batch.proposal_batch.bindings),
    )
    report = detect_java_identity_conflicts(duplicated, batch.source_index)
    assert report.status == "FAIL"
    assert {item.conflict_kind for item in report.conflicts} == {
        "DUPLICATE_PROPOSAL_BINDING",
        "ONE_PROPOSAL_MULTIPLE_DECLARATIONS",
    }
    assert report.implicated_proposal_ids == (
        batch.proposal_batch.bindings[0].proposal_id,
    )


def test_review_requires_trust_and_forbids_contradictory_java_status(java_closure):
    _store, _bundle, _goldens, batch = java_closure
    proposal = batch.trusted_proposals[0]
    updated, _review, approval = review_proposal(
        proposal,
        reviewer_identity="human",
        reviewer_type=ActorIdentityType.USER,
        decision=ReviewDecision.APPROVE,
        rationale="exact independent golden",
        timestamp=STAMP,
        trust_authorization=batch,
    )
    assert updated.status is ProposalStatus.APPROVED
    assert approval is not None
    with pytest.raises(ValueError, match="contradicts"):
        review_proposal(
            with_status(proposal, ProposalStatus.VERIFIED),
            reviewer_identity="human",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="invalid shortcut",
            timestamp=STAMP,
            trust_authorization=batch,
        )
    withheld = next(
        proposal
        for proposal, decision in zip(
            batch.proposal_batch.proposals, batch.decisions, strict=True
        )
        if decision.final_state is ProposalTrustState.WITHHELD
    )
    with pytest.raises(ValueError, match="withheld"):
        review_proposal(
            withheld,
            reviewer_identity="human",
            reviewer_type=ActorIdentityType.USER,
            decision=ReviewDecision.APPROVE,
            rationale="must fail",
            timestamp=STAMP,
            trust_authorization=batch,
        )


def test_full_closure_rejects_replay_and_hash_tamper(java_closure):
    store, bundle, _goldens, batch = java_closure
    with pytest.raises(ValueError):
        verify_trust_bound_batch(replace(batch, batch_hash="0" * 64), store)
    with pytest.raises(ValueError):
        verify_trust_bound_batch(
            replace(batch, bundle=replace(bundle, bundle_id="replay")), store
        )


def test_golden_author_is_independent_and_reproducible(tmp_path):
    script = ROOT / "scripts/m341_author_java_goldens.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(value.startswith("ai_brain") for value in imported)
    output = tmp_path / "sealed.json"
    subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.read_bytes() == GOLDENS.read_bytes()


def test_acceptance_covers_200_negatives_compile_and_disjointness(tmp_path):
    output = tmp_path / "acceptance.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/m341_java_trust_acceptance.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["corpus"]["real_file_count"] >= 20
    assert report["corpus"]["synthetic_file_count"] >= 20
    assert report["corpus"]["m33_overlap_count"] == 0
    assert report["negative_evaluation"]["constructed_count"] >= 200
    assert report["negative_evaluation"]["false_accept_count"] == 0
    assert report["negative_evaluation"]["tamper_case_count"] == 10
    assert report["negative_evaluation"]["tamper_rejection_count"] == 10
    assert report["review_and_compile"]["compiled_record_count"] == 300
    assert report["review_and_compile"]["source_binding_count"] == 300
    assert report["torch_loaded"] is False
    assert output.read_bytes().endswith(b"\n")
    assert b"\r\n" not in output.read_bytes()


def test_acceptance_cannot_pass_with_zero_trusted_proposals():
    namespace = runpy.run_path(str(ROOT / "scripts/m341_java_trust_acceptance.py"))
    assert namespace["_acceptance_status"]({"trusted_count": False}) == "FAIL"
