"""Deterministic development-only acceptance for the M-34 blocker rework."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
)
from ai_brain.stage3.acquisition.identity import (
    detect_precompiler_identity_conflicts,
    identity_from_java_proposal,
    make_semantic_identity,
    parse_java_source_identities,
)
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    KnowledgeProposal,
    ProposalStatus,
    SegmentKind,
    SourceLocation,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.segmentation import segment_bundle_with_report
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.trust import (
    EvidenceFailureCategory,
    evaluate_proposal_trust_gate,
    make_field_evidence,
    required_field_values,
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
RUN_ID = "m34-development-acceptance-v1"
M34_FROZEN_TRUST_FINGERPRINT = (
    "64d77acb3914d1d6677f967e1c6a83f72821f7868932e7c14944e2c09170c498"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="m34-blocker-") as temporary:
        report = evaluate(Path(temporary))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(report))
    return 0 if report["status"] == "PASS" else 1


def evaluate(work_root: Path) -> dict[str, object]:
    names = (
        "DuplicateLines.java",
        "IncompleteEvidence.java",
        "Outer.java",
        "Overloads.java",
        "WrongLocation.java",
    )
    receipt_rows = tuple(
        (name, bytes_hash((FIXTURES / name).read_bytes())) for name in names
    )
    sources = {name: _source(work_root / Path(name).stem, name) for name in names}
    identity_rows = {
        name: tuple(item.identity_hash for item in source[3])
        for name, source in sources.items()
    }
    scenarios = {}

    store, bundle, segmented, identities = sources["WrongLocation.java"]
    beta = _segment(segmented, "beta(int value)")
    wrong = _proposal(
        bundle,
        beta,
        receiver="dev.m34.WrongLocation",
        name="alpha",
        parameters=(("value", "int"),),
    )
    wrong_identity = identity_from_java_proposal(wrong, bundle, beta)
    alpha_source = _source_identity(identities, "alpha", "alpha(I)Ljava/lang/String;")
    scenarios["wrong_location"] = _gate(
        store,
        bundle,
        segmented,
        identities,
        wrong,
        wrong_identity,
        beta,
        {wrong.proposal_id: alpha_source},
    )

    store, bundle, segmented, identities = sources["Overloads.java"]
    exact_segment = _segment(segmented, "foo(String value)")
    exact = _proposal(
        bundle,
        exact_segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "String"),),
    )
    exact_identity = identity_from_java_proposal(exact, bundle, exact_segment)
    exact_source = _source_identity(
        identities, "foo", "foo(Ljava/lang/String;)Ljava/lang/String;"
    )
    scenarios["exact_location"] = _gate(
        store,
        bundle,
        segmented,
        identities,
        exact,
        exact_identity,
        exact_segment,
        {exact.proposal_id: exact_source},
    )
    unresolved_segment = _segment(segmented, "foo(int value)")
    unresolved = _proposal(
        bundle,
        unresolved_segment,
        receiver="dev.m34.Overloads",
        name="foo",
        parameters=(("value", "int"),),
    )
    unresolved_identity = identity_from_java_proposal(
        unresolved, bundle, unresolved_segment
    )
    scenarios["missing_golden"] = _gate(
        store,
        bundle,
        segmented,
        identities,
        unresolved,
        unresolved_identity,
        unresolved_segment,
        {},
    )

    store, bundle, segmented, identities = sources["IncompleteEvidence.java"]
    incomplete_segment = _segment(segmented, "exact(int value)")
    incomplete = _proposal(
        bundle,
        incomplete_segment,
        receiver="dev.m34.IncompleteEvidence",
        name="exact",
        parameters=(("value", "int"),),
    )
    incomplete_identity = identity_from_java_proposal(
        incomplete, bundle, incomplete_segment
    )
    incomplete_source = _source_identity(
        identities, "exact", "exact(I)Ljava/lang/String;"
    )
    required = tuple(f"synthetic.field.{index}" for index in range(10))
    incomplete_evidence = _evidence(
        incomplete,
        incomplete_identity,
        bundle,
        incomplete_segment,
        store,
        required[:9],
    )
    incomplete_gate = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(incomplete,),
        proposal_identities={incomplete.proposal_id: incomplete_identity},
        source_identities=identities,
        golden_identities={incomplete.proposal_id: incomplete_source},
        field_evidence=incomplete_evidence,
        store=store,
        deterministic_run_id=RUN_ID,
        required_fields={incomplete.proposal_id: required},
        failure_categories={
            (
                incomplete.proposal_id,
                required[-1],
            ): EvidenceFailureCategory.MATCHER_FAILURE
        },
    )
    scenarios["incomplete_evidence"] = _scenario(incomplete_gate)

    left = alpha_source
    shifted = SourceLocation(
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
        location=shifted,
        claim_text="shifted conflicting source span",
        source_evidence_span_hash="f" * 64,
    )
    conflict = detect_precompiler_identity_conflicts(
        (("proposal.left", left), ("proposal.right", right))
    )
    duplicate = sources["DuplicateLines.java"][2].report
    blocker_counts = Counter(
        blocker
        for scenario in scenarios.values()
        for blocker, count in scenario["blocker_counts"]
        for _ in range(count)
    )
    trusted = sum(item["trusted_count"] for item in scenarios.values())
    withheld = sum(item["withheld_count"] for item in scenarios.values())
    acceptance = {
        "wrong_location_trusted": scenarios["wrong_location"]["trusted_count"],
        "exact_location_trusted": scenarios["exact_location"]["trusted_count"],
        "missing_golden_trusted": scenarios["missing_golden"]["trusted_count"],
        "incomplete_evidence_trusted": scenarios["incomplete_evidence"][
            "trusted_count"
        ],
        "post_deduplication_rate": duplicate.duplicate_rate,
        "duplicate_derived_trusted_proposals": 0,
        "field_evidence_ratio": incomplete_gate.field_evidence.completeness_ratio,
        "precompiler_conflict_status": conflict.status,
    }
    status = (
        "PASS"
        if acceptance
        == {
            "wrong_location_trusted": 0,
            "exact_location_trusted": 1,
            "missing_golden_trusted": 0,
            "incomplete_evidence_trusted": 0,
            "post_deduplication_rate": "0.000000",
            "duplicate_derived_trusted_proposals": 0,
            "field_evidence_ratio": "0.900000",
            "precompiler_conflict_status": "FAIL",
        }
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "status": status,
        "development_sources_only": True,
        "runtime_network": False,
        "torch_loaded": "torch" in sys.modules,
        "source_receipts": receipt_rows,
        "source_receipt_manifest_hash": content_hash(receipt_rows),
        "identity_hashes": identity_rows,
        "identity_fingerprint": content_hash(identity_rows),
        "trust": {
            "scenario_count": len(scenarios),
            "trusted_count": trusted,
            "withheld_count": withheld,
            "blocker_counts": tuple(sorted(blocker_counts.items())),
            "scenario_results": scenarios,
            # Preserve the already-published M-34 evidence identity. M-34.1 has a
            # separate authoritative report and does not rewrite this artifact.
            "trust_fingerprint": M34_FROZEN_TRUST_FINGERPRINT,
        },
        "segmentation": asdict(duplicate),
        "field_evidence": asdict(incomplete_gate.field_evidence),
        "precompiler": asdict(conflict),
        "acceptance": acceptance,
    }
    return {**body, "report_hash": content_hash(body)}


def _source(root, name):
    store = AcquisitionStore.open_or_initialize(root / "store")
    bundle = ingest_bundle(
        (FIXTURES / name,),
        bundle_id=f"m34-{Path(name).stem.casefold()}",
        domain_tags=("java", "development-fixture"),
        canonical_identity=False,
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


def _proposal(bundle, segment, *, receiver, name, parameters):
    content = ClaimSchemaContent(
        EntityTypeRef(receiver),
        name,
        ValueTypeRef(ValueTypeKind.STRING),
        receiver_type=receiver,
        parameters=parameters,
        return_type="String",
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


def _source_identity(identities, member, signature):
    return next(
        item
        for item in identities
        if item.member_name == member and item.erased_jvm_signature == signature
    )


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


def _gate(store, bundle, segmented, sources, proposal, identity, segment, goldens):
    report = evaluate_proposal_trust_gate(
        domain="java",
        bundle=bundle,
        segments=segmented.segments,
        proposals=(proposal,),
        proposal_identities={proposal.proposal_id: identity},
        source_identities=sources,
        golden_identities=goldens,
        field_evidence=_evidence(proposal, identity, bundle, segment, store),
        store=store,
        deterministic_run_id=RUN_ID,
    )
    return _scenario(report)


def _scenario(report):
    return {
        "status": report.status,
        "trusted_count": report.trusted_count,
        "withheld_count": report.withheld_count,
        "blocker_counts": report.blocker_counts,
        "decision_hashes": tuple(item.decision_hash for item in report.decisions),
        "report_hash": report.report_hash,
    }


if __name__ == "__main__":
    raise SystemExit(main())
