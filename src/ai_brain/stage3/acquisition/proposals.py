from __future__ import annotations

from dataclasses import asdict, replace

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.classifiers import classify_segment
from ai_brain.stage3.acquisition.extractors import extract_candidate
from ai_brain.stage3.acquisition.models import (
    KnowledgeProposal,
    ProposalStatus,
    SourceBundle,
    SourceSegment,
)
from ai_brain.stage3.acquisition.version import (
    KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    SOURCE_COMPILER_VERSION,
)


def propose_knowledge(
    bundle: SourceBundle, segments: tuple[SourceSegment, ...]
) -> tuple[KnowledgeProposal, ...]:
    result = []
    for segment in segments:
        classified = classify_segment(segment)
        if classified is None:
            continue
        kind, method = classified
        try:
            candidate = extract_candidate(segment, kind, method)
        except ValueError:
            continue
        body = {
            "proposal_id": "",
            "source_bundle_id": bundle.bundle_id,
            "segment_ids": (segment.segment_id,),
            "proposed_kind": kind,
            "proposed_epistemic_character": candidate.epistemic,
            "proposed_content": candidate.content,
            "proposed_dependencies": candidate.dependencies,
            "proposed_applicability": candidate.applicability,
            "proposed_capabilities": candidate.capabilities,
            "extraction_method": method,
            "status": candidate.status,
            "ambiguity_fields": candidate.ambiguity_fields,
            "compiler_version": SOURCE_COMPILER_VERSION,
            "schema_version": KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
        }
        body["proposal_id"] = f"proposal.{content_hash(body)[:32]}"
        proposal = KnowledgeProposal(**body, proposal_hash=content_hash(body))
        result.append(proposal)
    return tuple(result)


def with_status(value: KnowledgeProposal, status: ProposalStatus) -> KnowledgeProposal:
    provisional = replace(value, status=status, proposal_hash="")
    body = asdict(provisional)
    body.pop("proposal_hash")
    return replace(provisional, proposal_hash=content_hash(body))
