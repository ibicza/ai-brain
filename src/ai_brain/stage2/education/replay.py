"""Live factual/calculation replay for persisted educational sessions."""

from __future__ import annotations

from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.education.currentness import evaluate_dependency_currentness
from ai_brain.stage2.education.exercise_generation import verify_exercise_instance
from ai_brain.stage2.education.models import EducationalReplayStatus


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
    currentness = evaluate_dependency_currentness(
        adapter.service, graph, receipt, instance, spec
    )
    if not currentness.current:
        return _status(currentness.status, session_id)
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


def _status(status: EducationalReplayStatus, session_id: str):
    return {"status": status.value, "session_id": session_id}
