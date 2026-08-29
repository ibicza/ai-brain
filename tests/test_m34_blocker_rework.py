from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.compiler import compile_provisional_pack
from ai_brain.stage3.acquisition.identity import (
    IdentityBlocker,
    IdentityMatch,
    PrecompilerIdentityConflict,
    compare_identities,
    detect_precompiler_identity_conflicts,
    identity_from_java_proposal,
    make_semantic_identity,
    match_java_source_location,
    parse_java_source_identities,
    require_precompiler_identity_closure,
)
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    KnowledgeProposal,
    ProposalApproval,
    ProposalStatus,
    SegmentKind,
    SourceLocation,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.proposals import with_status
from ai_brain.stage3.acquisition.segmentation import (
    DuplicateSegmentGateError,
    require_unique_segments,
    segment_bundle_with_report,
)
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.trust import (
    EvidenceFailureCategory,
    ProposalTrustState,
    TrustBlockerReason,
    evaluate_proposal_trust_gate,
    make_field_evidence,
    required_field_values,
    verify_trust_gate_report,
)
from ai_brain.stage3.acquisition.version import (
    KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    SOURCE_COMPILER_VERSION,
)
from ai_brain.stage3.knowledge_ir.records import (
    ClaimSchemaContent,
    EntityTypeRef,
    EpistemicCharacter,
    KnowledgeKind,
    ValueTypeKind,
    ValueTypeRef,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/m34_blocker"
STAMP = "2026-08-30T00:00:00Z"
RUN_ID = "m34-development-regression-v1"


def _source(tmp_path, name):
    store = AcquisitionStore.open_or_initialize(tmp_path / f"store-{name}")
    bundle = ingest_bundle(
        (FIXTURES / name,),
        bundle_id=f"m34-{Path(name).stem.casefold()}",
        domain_tags=("java", "development-fixture"),
        imported_at=STAMP,
        version="development-v1",
        store=store,
    )
    segmented = segment_bundle_with_report(bundle, store)
    document = bundle.documents[0]
    identities = parse_java_source_identities(
        document, store.get_blob(document.bytes_hash)
    )
    return store, bundle, segmented, identities


def _segment(segmented, marker):
    return next(
        item
        for item in segmented.segments
        if item.kind is not SegmentKind.DOCUMENT and marker in item.canonical_text
    )


def _proposal(bundle, segment, *, receiver, name, parameters, returns="String"):
    content = ClaimSchemaContent(
        EntityTypeRef(receiver),
        name,
        ValueTypeRef(ValueTypeKind.STRING),
        receiver_type=receiver,
        parameters=parameters,
        return_type=returns,
    )
    body = {
        "proposal_id": "",
        "source_bundle_id": bundle.bundle_id,
        "segment_ids": (segment.segment_id,),
        "proposed_kind": KnowledgeKind.CLAIM_SCHEMA,
        "proposed_epistemic_character": EpistemicCharacter.NORMATIVE,
        "proposed_content": content,
        "proposed_dependencies": (),
        "proposed_applicability": (),
        "proposed_capabilities": (),
        "extraction_method": ExtractionMethod.DETERMINISTIC_STRUCTURED,
        "status": ProposalStatus.PROPOSED,
        "ambiguity_fields": (),
        "compiler_version": SOURCE_COMPILER_VERSION,
        "schema_version": KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    }
    body["proposal_id"] = f"proposal.{content_hash(body)[:32]}"
    return KnowledgeProposal(**body, proposal_hash=content_hash(body))


def _evidence(proposal, identity, bundle, segment, store, paths=None):
    document = bundle.documents[0]
    raw = store.get_blob(document.bytes_hash)
    values = dict(required_field_values(proposal))
    selected = paths or tuple(sorted(values))
    return tuple(
        make_field_evidence(
            proposal=proposal,
            field_path=path,
            document_id=document.document_id,
            document_bytes_hash=document.bytes_hash,
            source_location=segment.source_location,
            raw=raw,
            normalized_value=values.get(path, '"value"'),
            semantic_identity_hash=identity.identity_hash,
        )
        for path in selected
    )


def _source_identity(identities, *, member, signature, nested=()):
    return next(
        item
        for item in identities
        if item.member_name == member
        and item.erased_jvm_signature == signature
        and item.nested_type_path == nested
    )


def test_java_false_trust_is_blocked_when_claim_is_attached_to_wrong_location(
    tmp_path,
):
    store, bundle, segmented, source_identities = _source(
        tmp_path, "WrongLocation.java"
    )
    wrong_segment = _segment(segmented, "beta(int value)")
    proposal = _proposal(
        bundle,
        wrong_segment,
        receiver="dev.m34.WrongLocation",
        name="alpha",
        parameters=(("value", "int"),),
    )
    proposal_identity = identity_from_java_proposal(proposal, bundle, wrong_segment)
    golden = _source_identity(
        source_identities,
        member="alpha",
        signature="alpha(I)Ljava/lang/String;",
    )
    report = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(proposal,),
        proposal_identities={proposal.proposal_id: proposal_identity},
        source_identities=source_identities,
        golden_identities={proposal.proposal_id: golden},
        field_evidence=_evidence(
            proposal, proposal_identity, bundle, wrong_segment, store
        ),
        store=store,
        deterministic_run_id=RUN_ID,
    )
    verify_trust_gate_report(report)
    assert report.trusted_count == 0
    assert report.decisions[0].final_state is ProposalTrustState.WITHHELD
    assert report.decisions[0].blocker_reason in {
        TrustBlockerReason.LOCATION_MISMATCH,
        TrustBlockerReason.CONFLICTING_IDENTITY,
    }


def test_java_overloads_require_erased_signature_not_name_only(tmp_path):
    _, bundle, segmented, identities = _source(tmp_path, "Overloads.java")
    expected = {
        "foo(I)Ljava/lang/String;",
        "foo(Ljava/lang/String;)Ljava/lang/String;",
        "foo(II)Ljava/lang/String;",
    }
    overloads = tuple(item for item in identities if item.member_name == "foo")
    assert {item.erased_jvm_signature for item in overloads} == expected
    string_source = _source_identity(
        identities,
        member="foo",
        signature="foo(Ljava/lang/String;)Ljava/lang/String;",
    )
    segment = _segment(segmented, "foo(String value)")
    proposal = _proposal(
        bundle,
        segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "String"),),
    )
    exact = identity_from_java_proposal(proposal, bundle, segment)
    assert compare_identities(exact, string_source) is IdentityMatch.EXACT
    assert (
        match_java_source_location(
            exact, identities, golden_identity=string_source
        ).blocker_reason
        is None
    )
    name_only = make_semantic_identity(
        domain=exact.domain,
        source_document_id=exact.source_document_id,
        source_snapshot_hash=exact.source_snapshot_hash,
        source_unit_id=exact.source_unit_id,
        package_name=exact.package_name,
        top_level_type_name=exact.top_level_type_name,
        nested_type_path=exact.nested_type_path,
        member_kind=exact.member_kind,
        member_name=exact.member_name,
        erased_jvm_signature=None,
        location=segment.source_location,
        claim_text=segment.canonical_text,
        source_evidence_span_hash=segment.source_span_hash,
    )
    blocked = match_java_source_location(
        name_only, identities, golden_identity=string_source
    )
    assert blocked.status is IdentityMatch.CONFLICT
    assert blocked.blocker_reason is IdentityBlocker.CONFLICTING_IDENTITY


def test_nested_type_path_is_part_of_java_identity(tmp_path):
    _, _, segmented, identities = _source(tmp_path, "Outer.java")
    inner = _source_identity(
        identities,
        member="same",
        signature="same(I)Ljava/lang/String;",
        nested=("Inner",),
    )
    segment = _segment(segmented, 'return "inner"')
    wrong_nested = make_semantic_identity(
        domain=inner.domain,
        source_document_id=inner.source_document_id,
        source_snapshot_hash=inner.source_snapshot_hash,
        source_unit_id=inner.source_unit_id,
        package_name=inner.package_name,
        top_level_type_name=inner.top_level_type_name,
        nested_type_path=("OtherInner",),
        member_kind=inner.member_kind,
        member_name=inner.member_name,
        erased_jvm_signature=inner.erased_jvm_signature,
        location=segment.source_location,
        claim_text=segment.canonical_text,
        source_evidence_span_hash=segment.source_span_hash,
    )
    result = match_java_source_location(wrong_nested, identities, golden_identity=inner)
    assert result.blocker_reason in {
        IdentityBlocker.LOCATION_MISMATCH,
        IdentityBlocker.CONFLICTING_IDENTITY,
    }


def test_duplicate_segment_gate_deduplicates_ingestion_and_rejects_raw_duplicates(
    tmp_path,
):
    _, _, segmented, _ = _source(tmp_path, "DuplicateLines.java")
    assert segmented.report.duplicate_rate == "0.000000"
    assert float(segmented.report.input_duplicate_rate) > 0.02
    assert segmented.report.alias_count == 4
    repeated = _segment(segmented, "repeated documentation sentence")
    raw_duplicates = tuple(
        replace(
            repeated,
            segment_id=f"duplicate.{index}",
            ordinal=index,
            segment_hash=f"{index:064x}",
        )
        for index in range(5)
    )
    with pytest.raises(DuplicateSegmentGateError) as captured:
        require_unique_segments(raw_duplicates)
    assert float(captured.value.report.input_duplicate_rate) > 0.02
    assert captured.value.report.input_exact_duplicates == 4


def test_java_field_evidence_9_of_10_forces_zero_trust_and_lists_missing(tmp_path):
    store, bundle, segmented, identities = _source(tmp_path, "IncompleteEvidence.java")
    segment = _segment(segmented, "exact(int value)")
    proposal = _proposal(
        bundle,
        segment,
        receiver="dev.m34.IncompleteEvidence",
        name="exact",
        parameters=(("value", "int"),),
    )
    identity = identity_from_java_proposal(proposal, bundle, segment)
    golden = _source_identity(
        identities,
        member="exact",
        signature="exact(I)Ljava/lang/String;",
    )
    required = tuple(f"synthetic.field.{index}" for index in range(10))
    report = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(proposal,),
        proposal_identities={proposal.proposal_id: identity},
        source_identities=identities,
        golden_identities={proposal.proposal_id: golden},
        field_evidence=_evidence(
            proposal, identity, bundle, segment, store, required[:9]
        ),
        store=store,
        deterministic_run_id=RUN_ID,
        required_fields={proposal.proposal_id: required},
        failure_categories={
            (
                proposal.proposal_id,
                required[-1],
            ): EvidenceFailureCategory.MATCHER_FAILURE
        },
    )
    assert report.field_evidence.required_count == 10
    assert report.field_evidence.evidence_count == 9
    assert report.field_evidence.completeness_ratio == "0.900000"
    assert report.field_evidence.missing[0].field_path == required[-1]
    assert (
        report.field_evidence.missing[0].failure_category
        is EvidenceFailureCategory.MATCHER_FAILURE
    )
    assert report.trusted_count == 0
    assert report.status == "FAIL"
    assert (
        report.decisions[0].blocker_reason is TrustBlockerReason.MISSING_FIELD_EVIDENCE
    )


def test_precompiler_conflict_is_deterministic_and_prevents_pack_creation(
    tmp_path,
):
    store, bundle, segmented, identities = _source(tmp_path, "WrongLocation.java")
    left = _source_identity(
        identities,
        member="alpha",
        signature="alpha(I)Ljava/lang/String;",
    )
    shifted_location = SourceLocation(
        left.start_offset + 1,
        left.end_offset + 1,
        left.start_line + 1,
        left.end_line + 1,
        (),
    )
    right = make_semantic_identity(
        domain=left.domain,
        source_document_id=left.source_document_id,
        source_snapshot_hash=left.source_snapshot_hash,
        source_unit_id=left.source_unit_id,
        package_name=left.package_name,
        top_level_type_name=left.top_level_type_name,
        nested_type_path=left.nested_type_path,
        member_kind=left.member_kind,
        member_name=left.member_name,
        erased_jvm_signature=left.erased_jvm_signature,
        location=shifted_location,
        claim_text="shifted conflicting source span",
        source_evidence_span_hash="f" * 64,
    )
    proposal_identities = (("proposal.left", left), ("proposal.right", right))
    first = detect_precompiler_identity_conflicts(proposal_identities)
    second = detect_precompiler_identity_conflicts(tuple(reversed(proposal_identities)))
    assert first.status == "FAIL"
    assert first.report_hash == second.report_hash
    assert first.conflicts[0].conflict_kind == "SAME_IDENTITY_DIFFERENT_SOURCE_SPANS"
    output = tmp_path / "must-not-build"
    with pytest.raises(PrecompilerIdentityConflict):
        require_precompiler_identity_closure(proposal_identities)
    assert not output.exists()
    alpha_segment = _segment(segmented, "alpha(int value)")
    left_proposal = _proposal(
        bundle,
        alpha_segment,
        receiver="dev.m34.WrongLocation",
        name="alpha",
        parameters=(("value", "int"),),
    )
    provisional = replace(
        left_proposal,
        proposal_id=f"{left_proposal.proposal_id}.conflict",
        proposal_hash="",
    )
    row = asdict(provisional)
    row.pop("proposal_hash")
    right_proposal = replace(provisional, proposal_hash=content_hash(row))
    gate = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(left_proposal, right_proposal),
        proposal_identities={
            left_proposal.proposal_id: left,
            right_proposal.proposal_id: right,
        },
        source_identities=identities,
        golden_identities={
            left_proposal.proposal_id: left,
            right_proposal.proposal_id: left,
        },
        field_evidence=(),
        store=store,
        deterministic_run_id=RUN_ID,
        required_fields={
            left_proposal.proposal_id: (),
            right_proposal.proposal_id: (),
        },
    )
    assert gate.status == "FAIL"
    assert gate.precompiler.status == "FAIL"
    with pytest.raises(PrecompilerIdentityConflict):
        compile_provisional_pack(
            bundle,
            segmented.segments,
            (left_proposal, right_proposal),
            (),
            output,
            domain_id="java-development",
            trust_gate_report=gate,
        )
    assert not output.exists()


def test_unresolved_identity_abstains_with_no_trusted_or_installed_answer(tmp_path):
    store, bundle, segmented, identities = _source(tmp_path, "Overloads.java")
    segment = _segment(segmented, "foo(int value)")
    proposal = _proposal(
        bundle,
        segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "int"),),
    )
    identity = identity_from_java_proposal(proposal, bundle, segment)
    report = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(proposal,),
        proposal_identities={proposal.proposal_id: identity},
        source_identities=identities,
        golden_identities={},
        field_evidence=_evidence(proposal, identity, bundle, segment, store),
        store=store,
        deterministic_run_id=RUN_ID,
    )
    verify_trust_gate_report(report)
    assert report.trusted_count == 0
    assert report.withheld_count == 1
    assert report.decisions[0].final_state is ProposalTrustState.WITHHELD
    assert report.decisions[0].blocker_reason is TrustBlockerReason.GOLDEN_REQUIRED
    approved = with_status(proposal, ProposalStatus.APPROVED)
    approval_body = {
        "proposal_id": approved.proposal_id,
        "original_proposal_hash": proposal.proposal_hash,
        "approved_proposal_hash": approved.proposal_hash,
        "review_hash": "m34-safe-abstention-review",
    }
    approval = ProposalApproval(
        **approval_body, approval_hash=content_hash(approval_body)
    )
    output = tmp_path / "must-not-install"
    with pytest.raises(ValueError, match="outside trusted proposal closure"):
        compile_provisional_pack(
            bundle,
            segmented.segments,
            (approved,),
            (approval,),
            output,
            domain_id="java-development",
            trust_gate_report=report,
        )
    assert not output.exists()


def test_exact_java_identity_uses_only_legal_trust_transition_path(tmp_path):
    store, bundle, segmented, identities = _source(tmp_path, "Overloads.java")
    segment = _segment(segmented, "foo(String value)")
    proposal = _proposal(
        bundle,
        segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "String"),),
    )
    identity = identity_from_java_proposal(proposal, bundle, segment)
    golden = _source_identity(
        identities,
        member="foo",
        signature="foo(Ljava/lang/String;)Ljava/lang/String;",
    )
    report = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(proposal,),
        proposal_identities={proposal.proposal_id: identity},
        source_identities=identities,
        golden_identities={proposal.proposal_id: golden},
        field_evidence=_evidence(proposal, identity, bundle, segment, store),
        store=store,
        deterministic_run_id=RUN_ID,
    )
    verify_trust_gate_report(report)
    decision = report.decisions[0]
    assert report.trusted_count == 1
    assert decision.final_state is ProposalTrustState.TRUSTED
    assert tuple(item.next_state for item in decision.receipts) == (
        ProposalTrustState.SOURCE_EVIDENCE_FOUND,
        ProposalTrustState.IDENTITY_RESOLVED,
        ProposalTrustState.GOLDEN_LOCATION_MATCHED,
        ProposalTrustState.TRUSTED,
    )
    assert all(item.deterministic_run_id == RUN_ID for item in decision.receipts)
    assert content_hash(asdict(report))


def test_development_acceptance_is_byte_deterministic_and_cross_platform_bound(
    tmp_path,
):
    outputs = (tmp_path / "first.json", tmp_path / "second.json")
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/m34_blocker_acceptance.py"),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    report = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["source_receipt_manifest_hash"] == (
        "46428bf978ba6a16b1f2cead349b3acf38532940ef86c764149b4834769d99ab"
    )
    assert report["identity_fingerprint"] == (
        "b37e4577be2af12f21a528fdfae42aab2a0347fd33c59b7dc18f7186d57d7f7b"
    )
    assert report["trust"]["trust_fingerprint"] == (
        "64d77acb3914d1d6677f967e1c6a83f72821f7868932e7c14944e2c09170c498"
    )
    assert report["precompiler"]["report_hash"] == (
        "1802f49837ebf943870c99b6ac55fec947ee8b30e8302b96046cc77d81e3022b"
    )


def test_java_gate_reparses_source_bytes_and_compiler_rejects_missing_report(tmp_path):
    store, bundle, segmented, identities = _source(tmp_path, "Overloads.java")
    segment = _segment(segmented, "foo(int value)")
    proposal = _proposal(
        bundle,
        segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "int"),),
    )
    identity = identity_from_java_proposal(proposal, bundle, segment)
    tampered = make_semantic_identity(
        domain=identities[0].domain,
        source_document_id=identities[0].source_document_id,
        source_snapshot_hash=identities[0].source_snapshot_hash,
        source_unit_id=identities[0].source_unit_id,
        package_name=identities[0].package_name,
        top_level_type_name=identities[0].top_level_type_name,
        nested_type_path=identities[0].nested_type_path,
        member_kind=identities[0].member_kind,
        member_name="forged",
        erased_jvm_signature=identities[0].erased_jvm_signature,
        location=SourceLocation(
            identities[0].start_offset,
            identities[0].end_offset,
            identities[0].start_line,
            identities[0].end_line,
            (),
        ),
        claim_text="forged parsed identity",
        source_evidence_span_hash=identities[0].source_evidence_span_hash,
    )
    with pytest.raises(ValueError, match="parsed source bytes"):
        evaluate_proposal_trust_gate(
            domain="java",
            bundle=bundle,
            segments=segmented.segments,
            proposals=(proposal,),
            proposal_identities={proposal.proposal_id: identity},
            source_identities=(tampered, *identities[1:]),
            golden_identities={},
            field_evidence=_evidence(proposal, identity, bundle, segment, store),
            store=store,
            deterministic_run_id=RUN_ID,
        )
    output = tmp_path / "no-report-pack"
    with pytest.raises(ValueError, match="trust gate report"):
        compile_provisional_pack(
            bundle,
            segmented.segments,
            (),
            (),
            output,
            domain_id="java-development",
        )
    assert not output.exists()
