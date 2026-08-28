"""Authority-neutral verification for offline compilation receipts."""

from __future__ import annotations

from dataclasses import asdict

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.models import (
    ActorIdentityType,
    EducationalCompilationReceipt,
)
from ai_brain.stage2.education.version import EDUCATIONAL_COMPILATION_POLICY_VERSION
from ai_brain.stage2.facts.canonical import content_hash

COMPILER_IDENTITY = "m291-verified-answer-key-compiler"


def verify_compilation_receipt(
    receipt: EducationalCompilationReceipt,
    service: ChemistryDomainService,
    *,
    graph_hash: str | None = None,
    graph=None,
    spec=None,
) -> None:
    body = asdict(receipt)
    digest = body.pop("receipt_hash")
    if content_hash(body) != digest:
        raise ValueError("educational compilation receipt hash mismatch")
    if (
        receipt.actor_identity_type is not ActorIdentityType.TRUSTED_PROCESS
        or receipt.compiler_identity != COMPILER_IDENTITY
        or receipt.compilation_policy_version != EDUCATIONAL_COMPILATION_POLICY_VERSION
    ):
        raise ValueError("invalid educational compilation authority")
    manifest = service.manifest
    if receipt.chemistry_domain_manifest_hash != manifest["domain_manifest_hash"]:
        raise ValueError("stale educational compilation domain")
    if receipt.fact_memory_snapshot_hash != manifest["fact_memory_snapshot_hash"]:
        raise ValueError("stale educational compilation FactMemory")
    if receipt.source_chain_hash != manifest["source_chain_hash"]:
        raise ValueError("stale educational compilation source chain")
    current = (
        content_hash("chemistry_fact_lookup_v1")
        if receipt.tool_id == "chemistry_fact_lookup"
        else service.registry.descriptor(receipt.tool_id).implementation_manifest_hash
    )
    if receipt.tool_implementation_manifest_hash != current:
        raise ValueError("stale educational compilation tool")
    if graph_hash is not None and receipt.educational_graph_hash != graph_hash:
        raise ValueError("compilation receipt references another graph")
    if graph is not None:
        expected_request_hash = content_hash(
            receipt.canonical_arguments
            if receipt.tool_id == "chemistry_fact_lookup"
            else {
                "tool_id": receipt.tool_id,
                "arguments": receipt.canonical_arguments,
            }
        )
        if (
            receipt.educational_graph_hash != graph.graph_hash
            or receipt.exact_result_hash != graph.source_result_hash
            or receipt.knowledge_snapshot_hash != graph.knowledge_snapshot_hash
            or receipt.tool_implementation_manifest_hash
            != (
                content_hash("chemistry_fact_lookup_v1")
                if receipt.tool_id == "chemistry_fact_lookup"
                else graph.tool_implementation_hash
            )
            or graph.request_hash != expected_request_hash
        ):
            raise ValueError("compilation receipt semantic dependency mismatch")
    if spec is not None and receipt.exercise_spec_hash != spec.spec_hash:
        raise ValueError("compilation receipt references another exercise spec")
