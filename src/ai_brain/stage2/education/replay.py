"""Current-dependency and event-chain replay for educational sessions."""

from __future__ import annotations

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.education.exercise_generation import verify_exercise_instance
from ai_brain.stage2.education.exercises import verify_exercise_spec
from ai_brain.stage2.education.models import (
    EducationalReplayStatus,
    TutorSessionStatus,
)
from ai_brain.stage2.education.serialization import (
    graph_from_dict,
    instance_from_dict,
    spec_from_dict,
)
from ai_brain.stage2.education.sessions import apply_event, start_session
from ai_brain.stage2.education.version import (
    GRADING_SCHEMA_VERSION,
    HINT_POLICY_VERSION,
)


def replay_educational_session(
    store, adapter: ChemistryEducationAdapter, session_id: str
):
    try:
        stored = store.get_session(session_id)
        instance = instance_from_dict(
            store.get_artifact(stored.exercise_hash, expected_kind="exercise_instance")
        )
        spec = spec_from_dict(
            store.get_artifact(
                instance.exercise_spec_hash, expected_kind="exercise_spec"
            )
        )
        graph = graph_from_dict(
            store.get_artifact(stored.graph_hash, expected_kind="derivation_graph")
        )
        verify_exercise_spec(spec)
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
    if graph.tool_implementation_hash is not None:
        current = {
            value for _, value in adapter.service.registry.current_manifest_hashes()
        }
        if graph.tool_implementation_hash not in current:
            return _status(EducationalReplayStatus.STALE_TOOL, session_id)
    if instance.exercise_spec_hash != spec.spec_hash:
        return _status(EducationalReplayStatus.STALE_EXERCISE_SPEC, session_id)
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
    if GRADING_SCHEMA_VERSION != 1:
        return _status(EducationalReplayStatus.STALE_GRADING_POLICY, session_id)
    if HINT_POLICY_VERSION != "1.0":
        return _status(EducationalReplayStatus.STALE_HINT_POLICY, session_id)
    events = store.events(session_id)
    if not events:
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    rebuilt, presented = start_session(
        instance, session_id=session_id, created_at=events[0].created_at
    )
    if presented != events[0]:
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    try:
        for event in events[1:]:
            rebuilt = apply_event(rebuilt, event)
    except ValueError:
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    if rebuilt != stored:
        return _status(EducationalReplayStatus.INVALID_SESSION, session_id)
    return {
        **_status(EducationalReplayStatus.CURRENT, session_id),
        "event_count": len(events),
        "session_status": TutorSessionStatus(stored.status).value,
        "graph_hash": graph.graph_hash,
        "exercise_hash": instance.instance_hash,
    }


def _status(status: EducationalReplayStatus, session_id: str):
    return {"status": status.value, "session_id": session_id}
