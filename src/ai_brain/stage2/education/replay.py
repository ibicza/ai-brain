"""Live factual/calculation replay for persisted educational sessions."""

from __future__ import annotations

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.domains.chemistry.models import ChemistryReplayStatus
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.education.compilation_receipts import verify_compilation_receipt
from ai_brain.stage2.education.exercise_generation import verify_exercise_instance
from ai_brain.stage2.education.models import EducationalReplayStatus
from ai_brain.stage2.education.version import (
    GRADING_SCHEMA_VERSION,
    HINT_POLICY_VERSION,
)
from ai_brain.stage2.facts.models import (
    ClaimStatus,
    EvidenceConflictState,
    SourceStatus,
)


def replay_educational_session(
    store, adapter: ChemistryEducationAdapter, session_id: str
):
    try:
        stored = store.get_session(session_id)
        instance = store.get_artifact(
            stored.exercise_hash, expected_kind="exercise_instance_internal"
        )
        spec = store.get_artifact(
            instance.exercise_spec_hash, expected_kind="exercise_spec"
        )
        graph = store.get_artifact(stored.graph_hash, expected_kind="derivation_graph")
        receipt = store.get_artifact(
            instance.compilation_receipt_hash,
            expected_kind="compilation_receipt",
        )
        verify_exercise_instance(instance, spec, graph)
    except (KeyError, TypeError, ValueError):
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    manifest = adapter.service.manifest
    if graph.domain_version != manifest["domain_version"]:
        return _status(EducationalReplayStatus.STALE_DOMAIN, session_id)
    if graph.fact_memory_snapshot_hash != manifest["fact_memory_snapshot_hash"]:
        return _status(EducationalReplayStatus.STALE_FACT_MEMORY, session_id)
    if graph.source_chain_hash != manifest["source_chain_hash"]:
        return _status(EducationalReplayStatus.STALE_SOURCE_CHAIN, session_id)
    try:
        verify_compilation_receipt(
            receipt, adapter.service, graph_hash=graph.graph_hash
        )
    except ValueError:
        return _status(EducationalReplayStatus.STALE_COMPILATION_RECEIPT, session_id)
    source_status = _replay_source(graph, adapter)
    if source_status is not EducationalReplayStatus.CURRENT:
        return _status(source_status, session_id)
    try:
        adapter.verify_graph(graph)
    except ValueError:
        return _status(EducationalReplayStatus.INVALID_GRAPH, session_id)
    root = next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )
    expected = instance.hidden_expected_answer
    if "value" in expected and str(root.exact_output) != expected["value"]:
        return _status(EducationalReplayStatus.STALE_ANSWER_KEY, session_id)
    if "element_counts" in expected and root.exact_output != expected["element_counts"]:
        return _status(EducationalReplayStatus.STALE_ANSWER_KEY, session_id)
    if {"lower", "upper"} <= expected.keys() and root.exact_output != {
        "lower": expected["lower"],
        "upper": expected["upper"],
    }:
        return _status(EducationalReplayStatus.STALE_ANSWER_KEY, session_id)
    if GRADING_SCHEMA_VERSION != 2:
        return _status(EducationalReplayStatus.STALE_GRADING_POLICY, session_id)
    if HINT_POLICY_VERSION != "2.0":
        return _status(EducationalReplayStatus.STALE_HINT_POLICY, session_id)
    events = store.events(session_id)
    if not events or events[0].event_type != "SESSION_PRESENTED":
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    try:
        # Store verification independently rebuilds from the presentation event.
        store.verify()
    except ValueError:
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    return {
        **_status(EducationalReplayStatus.CURRENT, session_id),
        "event_count": len(events),
        "session_status": stored.status.value,
        "graph_hash": graph.graph_hash,
        "exercise_hash": instance.instance_hash,
        "live_source_replay": "CURRENT",
    }


def _replay_source(graph, adapter) -> EducationalReplayStatus:
    if graph.source_result_type.startswith("ChemistryResultBundle:"):
        status = replay_chemistry_result(
            graph.source_result_artifact,
            adapter.service.memory,
            adapter.service.manifest,
        )
        return _CHEMISTRY_STATUS_MAP.get(
            status, EducationalReplayStatus.INVALID_SOURCE_RESULT
        )
    try:
        evidence_hashes = set()
        source_hashes = set()
        for claim_id in graph.claim_ids:
            state = adapter.service.memory.get_claim_state(claim_id)
            if state.status in {ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED}:
                return EducationalReplayStatus.STALE_CLAIM
            if (
                state.status not in {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED}
                or state.evidence_conflict_state == EvidenceConflictState.CONTESTED
                or state.contradicting_evidence_ids
            ):
                return EducationalReplayStatus.STALE_CLAIM
            for evidence_id in state.supporting_evidence_ids:
                evidence = adapter.service.memory.verify_evidence(evidence_id)
                evidence_hashes.add(evidence.evidence_hash)
                source = adapter.service.memory.get_source_state(evidence.source_id)
                if source.status != SourceStatus.ACTIVE:
                    return EducationalReplayStatus.STALE_SOURCE
                source_hashes.add(source.record.record_hash)
        if not set(graph.evidence_hashes) <= evidence_hashes:
            return EducationalReplayStatus.STALE_EVIDENCE
        if not set(graph.source_hashes) <= source_hashes:
            return EducationalReplayStatus.STALE_SOURCE
    except (KeyError, TypeError, ValueError):
        return EducationalReplayStatus.INVALID_SOURCE_RESULT
    return EducationalReplayStatus.CURRENT


_CHEMISTRY_STATUS_MAP = {
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


def _status(status: EducationalReplayStatus, session_id: str):
    return {"status": status.value, "session_id": session_id}
