"""Production Java proposal extraction from the trust-bearing source index."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_semantics import (
    build_java_claim_content,
    proposal_field_manifest_hash,
)
from ai_brain.stage3.acquisition.java_source_index import JavaSourceIndex
from ai_brain.stage3.acquisition.models import (
    ExtractionMethod,
    KnowledgeProposal,
    ProposalStatus,
    SourceBundle,
)
from ai_brain.stage3.acquisition.segmentation import DeduplicatedSegments
from ai_brain.stage3.acquisition.version import (
    KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
    SOURCE_COMPILER_VERSION,
)
from ai_brain.stage3.knowledge_ir.records import EpistemicCharacter, KnowledgeKind


@dataclass(frozen=True)
class JavaProposalBinding:
    proposal_id: str
    proposal_hash: str
    parser_node_id: str
    segment_id: str
    binding_hash: str


@dataclass(frozen=True)
class JavaProposalBatch:
    bundle_id: str
    bundle_hash: str
    source_index_hash: str
    segmentation_report_hash: str
    proposals: tuple[KnowledgeProposal, ...]
    bindings: tuple[JavaProposalBinding, ...]
    proposal_manifest_hash: str
    proposal_field_manifest_hash: str
    batch_hash: str


def propose_java_knowledge(
    bundle: SourceBundle,
    segmentation: DeduplicatedSegments,
    source_index: JavaSourceIndex,
) -> JavaProposalBatch:
    segment_by_occurrence = {
        (
            item.document_id,
            item.source_location.byte_start,
            item.source_location.byte_end,
        ): item
        for item in segmentation.segments
    }
    proposals = []
    bindings = []
    for declaration in source_index.declarations:
        if declaration.member_kind not in {"method", "constructor"}:
            continue
        segment = segment_by_occurrence.get(
            (
                declaration.document_id,
                declaration.declaration_span.byte_start,
                declaration.declaration_span.byte_end,
            )
        )
        if segment is None:
            raise ValueError("Java declaration has no physical source segment")
        content = build_java_claim_content(declaration)
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
            "extraction_method": ExtractionMethod.JAVA_AST,
            "status": ProposalStatus.PROPOSED,
            "ambiguity_fields": (
                (declaration.unsupported_reason,)
                if declaration.unsupported_reason
                else ()
            ),
            "compiler_version": SOURCE_COMPILER_VERSION,
            "schema_version": KNOWLEDGE_PROPOSAL_SCHEMA_VERSION,
        }
        body["proposal_id"] = f"proposal.{content_hash(body)[:32]}"
        proposal = KnowledgeProposal(**body, proposal_hash=content_hash(body))
        binding_body = {
            "proposal_id": proposal.proposal_id,
            "proposal_hash": proposal.proposal_hash,
            "parser_node_id": declaration.node_id,
            "segment_id": segment.segment_id,
        }
        proposals.append(proposal)
        bindings.append(
            JavaProposalBinding(**binding_body, binding_hash=content_hash(binding_body))
        )
    ordered = tuple(sorted(proposals, key=lambda item: item.proposal_id))
    binding_values = tuple(sorted(bindings, key=lambda item: item.proposal_id))
    manifest = tuple((item.proposal_id, item.proposal_hash) for item in ordered)
    body = {
        "bundle_id": bundle.bundle_id,
        "bundle_hash": bundle.bundle_hash,
        "source_index_hash": source_index.index_hash,
        "segmentation_report_hash": segmentation.report.report_hash,
        "proposals": ordered,
        "bindings": binding_values,
        "proposal_manifest_hash": content_hash(manifest),
        "proposal_field_manifest_hash": content_hash(
            tuple(
                (item.proposal_id, proposal_field_manifest_hash(item.proposed_content))
                for item in ordered
            )
        ),
    }
    return JavaProposalBatch(**body, batch_hash=content_hash(body))
