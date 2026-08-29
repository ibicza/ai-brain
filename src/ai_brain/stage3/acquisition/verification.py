from __future__ import annotations

from dataclasses import asdict, replace

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    KnowledgeProposal,
    ProposalStatus,
    SourceBundle,
    SourceSegment,
)
from ai_brain.stage3.acquisition.proposals import with_status
from ai_brain.stage3.acquisition.segmentation import verify_segments
from ai_brain.stage3.acquisition.version import (
    KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    SOURCE_COMPILER_VERSION,
)
from ai_brain.stage3.knowledge_ir.records import KnowledgeRecord
from ai_brain.stage3.knowledge_ir.validation import record_content_hash, validate_record
from ai_brain.stage3.knowledge_ir.version import UNIVERSAL_KNOWLEDGE_IR_SCHEMA_VERSION


def verify_proposals(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    proposals: tuple[KnowledgeProposal, ...],
    store,
) -> tuple[KnowledgeProposal, ...]:
    verify_segments(bundle, segments, store)
    segment_ids = {item.segment_id for item in segments}
    result = []
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
        status = (
            ProposalStatus.VERIFIED
            if proposal.extraction_method is ExtractionMethod.DETERMINISTIC_STRUCTURED
            else ProposalStatus.REVIEW_REQUIRED
        )
        result.append(with_status(proposal, status))
    return tuple(result)


def _verify_proposal_hash(value: KnowledgeProposal) -> None:
    body = asdict(value)
    digest = body.pop("proposal_hash")
    if content_hash(body) != digest:
        raise ValueError("knowledge proposal hash mismatch")
