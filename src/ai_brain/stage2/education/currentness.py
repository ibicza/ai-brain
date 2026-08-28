"""Bounded live dependency-currentness checks shared by runtime and replay."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.domains.chemistry.models import ChemistryReplayStatus
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.education.compilation_receipts import verify_compilation_receipt
from ai_brain.stage2.education.exercise_generation import verify_exercise_instance
from ai_brain.stage2.education.models import EducationalReplayStatus, GraphNodeKind
from ai_brain.stage2.education.version import (
    GRADING_SCHEMA_VERSION,
    HINT_POLICY_VERSION,
)
from ai_brain.stage2.facts.models import (
    ClaimStatus,
    EvidenceConflictState,
    SourceStatus,
)


@dataclass(frozen=True)
class EducationalCurrentnessResult:
    status: EducationalReplayStatus

    @property
    def current(self) -> bool:
        return self.status is EducationalReplayStatus.CURRENT


class EducationalIntegrityError(ValueError):
    """Typed fail-closed result safe for learner-facing exception surfaces."""

    def __init__(self, status: EducationalReplayStatus) -> None:
        self.status = status
        super().__init__(status.value)


def evaluate_entry_currentness(service, entry) -> EducationalCurrentnessResult:
    return evaluate_dependency_currentness(
        service,
        entry.graph,
        entry.compilation_receipt,
        entry.internal_instance,
        entry.exercise_spec,
    )


def evaluate_dependency_currentness(service, graph, receipt, instance, spec):
    manifest = service.manifest
    if graph.domain_version != manifest["domain_version"]:
        return _result(EducationalReplayStatus.STALE_DOMAIN)
    if receipt.chemistry_domain_manifest_hash != manifest["domain_manifest_hash"]:
        return _result(EducationalReplayStatus.STALE_DOMAIN)
    if graph.fact_memory_snapshot_hash != manifest["fact_memory_snapshot_hash"]:
        return _result(EducationalReplayStatus.STALE_FACT_MEMORY)
    if receipt.fact_memory_snapshot_hash != manifest["fact_memory_snapshot_hash"]:
        return _result(EducationalReplayStatus.STALE_FACT_MEMORY)
    if (
        graph.source_chain_hash != manifest["source_chain_hash"]
        or receipt.source_chain_hash != manifest["source_chain_hash"]
    ):
        return _result(EducationalReplayStatus.STALE_SOURCE_CHAIN)
    if receipt.exact_result_hash != graph.source_result_hash:
        return _result(EducationalReplayStatus.STALE_COMPILATION_RECEIPT)
    if receipt.educational_graph_hash != graph.graph_hash:
        return _result(EducationalReplayStatus.STALE_COMPILATION_RECEIPT)
    if receipt.knowledge_snapshot_hash != graph.knowledge_snapshot_hash:
        return _result(EducationalReplayStatus.STALE_COMPILATION_RECEIPT)
    try:
        verify_compilation_receipt(
            receipt,
            service,
            graph_hash=graph.graph_hash,
            graph=graph,
            spec=spec,
        )
    except ValueError as error:
        message = str(error).casefold()
        if "tool" in message:
            return _result(EducationalReplayStatus.STALE_TOOL)
        if "factmemory" in message:
            return _result(EducationalReplayStatus.STALE_FACT_MEMORY)
        if "source chain" in message:
            return _result(EducationalReplayStatus.STALE_SOURCE_CHAIN)
        if "domain" in message:
            return _result(EducationalReplayStatus.STALE_DOMAIN)
        return _result(EducationalReplayStatus.STALE_COMPILATION_RECEIPT)
    source_status = replay_source_currentness(graph, service)
    if source_status is not EducationalReplayStatus.CURRENT:
        return _result(source_status)
    try:
        verify_exercise_instance(instance, spec, graph)
        from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
            ChemistryEducationAdapter,
        )

        ChemistryEducationAdapter(service).verify_graph(graph)
    except (KeyError, TypeError, ValueError):
        return _result(EducationalReplayStatus.INVALID_GRAPH)
    if not _answer_key_matches(instance, graph):
        return _result(EducationalReplayStatus.STALE_ANSWER_KEY)
    if GRADING_SCHEMA_VERSION != 3:
        return _result(EducationalReplayStatus.STALE_GRADING_POLICY)
    if HINT_POLICY_VERSION != "3.0":
        return _result(EducationalReplayStatus.STALE_HINT_POLICY)
    return _result(EducationalReplayStatus.CURRENT)


def require_current(result: EducationalCurrentnessResult) -> None:
    if not result.current:
        raise EducationalIntegrityError(result.status)


def replay_source_currentness(graph, service) -> EducationalReplayStatus:
    if graph.source_result_type.startswith("ChemistryResultBundle:"):
        status = replay_chemistry_result(
            graph.source_result_artifact,
            service.memory,
            service.manifest,
        )
        return CHEMISTRY_STATUS_MAP.get(
            status, EducationalReplayStatus.INVALID_SOURCE_RESULT
        )
    try:
        evidence_hashes = set()
        source_hashes = set()
        for claim_id in graph.claim_ids:
            try:
                state = service.memory.get_claim_state(claim_id)
            except (KeyError, TypeError, ValueError):
                return EducationalReplayStatus.STALE_CLAIM
            if state.status in {ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED}:
                return EducationalReplayStatus.STALE_CLAIM
            if (
                state.status not in {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED}
                or state.evidence_conflict_state == EvidenceConflictState.CONTESTED
                or state.contradicting_evidence_ids
            ):
                return EducationalReplayStatus.STALE_CLAIM
            for evidence_id in state.supporting_evidence_ids:
                try:
                    evidence = service.memory.verify_evidence(evidence_id)
                except (KeyError, TypeError, ValueError):
                    return EducationalReplayStatus.STALE_EVIDENCE
                evidence_hashes.add(evidence.evidence_hash)
                try:
                    source = service.memory.get_source_state(evidence.source_id)
                except (KeyError, TypeError, ValueError):
                    return EducationalReplayStatus.STALE_SOURCE
                if source.status != SourceStatus.ACTIVE:
                    return EducationalReplayStatus.STALE_SOURCE
                source_hashes.add(source.record.record_hash)
        if not set(graph.evidence_hashes) <= evidence_hashes:
            return EducationalReplayStatus.STALE_EVIDENCE
        if not set(graph.source_hashes) <= source_hashes:
            return EducationalReplayStatus.STALE_SOURCE
    except (TypeError, ValueError):
        return EducationalReplayStatus.INVALID_SOURCE_RESULT
    return EducationalReplayStatus.CURRENT


def _answer_key_matches(instance, graph) -> bool:
    if instance.hidden_answer_graph_hash != graph.graph_hash:
        return False
    root = next(
        (node for node in graph.nodes if node.node_id == graph.root_result_node_id), None
    )
    if root is None or root.kind is not GraphNodeKind.FINAL_RESULT:
        return False
    expected = instance.hidden_expected_answer
    if "value" in expected:
        return str(root.exact_output) == expected["value"]
    if "element_counts" in expected:
        return root.exact_output == expected["element_counts"]
    if {"lower", "upper"} <= expected.keys():
        return root.exact_output == {
            "lower": expected["lower"],
            "upper": expected["upper"],
        }
    if "text" in expected:
        return str(root.exact_output) == expected["text"]
    return False


def _result(status: EducationalReplayStatus) -> EducationalCurrentnessResult:
    return EducationalCurrentnessResult(status=status)


CHEMISTRY_STATUS_MAP = {
    ChemistryReplayStatus.CURRENT: EducationalReplayStatus.CURRENT,
    ChemistryReplayStatus.STALE_FACT_MEMORY: EducationalReplayStatus.STALE_FACT_MEMORY,
    ChemistryReplayStatus.STALE_ELEMENT_CLAIM: EducationalReplayStatus.STALE_CLAIM,
    ChemistryReplayStatus.RETRACTED_ELEMENT_CLAIM: EducationalReplayStatus.STALE_CLAIM,
    ChemistryReplayStatus.SUPERSEDED_ELEMENT_CLAIM: EducationalReplayStatus.STALE_CLAIM,
    ChemistryReplayStatus.CONFLICTING_ATOMIC_WEIGHT: EducationalReplayStatus.STALE_CLAIM,
    ChemistryReplayStatus.CONTRADICTING_EVIDENCE: EducationalReplayStatus.STALE_EVIDENCE,
    ChemistryReplayStatus.STALE_EVIDENCE: EducationalReplayStatus.STALE_EVIDENCE,
    ChemistryReplayStatus.STALE_SOURCE: EducationalReplayStatus.STALE_SOURCE,
    ChemistryReplayStatus.RETRACTED_SOURCE: EducationalReplayStatus.STALE_SOURCE,
    ChemistryReplayStatus.RETRACTED_UPSTREAM_SOURCE: EducationalReplayStatus.STALE_UPSTREAM_SOURCE,
    ChemistryReplayStatus.UNAVAILABLE_UPSTREAM_SOURCE: EducationalReplayStatus.STALE_UPSTREAM_SOURCE,
    ChemistryReplayStatus.STALE_UPSTREAM_SOURCE: EducationalReplayStatus.STALE_UPSTREAM_SOURCE,
    ChemistryReplayStatus.STALE_SOURCE_CHAIN: EducationalReplayStatus.STALE_SOURCE_CHAIN,
    ChemistryReplayStatus.STALE_TOOL_IMPLEMENTATION: EducationalReplayStatus.STALE_TOOL,
    ChemistryReplayStatus.STALE_ROUNDING_POLICY: EducationalReplayStatus.STALE_TOOL,
    ChemistryReplayStatus.STALE_DOMAIN_MANIFEST: EducationalReplayStatus.STALE_DOMAIN,
    ChemistryReplayStatus.INVALID_RESULT: EducationalReplayStatus.INVALID_SOURCE_RESULT,
}
