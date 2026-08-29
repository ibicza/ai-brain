from __future__ import annotations

from dataclasses import asdict, replace

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.evidence import verify_field_evidence
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    FieldSourceEvidence,
    KnowledgeProposal,
    ProposalStatus,
    ReviewDecision,
    SourceBundle,
    SourceSegment,
)
from ai_brain.stage3.acquisition.proposals import with_status
from ai_brain.stage3.acquisition.review import review_proposal
from ai_brain.stage3.acquisition.segmentation import verify_segments
from ai_brain.stage3.acquisition.version import (
    KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    SOURCE_COMPILER_VERSION,
)
from ai_brain.stage3.knowledge_ir.records import KnowledgeRecord
from ai_brain.stage3.knowledge_ir.validation import record_content_hash, validate_record
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION

AUTOMATIC_SOURCE_VERIFIER_ID = "m33.exact-source-entailment-verifier.v1"


def verify_proposals(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    store,
    *,
    field_evidence: tuple[FieldSourceEvidence, ...] | None = None,
) -> tuple[KnowledgeProposal, ...]:
    verify_segments(bundle, segments, store)
    segment_ids = {item.segment_id for item in segments}
    result = []
    evidence_report = (
        verify_field_evidence(bundle, segments, proposals, field_evidence, store)
        if field_evidence is not None
        else None
    )
    evidence_keys = (
        {(item.proposal_id, item.field_path) for item in field_evidence}
        if field_evidence is not None
        else set()
    )
    for proposal in proposals:
        _verify_proposal_hash(proposal)
        if (
            proposal.source_bundle_id != bundle.bundle_id
            or not set(proposal.segment_ids) <= segment_ids
        ):
            raise ValueError("proposal source closure is incomplete")
        if (
            proposal.compiler_version != SOURCE_COMPILER_VERSION
            or proposal.schema_version != KNOWLEDGE_PROPOSAL_SCHEMA_VERSION
        ):
            raise ValueError("proposal compiler or schema mismatch")
        if proposal.extraction_method is ExtractionMethod.ASSISTIVE_MODEL_PROPOSAL:
            if proposal.status is ProposalStatus.VERIFIED:
                raise ValueError("assistive proposal cannot mark itself verified")
            result.append(with_status(proposal, ProposalStatus.REVIEW_REQUIRED))
            continue
        if proposal.ambiguity_fields or proposal.status in {
            ProposalStatus.REVIEW_REQUIRED,
            ProposalStatus.NEEDS_NEW_CAPABILITY,
            ProposalStatus.CONFLICT,
        }:
            result.append(
                with_status(
                    proposal,
                    proposal.status
                    if proposal.status is not ProposalStatus.PROPOSED
                    else ProposalStatus.REVIEW_REQUIRED,
                )
            )
            continue
        record = KnowledgeRecord(
            proposal.proposal_id,
            bundle.bundle_id,
            proposal.proposed_kind,
            UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION,
            proposal.proposed_epistemic_character,
            proposal.segment_ids,
            proposal.proposed_dependencies,
            proposal.proposed_applicability,
            proposal.proposed_capabilities,
            bundle.created_at,
            proposal.proposed_content,
            "",
        )
        record = replace(record, content_hash=record_content_hash(record))
        validate_record(record)
        if field_evidence is None:
            # Exact M-32 compatibility. M-33 callers must pass field evidence.
            status = (
                ProposalStatus.VERIFIED
                if proposal.extraction_method
                is ExtractionMethod.DETERMINISTIC_STRUCTURED
                else ProposalStatus.REVIEW_REQUIRED
            )
        else:
            from ai_brain.stage3.acquisition.evidence import required_field_paths

            complete = all(
                (proposal.proposal_id, path) in evidence_keys
                for path in required_field_paths(proposal)
            )
            status = (
                ProposalStatus.SOURCE_ENTAILED
                if complete
                else ProposalStatus.STRUCTURE_VERIFIED
            )
        result.append(with_status(proposal, status))
    if evidence_report is not None and evidence_report["evidence_count"] != len(
        field_evidence
    ):
        raise ValueError("field evidence verification count mismatch")
    return tuple(result)


def _verify_proposal_hash(value: KnowledgeProposal) -> None:
    body = asdict(value)
    digest = body.pop("proposal_hash")
    if content_hash(body) != digest:
        raise ValueError("knowledge proposal hash mismatch")


def corroborate_source_entailed(
    proposals: tuple[KnowledgeProposal, ...],
    evidence: tuple[FieldSourceEvidence, ...],
) -> tuple[KnowledgeProposal, ...]:
    """Mark identical normalized content supported by independent documents."""

    documents = {
        item.proposal_id: {
            value.document_id
            for value in evidence
            if value.proposal_id == item.proposal_id
        }
        for item in proposals
    }
    groups: dict[str, list[KnowledgeProposal]] = {}
    for proposal in proposals:
        if proposal.status is ProposalStatus.SOURCE_ENTAILED:
            groups.setdefault(
                content_hash(asdict(proposal.proposed_content)), []
            ).append(proposal)
    corroborated = {
        proposal.proposal_id
        for group in groups.values()
        if len(group) > 1
        and len(set().union(*(documents[item.proposal_id] for item in group))) > 1
        for proposal in group
    }
    return tuple(
        with_status(item, ProposalStatus.CROSS_SOURCE_CORROBORATED)
        if item.proposal_id in corroborated
        else item
        for item in proposals
    )


def approve_exact_source_entailed(
    proposal: KnowledgeProposal,
    *,
    timestamp: str,
):
    if proposal.status not in {
        ProposalStatus.SOURCE_ENTAILED,
        ProposalStatus.CROSS_SOURCE_CORROBORATED,
    }:
        raise ValueError("automatic approval requires exact source entailment")
    return review_proposal(
        proposal,
        reviewer_identity=AUTOMATIC_SOURCE_VERIFIER_ID,
        reviewer_type=ActorIdentityType.TRUSTED_PROCESS,
        decision=ReviewDecision.APPROVE,
        rationale="Exact field evidence and typed source-entailment checks passed",
        timestamp=timestamp,
    )
