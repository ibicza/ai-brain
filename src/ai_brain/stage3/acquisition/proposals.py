from __future__ import annotations

import re
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
from ai_brain.stage3.knowledge_ir.records import (
    ClaimSchemaContent,
    EntityTypeRef,
    KnowledgeKind,
)


def propose_knowledge(
    bundle: SourceBundle,
    segments: tuple[SourceSegment, ...],
    *,
    explicit_trust_stages: bool = False,
) -> tuple[KnowledgeProposal, ...]:
    result = []
    api_context = _api_context(segments) if explicit_trust_stages else {}
    for segment in segments:
        classified = classify_segment(segment)
        if classified is None:
            continue
        kind, method = classified
        try:
            candidate = extract_candidate(segment, kind, method)
        except ValueError:
            continue
        if (
            explicit_trust_stages
            and kind is KnowledgeKind.DEFINITION
            and method.value == "DETERMINISTIC_PATTERN"
        ):
            candidate = replace(
                candidate,
                ambiguity_fields=(),
                status=ProposalStatus.PROPOSED,
            )
        proposal_segment_ids = (segment.segment_id,)
        if (
            explicit_trust_stages
            and kind is KnowledgeKind.CLAIM_SCHEMA
            and isinstance(candidate.content, ClaimSchemaContent)
            and segment.document_id in api_context
        ):
            receiver, context_segment_id = api_context[segment.document_id]
            candidate = replace(
                candidate,
                content=replace(
                    candidate.content,
                    subject_type=EntityTypeRef(_slug(receiver)),
                    receiver_type=receiver,
                ),
                ambiguity_fields=(),
                status=ProposalStatus.PROPOSED,
            )
            proposal_segment_ids = tuple(
                dict.fromkeys((context_segment_id, segment.segment_id))
            )
        body = {
            "proposal_id": "",
            "source_bundle_id": bundle.bundle_id,
            "segment_ids": proposal_segment_ids,
            "proposed_kind": kind,
            "proposed_epistemic_character": candidate.epistemic,
            "proposed_content": candidate.content,
            "proposed_dependencies": candidate.dependencies,
            "proposed_applicability": candidate.applicability,
            "proposed_capabilities": (
                _m33_capabilities(kind, candidate.capabilities)
                if explicit_trust_stages
                else candidate.capabilities
            ),
            "extraction_method": method,
            "status": (
                ProposalStatus.PARSED
                if explicit_trust_stages and candidate.status is ProposalStatus.PROPOSED
                else candidate.status
            ),
            "ambiguity_fields": candidate.ambiguity_fields,
            "compiler_version": SOURCE_COMPILER_VERSION,
            "schema_version": KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
        }
        body["proposal_id"] = f"proposal.{content_hash(body)[:32]}"
        proposal = KnowledgeProposal(**body, proposal_hash=content_hash(body))
        result.append(proposal)
    return tuple(result)


def _m33_capabilities(kind, existing):
    replacement = {
        KnowledgeKind.EQUATION_RULE: ("generic.typed_scalar_equation_solver.v1",),
        KnowledgeKind.TAXONOMY_EDGE: ("generic.taxonomy_query.v1",),
        KnowledgeKind.PART_WHOLE_RELATION: ("generic.taxonomy_query.v1",),
        KnowledgeKind.TEMPORAL_RELATION: ("generic.temporal_query.v1",),
        KnowledgeKind.CLAIM_SCHEMA: ("generic.api_contract_query.v1",),
    }.get(kind, existing)
    return tuple(dict.fromkeys(replacement))


def _api_context(segments):
    result = {}
    pattern = re.compile(r"\b(?:class|interface|record|enum)\s+([A-Za-z_$][\w.$]*)")
    for segment in segments:
        match = pattern.search(segment.canonical_text)
        if match and segment.document_id not in result:
            result[segment.document_id] = (match.group(1), segment.segment_id)
    return result


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.strip().casefold()).strip("-")


def with_status(value: KnowledgeProposal, status: ProposalStatus) -> KnowledgeProposal:
    provisional = replace(value, status=status, proposal_hash="")
    body = asdict(provisional)
    body.pop("proposal_hash")
    return replace(provisional, proposal_hash=content_hash(body))
